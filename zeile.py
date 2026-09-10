#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""A small, fast GTK4 markdown viewer.

Renders a markdown file with python-markdown into a WebKitGTK view and
reloads it whenever the file changes on disk. Symlinks are resolved so
that watching a link follows its target.

A .md file is untrusted content a user double-clicks (install.sh makes this
the system default handler for text/markdown), so the rendered document runs
with document JavaScript structurally disabled, its HTML run through an
explicit sanitizer allowlist, no persistent storage, no network egress
beyond the click-to-open-externally path, and developer tools off unless
--debug/ZEILE_DEBUG is set. See docs in the repo's HANDOFF.md and its linked
plan for the full threat model and what was measured, not assumed.
"""

from __future__ import annotations

import argparse
import gettext
import html
import json
import os
import re
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

import markdown  # noqa: E402
import nh3  # noqa: E402
from gi.repository import Gio, GLib, Gtk, WebKit  # noqa: E402

from markdown_ext import MermaidExtension  # noqa: E402

APP_ID = "com.erdlabs.zeile"
__version__ = "0.1.0"

# fallback=True: on a system with no compiled translation for the current
# locale (or none at all, as on this dev machine's default LANG), _() just
# returns the original English string instead of raising -- translation is
# additive, never a hard requirement to run.
_ = gettext.translation(
    "zeile", localedir=Path(__file__).resolve().parent / "locale", fallback=True
).gettext

EXTENSIONS = [
    "extra",  # tables, fenced_code, footnotes, def_list, abbr, attr_list
    "admonition",
    "codehilite",
    "sane_lists",
    "smarty",
    "toc",
    "pymdownx.tasklist",
]

EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False, "noclasses": False},
    "toc": {"permalink": False},
    "pymdownx.tasklist": {"custom_checkbox": False},
}

# A YAML frontmatter block, stripped before conversion -- python-markdown has
# no opinion on frontmatter, so left alone it renders as a literal <hr> plus
# a paragraph of raw "key: value" text, confirmed broken. Anchored to the
# very start of the document; the closing "---" must be alone on its own
# line, same shape most static-site generators use.
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


# No script-src entry: enable-javascript-markup=False (set on the WebView
# below) already prevents any document <script> from running, and nh3 (see
# sanitize_html()) strips <script> tags outright regardless. This CSP layer
# exists for the non-script vector that needs no script at all -- an
# `<img src=http://tracker/pixel>` beacon -- which img-src 'self' kills.
# style-src allows inline <style> since we own all page styling ourselves
# and inject it as a literal <style> block below.
_CSP = (
    "default-src 'none'; img-src 'self' data:; font-src 'self' data:; "
    "style-src 'unsafe-inline'"
)

# nh3's own defaults strip `class`/`id` from most tags. Used as-is that
# silently breaks codehilite's <span class="k"> (colourless syntax
# highlighting), every heading id (kills TOC anchors), and footnote id/href
# pairs -- confirmed empirically before wiring this in. Mermaid diagrams are
# deliberately NOT special-cased here: they never reach the sanitizer as SVG
# markup at all (see markdown_ext.MermaidExtension's nonce mechanism), so
# this allowlist stays exactly as narrow as the plain-markdown features
# above actually need.
_ALLOWED_TAGS = nh3.ALLOWED_TAGS | {"input"}
_ALLOWED_ATTRIBUTES = {
    **nh3.ALLOWED_ATTRIBUTES,
    "abbr": {"title"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "h5": {"id"},
    "h6": {"id"},
    "span": {"class"},
    "code": {"class"},
    "pre": {"class"},
    "div": {"class"},
    "p": {"class"},
    "ul": {"class"},
    "li": {"id", "class"},
    "sup": {"id"},
    "a": {"id", "href", "class", "name"},
    # pymdownx.tasklist checkboxes -- read-only, `disabled` is load-bearing
    # (without it a click would try to toggle state nothing persists).
    "input": {"type", "disabled", "checked"},
}


def sanitize_html(body: str) -> str:
    """Strip everything nh3.clean() doesn't explicitly allow.

    Runs on markdown's converted output, which includes not just markdown
    syntax but any raw HTML a .md source embeds directly (the `extra`
    bundle's html passthrough) -- <script>, on* handlers, javascript:/data:
    URLs, <iframe>/<object>/<embed>, meta-refresh and <style> blocks are all
    removed here, verified empirically against nh3's actual default+override
    behaviour rather than assumed from its docs.
    """
    return nh3.clean(body, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRIBUTES)


def read_asset(name: str) -> str:
    """Return the contents of an asset shipped next to this script."""
    return (Path(__file__).resolve().parent / "assets" / name).read_text(encoding="utf-8")


def render_body(text: str, *, enable_mermaid: bool, dark: bool) -> tuple[str, list[dict]]:
    """Convert markdown text to sanitized HTML body content.

    Pure function -- no file I/O, no GTK -- so it's unit-testable directly.
    Returns (body, toc_tokens): the `toc` extension already computes a
    heading tree for anchor generation, so the TOC overlay reuses it instead
    of re-deriving it from the rendered HTML.
    """
    text = _strip_frontmatter(text)
    mermaid_ext = MermaidExtension(enable_mermaid=enable_mermaid, dark=dark)
    md = markdown.Markdown(
        extensions=[*EXTENSIONS, mermaid_ext],
        extension_configs=EXTENSION_CONFIGS,
    )
    body = md.convert(text)
    body = sanitize_html(body)
    body = mermaid_ext.resolve(body)
    return body, md.toc_tokens


def build_document(body: str, title: str) -> str:
    """Wrap a sanitized HTML body in the full page shell (CSP, stylesheet)."""
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{_CSP}\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{read_asset('style.css')}</style>"
        f"</head><body><article class='markdown-body'>{body}</article>"
        "</body></html>"
    )


def render(path: Path, *, enable_mermaid: bool, dark: bool) -> tuple[str, list[dict]]:
    """Read `path`, render and sanitize its markdown, return (html_doc, toc_tokens)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        body = f"<h1>{_('Cannot read file')}</h1><pre>{html.escape(str(exc))}</pre>"
        toc_tokens: list[dict] = []
    else:
        body, toc_tokens = render_body(text, enable_mermaid=enable_mermaid, dark=dark)

    return build_document(body, path.name), toc_tokens


def flatten_toc(tokens: list[dict], depth: int = 0) -> list[tuple[int, str, str]]:
    """Flatten the `toc` extension's nested heading tree to (depth, id, name)."""
    flat: list[tuple[int, str, str]] = []
    for token in tokens:
        flat.append((depth, token["id"], token["name"]))
        flat.extend(flatten_toc(token.get("children", []), depth + 1))
    return flat


_MARKDOWN_SUFFIXES = {".md", ".markdown"}


class Viewer(Gtk.ApplicationWindow):
    def __init__(
        self, app: Gtk.Application, path: Path, *, enable_mermaid: bool, debug: bool
    ) -> None:
        super().__init__(application=app, title=path.name)
        self.set_default_size(900, 1000)

        # Show the name the user opened, but watch the real file: monitoring a
        # symlink itself never reports edits made to its target.
        self.display_name = path.name
        self.path = path.resolve()
        self.enable_mermaid = enable_mermaid
        self.monitor: Gio.FileMonitor | None = None
        self._reload_source: int | None = None
        self._back_stack: list[Path] = []
        self._forward_stack: list[Path] = []

        self.dark = Gtk.Settings.get_default().get_property(
            "gtk-application-prefer-dark-theme"
        )

        # Ephemeral session: no cookie jar, no HTTP cache persisted to disk.
        # decide-policy below is what actually stops any request from being
        # made in the first place for anything but the local document tree.
        session = WebKit.NetworkSession.new_ephemeral()
        self.webview = WebKit.WebView(network_session=session)
        settings = self.webview.get_settings()
        settings.set_enable_javascript(True)
        # False here, not set_enable_javascript(False): this is the setting
        # that actually blocks a document's own <script>/onerror=, verified
        # empirically (window.* set by an injected <script> stayed
        # undefined). enable_javascript stays True so the app's own
        # evaluate_javascript() calls (scroll position, future TOC-jump)
        # keep working -- they never evaluate anything sourced from the
        # document itself.
        settings.set_enable_javascript_markup(False)
        settings.set_enable_html5_local_storage(False)
        settings.set_enable_html5_database(False)
        settings.set_enable_developer_extras(debug)
        self.webview.connect("decide-policy", self._on_decide_policy)
        self.find_controller = self.webview.get_find_controller()

        self.back_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.back_button.set_tooltip_text(_("Back (Alt+Left)"))
        self.back_button.connect("clicked", lambda _b: self.go_back())
        self.forward_button = Gtk.Button(icon_name="go-next-symbolic")
        self.forward_button.set_tooltip_text(_("Forward (Alt+Right)"))
        self.forward_button.connect("clicked", lambda _b: self.go_forward())
        self._update_nav_sensitivity()

        self._toc_flat: list[tuple[int, str, str]] = []
        self.toc_list = Gtk.ListBox()
        self.toc_list.connect("row-activated", self._on_toc_row_activated)
        toc_scroller = Gtk.ScrolledWindow()
        toc_scroller.set_min_content_height(300)
        toc_scroller.set_min_content_width(240)
        toc_scroller.set_child(self.toc_list)
        self.toc_popover = Gtk.Popover()
        self.toc_popover.set_child(toc_scroller)
        self.toc_popover.connect("show", self._populate_toc)
        self.toc_button = Gtk.MenuButton(icon_name="view-list-symbolic")
        self.toc_button.set_tooltip_text(_("Table of contents (Ctrl+T)"))
        self.toc_button.set_popover(self.toc_popover)

        export_button = Gtk.Button(icon_name="document-save-symbolic")
        export_button.set_tooltip_text(_("Export PDF…"))
        export_button.connect("clicked", lambda _b: self._export_pdf())
        print_button = Gtk.Button(icon_name="document-print-symbolic")
        print_button.set_tooltip_text(_("Print (Ctrl+P)"))
        print_button.connect("clicked", lambda _b: self._print_dialog())
        about_button = Gtk.Button(icon_name="help-about-symbolic")
        about_button.set_tooltip_text(_("About zeile"))
        about_button.connect("clicked", lambda _b: self._show_about())

        self._title_label = Gtk.Label(label=self.display_name)
        header = Gtk.HeaderBar()
        header.set_title_widget(self._title_label)
        header.pack_start(self.back_button)
        header.pack_start(self.forward_button)
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic")
        reload_button.set_tooltip_text(_("Reload (Ctrl+R)"))
        reload_button.connect("clicked", lambda _b: self.reload())
        header.pack_start(reload_button)
        header.pack_start(self.toc_button)
        header.pack_end(about_button)
        header.pack_end(export_button)
        header.pack_end(print_button)
        self.set_titlebar(header)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.connect("search-changed", self._on_search_changed)
        self.search_entry.connect(
            "next-match", lambda *_: self.find_controller.search_next()
        )
        self.search_entry.connect(
            "previous-match", lambda *_: self.find_controller.search_previous()
        )
        self.search_entry.connect("stop-search", lambda *_: self._close_search())
        self.search_bar = Gtk.SearchBar()
        self.search_bar.set_child(self.search_entry)
        self.search_bar.connect_entry(self.search_entry)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.webview)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.search_bar)
        box.append(scroller)
        box.set_vexpand(True)
        self.set_child(box)

        self._add_shortcuts()
        self.reload()
        self._watch()

    def _on_decide_policy(
        self,
        _webview: WebKit.WebView,
        decision: WebKit.PolicyDecision,
        decision_type: WebKit.PolicyDecisionType,
    ) -> bool:
        """Only allow file:// navigation under the open document's directory.

        A local .md/.markdown link re-enters our own renderer via
        navigate_to() instead of letting WebKit load it directly (which
        would dump raw markdown source with no way back -- confirmed broken
        before this). Any other local file:// link (an image, say) still
        loads in the WebView directly. Everything else -- http(s), any other
        scheme, or a file:// path outside the document's directory tree --
        is handed to the system's default opener. Combined with the
        ephemeral NetworkSession above, this is what actually makes "no
        network access" true rather than aspirational.
        """
        if decision_type != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            decision.use()
            return True

        uri = decision.get_navigation_action().get_request().get_uri()
        gfile = Gio.File.new_for_uri(uri)
        local_path = gfile.get_path()
        if gfile.get_uri_scheme() == "file" and local_path is not None:
            target = Path(local_path).resolve()
            if target.is_relative_to(self.path.parent):
                if target != self.path and target.suffix.lower() in _MARKDOWN_SUFFIXES:
                    decision.ignore()
                    self.navigate_to(target)
                    return True
                decision.use()
                return True

        decision.ignore()
        Gio.AppInfo.launch_default_for_uri(uri)
        return True

    def navigate_to(self, path: Path, *, record_history: bool = True) -> None:
        """Switch the currently displayed document, without opening a new window."""
        if record_history:
            self._back_stack.append(self.path)
            self._forward_stack.clear()
        self.path = path.resolve()
        self.display_name = self.path.name
        self._title_label.set_label(self.display_name)
        self.set_title(self.display_name)
        self._update_nav_sensitivity()
        self._watch()
        self.reload()

    def go_back(self) -> bool:
        if self._back_stack:
            self._forward_stack.append(self.path)
            self.navigate_to(self._back_stack.pop(), record_history=False)
        return True

    def go_forward(self) -> bool:
        if self._forward_stack:
            self._back_stack.append(self.path)
            self.navigate_to(self._forward_stack.pop(), record_history=False)
        return True

    def _update_nav_sensitivity(self) -> None:
        self.back_button.set_sensitive(bool(self._back_stack))
        self.forward_button.set_sensitive(bool(self._forward_stack))

    def _on_search_changed(self, entry: Gtk.SearchEntry) -> None:
        text = entry.get_text()
        if not text:
            self.find_controller.search_finish()
            return
        options = WebKit.FindOptions.CASE_INSENSITIVE | WebKit.FindOptions.WRAP_AROUND
        self.find_controller.search(text, options, 1000)

    def _close_search(self) -> None:
        self.find_controller.search_finish()
        self.search_bar.set_search_mode(False)

    def _toggle_search(self) -> bool:
        active = not self.search_bar.get_search_mode()
        self.search_bar.set_search_mode(active)
        if active:
            self.search_entry.grab_focus()
        else:
            self.find_controller.search_finish()
        return True

    def _populate_toc(self, *_args) -> bool:
        child = self.toc_list.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.toc_list.remove(child)
            child = following
        for depth, _heading_id, name in self._toc_flat:
            label = Gtk.Label(label=name, xalign=0)
            label.set_margin_start(12 + depth * 16)
            label.set_margin_top(4)
            label.set_margin_bottom(4)
            self.toc_list.append(label)
        return True

    def _on_toc_row_activated(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow) -> None:
        index = row.get_index()
        if 0 <= index < len(self._toc_flat):
            _depth, heading_id, _name = self._toc_flat[index]
            self.webview.evaluate_javascript(
                f"document.getElementById({json.dumps(heading_id)}).scrollIntoView();",
                -1,
                None,
                None,
                None,
                None,
                None,
            )
        self.toc_popover.popdown()

    def _show_about(self) -> None:
        about = Gtk.AboutDialog()
        about.set_transient_for(self)
        about.set_modal(True)
        about.set_program_name("zeile")
        about.set_version(__version__)
        about.set_comments(_("A small, fast, read-only markdown viewer."))
        about.set_license_type(Gtk.License.GPL_3_0)
        about.set_website("https://erdlabs.com")
        about.set_website_label("erdlabs.com")
        about.present()

    def _print_dialog(self) -> bool:
        """Interactive Ctrl+P: the OS print dialog, printer/copies/etc."""
        op = WebKit.PrintOperation.new(self.webview)
        op.run_dialog(self)
        return True

    def _export_pdf(self) -> None:
        """Non-interactive PDF export: a save-location picker, then straight
        to a PDF file -- no OS print dialog in between."""
        dialog = Gtk.FileDialog()
        dialog.set_title(_("Export PDF"))
        dialog.set_initial_name(self.path.stem + ".pdf")
        dialog.save(self, None, self._on_export_pdf_chosen)

    def _on_export_pdf_chosen(
        self, dialog: Gtk.FileDialog, result: Gio.AsyncResult
    ) -> None:
        try:
            gfile = dialog.save_finish(result)
        except GLib.Error:
            return  # user cancelled
        settings = Gtk.PrintSettings()
        settings.set("output-uri", gfile.get_uri())
        settings.set("output-file-format", "pdf")
        op = WebKit.PrintOperation.new(self.webview)
        op.set_print_settings(settings)
        op.print_()

    def _add_shortcuts(self) -> None:
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.GLOBAL)
        for accel, callback in (
            ("<Control>r", lambda *_: self.reload()),
            ("<Control>w", lambda *_: self.close()),
            ("<Control>q", lambda *_: self.close()),
            ("<Control>plus", lambda *_: self._zoom(0.1)),
            ("<Control>equal", lambda *_: self._zoom(0.1)),
            ("<Control>minus", lambda *_: self._zoom(-0.1)),
            ("<Control>0", lambda *_: self.webview.set_zoom_level(1.0)),
            ("<Control>f", lambda *_: self._toggle_search()),
            ("<Alt>Left", lambda *_: self.go_back()),
            ("<Alt>Right", lambda *_: self.go_forward()),
            ("<Control>t", lambda *_: self.toc_popover.popup()),
            ("<Control>p", lambda *_: self._print_dialog()),
        ):
            controller.add_shortcut(
                Gtk.Shortcut(
                    trigger=Gtk.ShortcutTrigger.parse_string(accel),
                    action=Gtk.CallbackAction.new(callback),
                )
            )
        self.add_controller(controller)

    def _zoom(self, delta: float) -> bool:
        level = min(3.0, max(0.4, self.webview.get_zoom_level() + delta))
        self.webview.set_zoom_level(level)
        return True

    def reload(self) -> bool:
        """Re-render the file, preserving the current scroll position."""
        self.webview.evaluate_javascript(
            "window.__zeileScroll = window.scrollY;", -1, None, None, None, None, None
        )
        html_doc, toc_tokens = render(
            self.path, enable_mermaid=self.enable_mermaid, dark=self.dark
        )
        self._toc_flat = flatten_toc(toc_tokens)
        self.webview.load_html(html_doc, self.path.as_uri())
        return True

    def _watch(self) -> None:
        """(Re-)establish the file monitor for self.path.

        Safe to call again after navigate_to() switches documents -- cancels
        whatever monitor was watching the previous file first, so an edit to
        a document we've since navigated away from doesn't trigger a reload.
        """
        if self.monitor is not None:
            self.monitor.cancel()
        gfile = Gio.File.new_for_path(str(self.path))
        self.monitor = gfile.monitor_file(Gio.FileMonitorFlags.NONE, None)
        self.monitor.connect("changed", self._on_changed)

    def _on_changed(self, _monitor, _f, _other, event) -> None:
        if event not in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.CREATED,
        ):
            return
        # Editors write in bursts; coalesce them into a single reload.
        if self._reload_source is not None:
            GLib.source_remove(self._reload_source)
        self._reload_source = GLib.timeout_add(120, self._debounced_reload)

    def _debounced_reload(self) -> bool:
        self._reload_source = None
        self.reload()
        return GLib.SOURCE_REMOVE


class ZeileApp(Gtk.Application):
    def __init__(self, path: Path, *, enable_mermaid: bool, debug: bool) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path
        self.enable_mermaid = enable_mermaid
        self.debug = debug

    def do_activate(self) -> None:
        Viewer(
            self, self.path, enable_mermaid=self.enable_mermaid, debug=self.debug
        ).present()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal GTK4 markdown viewer.")
    parser.add_argument("file", type=Path, help="markdown file to display")
    parser.add_argument(
        "--enable-mermaid",
        action="store_true",
        help="render ```mermaid fences via mmdc (mermaid-cli); off by default "
        "so the base install needs no Node.js",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable WebKit developer tools (same as setting ZEILE_DEBUG)",
    )
    args = parser.parse_args()

    if not args.file.exists():
        print(f"zeile: no such file: {args.file}", file=sys.stderr)
        return 1

    debug = args.debug or bool(os.environ.get("ZEILE_DEBUG"))
    return ZeileApp(args.file, enable_mermaid=args.enable_mermaid, debug=debug).run([])


if __name__ == "__main__":
    sys.exit(main())
