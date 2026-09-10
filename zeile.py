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
import html
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


def render(path: Path, *, enable_mermaid: bool, dark: bool) -> str:
    """Convert a markdown file to a full HTML document."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        body = f"<h1>Cannot read file</h1><pre>{html.escape(str(exc))}</pre>"
    else:
        text = _strip_frontmatter(text)
        mermaid_ext = MermaidExtension(enable_mermaid=enable_mermaid, dark=dark)
        md = markdown.Markdown(
            extensions=[*EXTENSIONS, mermaid_ext],
            extension_configs=EXTENSION_CONFIGS,
        )
        body = md.convert(text)
        body = sanitize_html(body)
        body = mermaid_ext.resolve(body)

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{_CSP}\">"
        f"<title>{html.escape(path.name)}</title>"
        f"<style>{read_asset('style.css')}</style>"
        f"</head><body><article class='markdown-body'>{body}</article>"
        "</body></html>"
    )


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

        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label=self.display_name))
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic")
        reload_button.set_tooltip_text("Reload (Ctrl+R)")
        reload_button.connect("clicked", lambda _b: self.reload())
        header.pack_start(reload_button)
        self.set_titlebar(header)

        scroller = Gtk.ScrolledWindow()
        scroller.set_child(self.webview)
        self.set_child(scroller)

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

        Everything else -- http(s), any other scheme, or a file:// path
        outside that tree -- is handed to the system's default opener
        instead of being loaded in this WebView. Combined with the ephemeral
        NetworkSession above, this is what actually makes "no network
        access" true rather than aspirational.
        """
        if decision_type != WebKit.PolicyDecisionType.NAVIGATION_ACTION:
            decision.use()
            return True

        uri = decision.get_navigation_action().get_request().get_uri()
        gfile = Gio.File.new_for_uri(uri)
        local_path = gfile.get_path()
        if (
            gfile.get_uri_scheme() == "file"
            and local_path is not None
            and Path(local_path).resolve().is_relative_to(self.path.parent)
        ):
            decision.use()
            return True

        decision.ignore()
        Gio.AppInfo.launch_default_for_uri(uri)
        return True

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
        html_doc = render(self.path, enable_mermaid=self.enable_mermaid, dark=self.dark)
        self.webview.load_html(html_doc, self.path.as_uri())
        return True

    def _watch(self) -> None:
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
