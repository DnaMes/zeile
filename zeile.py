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
from functools import partial
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


THEME_OPTIONS = (
    "auto",
    "github-light",
    "github-dark",
    "catppuccin-latte",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "catppuccin-mocha",
    "solarized-light",
    "solarized-dark",
    "gruvbox-light",
    "gruvbox-dark",
    "nord",
    "dracula",
    "rose-pine",
    "rose-pine-dawn",
    "tokyo-night",
    "tokyo-night-day",
)

THEME_DARKNESS: dict[str, bool | None] = {
    "auto": None,
    "github-light": False,
    "github-dark": True,
    "catppuccin-latte": False,
    "catppuccin-frappe": True,
    "catppuccin-macchiato": True,
    "catppuccin-mocha": True,
    "solarized-light": False,
    "solarized-dark": True,
    "gruvbox-light": False,
    "gruvbox-dark": True,
    "nord": True,
    "dracula": True,
    "rose-pine": True,
    "rose-pine-dawn": False,
    "tokyo-night": True,
    "tokyo-night-day": False,
}


BODY_FONT_OPTIONS = (
    "system",
    "inter",
    "atkinson",
    "ia-writer",
    "noto-serif",
    "ibmplex-sans",
)

CODE_FONT_OPTIONS = (
    "system",
    "jetbrains-mono",
    "ia-writer",
    "fira-code",
    "cascadia-code",
)

_DEFAULT_SETTINGS = {
    "theme": "auto",
    "body_font": "system",
    "code_font": "system",
    "zoom": "1.0",
    "window_w": "900",
    "window_h": "1000",
    "window_maximized": "false",
}


def _default_settings_path() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "zeile"
        / "settings.json"
    )


def _coerce_theme(theme: str) -> str:
    return theme if theme in THEME_OPTIONS else _DEFAULT_SETTINGS["theme"]


def _coerce_font(font: str, kind: str) -> str:
    allowed = BODY_FONT_OPTIONS if kind == "body" else CODE_FONT_OPTIONS
    return (
        font
        if font in allowed
        else _DEFAULT_SETTINGS["body_font" if kind == "body" else "code_font"]
    )


def _coerce_number(
    value, lo: float, hi: float, *, integer: bool = False, default: str | None = None
) -> str:
    """Clamp-to-range number coercion for free-form settings values.

    Unparseable input falls back to `default` (the documented default), not
    to the range minimum -- "garbage" should restore the shipped default,
    not produce a 200px window.
    """
    try:
        n = float(value)
    except (TypeError, ValueError):
        if default is not None:
            return default
        n = 0.0
    n = min(hi, max(lo, n))
    return str(int(n)) if integer else str(n)


def is_theme_dark(theme_id: str, *, fallback: bool) -> bool:
    value = THEME_DARKNESS.get(theme_id)
    if value is None:
        return fallback
    return value


def load_settings(*, path: Path | None = None) -> dict[str, str]:
    """Load viewer settings from JSON with robust fallback."""
    settings_path = path or _default_settings_path()
    settings = dict(_DEFAULT_SETTINGS)
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings

    if not isinstance(data, dict):
        return settings

    theme = data.get("theme")
    if isinstance(theme, str):
        settings["theme"] = _coerce_theme(theme)

    body_font = data.get("body_font")
    if isinstance(body_font, str):
        settings["body_font"] = _coerce_font(body_font, kind="body")

    code_font = data.get("code_font")
    if isinstance(code_font, str):
        settings["code_font"] = _coerce_font(code_font, kind="code")

    # Free-form numeric/bool keys: anything unparseable keeps the default,
    # never raises, never propagates a bad value into the UI.
    zoom = data.get("zoom")
    if isinstance(zoom, (int, float, str)):
        try:
            z = float(zoom)
            if 0.4 <= z <= 3.0:
                settings["zoom"] = str(z)
        except (TypeError, ValueError):
            pass
    for key, lo, hi in (("window_w", 200, 20000), ("window_h", 200, 20000)):
        val = data.get(key)
        if isinstance(val, (int, float, str)):
            try:
                n = int(float(val))
                if lo <= n <= hi:
                    settings[key] = str(n)
            except (TypeError, ValueError):
                pass
    maximized = data.get("window_maximized")
    if isinstance(maximized, bool):
        settings["window_maximized"] = "true" if maximized else "false"
    elif maximized in ("true", "false"):
        settings["window_maximized"] = maximized

    return settings


def save_settings(settings: dict[str, str], *, path: Path | None = None) -> None:
    """Persist settings if possible; silently ignore environment write failures."""
    settings_path = path or _default_settings_path()
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "theme": _coerce_theme(settings.get("theme", _DEFAULT_SETTINGS["theme"])),
            "body_font": _coerce_font(
                settings.get("body_font", _DEFAULT_SETTINGS["body_font"]), kind="body"
            ),
            "code_font": _coerce_font(
                settings.get("code_font", _DEFAULT_SETTINGS["code_font"]), kind="code"
            ),
            "zoom": _coerce_number(
                settings.get("zoom", _DEFAULT_SETTINGS["zoom"]), 0.4, 3.0
            ),
            "window_w": _coerce_number(
                settings.get("window_w", _DEFAULT_SETTINGS["window_w"]),
                200,
                20000,
                integer=True,
                default=_DEFAULT_SETTINGS["window_w"],
            ),
            "window_h": _coerce_number(
                settings.get("window_h", _DEFAULT_SETTINGS["window_h"]),
                200,
                20000,
                integer=True,
                default=_DEFAULT_SETTINGS["window_h"],
            ),
            "window_maximized": (
                "true"
                if settings.get("window_maximized", _DEFAULT_SETTINGS["window_maximized"])
                in (True, "true")
                else "false"
            ),
        }
        settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return


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


def print_backends_available() -> bool:
    """Whether GTK4 ships at least one print backend module.

    Recent GTK 4 releases (e.g. Arch's gtk4 1:4.22.4) no longer bundle the
    unix print backends, and nothing provides them separately -- without
    them WebKitPrintOperation quietly produces no file and no dialog. There
    is no public GTK API for enumerating backends, so this checks the
    well-known module directories. If a gtk-4.0 module tree exists at all,
    its verdict is trusted (a tree without printbackends/*.so means the
    backends are genuinely absent); only when no gtk-4.0 tree is found at
    all does this fall back to "available" -- buttons stay enabled, worst
    case is the old silent no-op.
    """
    import glob

    found_module_tree = False
    for libdir in ("/usr/lib", "/usr/lib64"):
        for version_dir in glob.glob(f"{libdir}/gtk-4.0/*"):
            found_module_tree = True
            if glob.glob(f"{version_dir}/printbackends/*.so"):
                return True
    return not found_module_tree


def render_body(
    text: str,
    *,
    enable_mermaid: bool,
    dark: bool,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
) -> tuple[str, list[dict]]:
    """Convert markdown text to sanitized HTML body content.

    Pure function -- no file I/O, no GTK -- so it's unit-testable directly.
    Returns (body, toc_tokens): the `toc` extension already computes a
    heading tree for anchor generation, so the TOC overlay reuses it instead
    of re-deriving it from the rendered HTML.

    body_font_id/code_font_id don't change the body HTML -- fonts are applied
    purely in CSS via data-font-* attributes on <html> (see build_document) --
    but they're accepted here so render() can forward the full setting set
    without the call sites needing to know which knobs affect which stage.
    """
    # Mermaid SVGs are pre-rendered with a light/dark palette baked in, so a
    # theme's darkness (not the system preference) decides the mmdc theme.
    theme_dark = is_theme_dark(theme_id, fallback=dark)
    text = _strip_frontmatter(text)
    mermaid_ext = MermaidExtension(enable_mermaid=enable_mermaid, dark=theme_dark)
    md = markdown.Markdown(
        extensions=[*EXTENSIONS, mermaid_ext],
        extension_configs=EXTENSION_CONFIGS,
    )
    body = md.convert(text)
    body = sanitize_html(body)
    body = mermaid_ext.resolve(body)
    return body, md.toc_tokens  # type: ignore[attr-defined]


def build_document(
    body: str,
    title: str,
    *,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
) -> str:
    """Wrap a sanitized HTML body in the full page shell (CSP, stylesheet)."""
    theme_id = _coerce_theme(theme_id)
    body_font_id = _coerce_font(body_font_id, kind="body")
    code_font_id = _coerce_font(code_font_id, kind="code")

    theme_attr = f' data-theme="{html.escape(theme_id)}"' if theme_id != "auto" else ""
    font_body_attr = f' data-font-body="{html.escape(body_font_id)}"'
    font_code_attr = f' data-font-code="{html.escape(code_font_id)}"'
    stylesheet = read_asset("style.css") + "\n" + read_asset("themes.css")

    return (
        "<!DOCTYPE html><html"
        f"{theme_attr}{font_body_attr}{font_code_attr}><head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{_CSP}\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{stylesheet}</style>"
        "</head><body><article class='markdown-body'>"
        f"{body}</article></body></html>"
    )


def render(
    path: Path,
    *,
    enable_mermaid: bool,
    dark: bool,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
) -> tuple[str, list[dict]]:
    """Read `path`, render and sanitize markdown, return (html_doc, toc_tokens)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        body = f"<h1>{_('Cannot read file')}</h1><pre>{html.escape(str(exc))}</pre>"
        toc_tokens: list[dict] = []
    else:
        body, toc_tokens = render_body(
            text,
            enable_mermaid=enable_mermaid,
            dark=dark,
            theme_id=theme_id,
            body_font_id=body_font_id,
            code_font_id=code_font_id,
        )

    return (
        build_document(
            body,
            path.name,
            theme_id=theme_id,
            body_font_id=body_font_id,
            code_font_id=code_font_id,
        ),
        toc_tokens,
    )


def flatten_toc(tokens: list[dict], depth: int = 0) -> list[tuple[int, str, str]]:
    """Flatten the `toc` extension's nested heading tree to (depth, id, name)."""
    flat: list[tuple[int, str, str]] = []
    for token in tokens:
        flat.append((depth, token["id"], token["name"]))
        flat.extend(flatten_toc(token.get("children", []), depth + 1))
    return flat


_MARKDOWN_SUFFIXES = {".md", ".markdown"}


def _a11y_label(widget: Gtk.Widget, label: str) -> None:
    """Icon-only buttons need an accessible name; tooltips alone are not
    reliably exposed to assistive technology."""
    widget.update_property([Gtk.AccessibleProperty.LABEL], [label])


def _theme_label(theme_id: str) -> str:
    mapping = {
        "auto": _("Auto (system)"),
        "github-light": _("GitHub Light"),
        "github-dark": _("GitHub Dark"),
        "catppuccin-latte": _("Catppuccin Latte"),
        "catppuccin-frappe": _("Catppuccin Frappé"),
        "catppuccin-macchiato": _("Catppuccin Macchiato"),
        "catppuccin-mocha": _("Catppuccin Mocha"),
        "solarized-light": _("Solarized Light"),
        "solarized-dark": _("Solarized Dark"),
        "gruvbox-light": _("Gruvbox Light"),
        "gruvbox-dark": _("Gruvbox Dark"),
        "nord": _("Nord"),
        "dracula": _("Dracula"),
        "rose-pine": _("Rosé Pine"),
        "rose-pine-dawn": _("Rosé Pine Dawn"),
        "tokyo-night": _("Tokyo Night"),
        "tokyo-night-day": _("Tokyo Night Day"),
    }
    return mapping.get(theme_id, theme_id)


def _font_label(font_id: str, *, is_code: bool) -> str:
    if is_code:
        mapping = {
            "system": _("System monospace"),
            "jetbrains-mono": _("JetBrains Mono"),
            "ia-writer": _("iA Writer Mono"),
            "fira-code": _("Fira Code"),
            "cascadia-code": _("Cascadia Code"),
        }
        return mapping.get(font_id, font_id)

    mapping = {
        "system": _("System"),
        "inter": _("Inter"),
        "atkinson": _("Atkinson Hyperlegible"),
        "ia-writer": _("iA Writer Quattro"),
        "noto-serif": _("Noto Serif"),
        "ibmplex-sans": _("IBM Plex Sans"),
    }
    return mapping.get(font_id, font_id)


class Viewer(Gtk.ApplicationWindow):
    def __init__(
        self,
        app: Gtk.Application,
        path: Path,
        *,
        enable_mermaid: bool,
        debug: bool,
        theme_id: str,
        body_font_id: str,
        code_font_id: str,
        settings_path: Path,
    ) -> None:
        super().__init__(application=app, title=path.name)
        self.set_default_size(900, 1000)

        # Show the name the user opened, but watch the real file: monitoring a
        # symlink itself never reports edits made to its target.
        self.display_name = path.name
        self.path = path.resolve()
        self.enable_mermaid = enable_mermaid

        self.theme_id = _coerce_theme(theme_id)
        self.body_font_id = _coerce_font(body_font_id, kind="body")
        self.code_font_id = _coerce_font(code_font_id, kind="code")
        self.settings_path = settings_path
        self._persisted = load_settings(path=settings_path)
        self.set_default_size(
            int(self._persisted["window_w"]), int(self._persisted["window_h"])
        )
        if self._persisted["window_maximized"] == "true":
            self.maximize()

        self.monitor: Gio.FileMonitor | None = None
        self._reload_source: int | None = None
        self._pending_restore_scroll = False
        self._scroll_to_restore = 0
        self._back_stack: list[Path] = []
        self._forward_stack: list[Path] = []

        # GTK preference is used for Mermaid defaults and to seed "Auto" theme.
        self.dark = Gtk.Settings.get_default().get_property(
            "gtk-application-prefer-dark-theme"
        )

        # Ephemeral session: no cookie jar, no HTTP cache persisted to disk.
        # decide-policy below is what actually stops any request from being
        # made in the first place for anything but the local document's tree.
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
        self.webview.connect("load-changed", self._on_load_changed)
        self.find_controller = self.webview.get_find_controller()

        # Restore persisted zoom, and follow system light/dark flips when in
        # "Auto" (the Mermaid palette bakes the theme in, so it needs a
        # re-render, not just a CSS flip).
        try:
            self.webview.set_zoom_level(float(self._persisted["zoom"]))
        except ValueError:
            pass
        Gtk.Settings.get_default().connect(
            "notify::gtk-application-prefer-dark-theme", self._on_system_theme_changed
        )
        self.connect("close-request", self._on_close_request)

        self.back_button = Gtk.Button(icon_name="go-previous-symbolic")
        self.back_button.set_tooltip_text(_("Back (Alt+Left)"))
        _a11y_label(self.back_button, _("Back"))
        self.back_button.connect("clicked", lambda _b: self.go_back())

        self.forward_button = Gtk.Button(icon_name="go-next-symbolic")
        self.forward_button.set_tooltip_text(_("Forward (Alt+Right)"))
        _a11y_label(self.forward_button, _("Forward"))
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
        _a11y_label(self.toc_button, _("Table of contents"))
        self.toc_button.set_popover(self.toc_popover)

        export_button = Gtk.Button(icon_name="document-save-symbolic")
        print_button = Gtk.Button(icon_name="document-print-symbolic")
        if print_backends_available():
            export_button.set_tooltip_text(_("Export PDF…"))
            print_button.set_tooltip_text(_("Print (Ctrl+P)"))
            _a11y_label(export_button, _("Export PDF"))
            _a11y_label(print_button, _("Print"))
        else:
            # GTK 4.22+ ships no print backends on some distros; the buttons
            # would silently no-op. Degrade visibly instead.
            reason = _("Unavailable: GTK4 print backends are missing on this system")
            for button in (export_button, print_button):
                button.set_sensitive(False)
                button.set_tooltip_text(reason)
        export_button.connect("clicked", lambda _b: self._export_pdf())
        print_button.connect("clicked", lambda _b: self._print_dialog())

        about_button = Gtk.Button(icon_name="help-about-symbolic")
        about_button.set_tooltip_text(_("About zeile"))
        _a11y_label(about_button, _("About zeile"))
        about_button.connect("clicked", lambda _b: self._show_about())

        self.theme_button = Gtk.MenuButton(icon_name="preferences-color-symbolic")
        self.theme_button.set_tooltip_text(_("Theme and fonts"))
        _a11y_label(self.theme_button, _("Theme and fonts"))
        self.theme_button.set_popover(self._build_theme_popover())

        self._title_label = Gtk.Label(label=self.display_name)
        header = Gtk.HeaderBar()
        header.set_title_widget(self._title_label)
        header.pack_start(self.back_button)
        header.pack_start(self.forward_button)

        reload_button = Gtk.Button(icon_name="view-refresh-symbolic")
        reload_button.set_tooltip_text(_("Reload (Ctrl+R)"))
        _a11y_label(reload_button, _("Reload"))
        reload_button.connect("clicked", lambda _b: self.reload())
        header.pack_start(reload_button)

        header.pack_start(self.toc_button)
        header.pack_start(self.theme_button)
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
        # Without these, the ScrolledWindow collapses to its natural
        # (minimum) size inside the Box below instead of filling it --
        # vexpand on the Box alone only affects the Box's own allocation
        # from its parent, not how the Box distributes space to its own
        # children. Confirmed by reproducing a fully black WebView with
        # this missing and fixing it by adding exactly these two lines.
        scroller.set_vexpand(True)
        scroller.set_hexpand(True)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.search_bar)
        box.append(scroller)
        self.set_child(box)

        self._add_shortcuts()
        self.reload()
        self._watch()

    def _build_theme_popover(self) -> Gtk.Popover:
        pop = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(8)
        box.set_margin_bottom(8)
        box.set_margin_start(8)
        box.set_margin_end(8)

        theme_title = Gtk.Label(label=_("Theme"), xalign=0)
        box.append(theme_title)

        theme_model = Gtk.StringList()
        self._theme_ids: list[str] = list(THEME_OPTIONS)
        for theme_id in self._theme_ids:
            theme_model.append(_theme_label(theme_id))

        self.theme_dropdown = Gtk.DropDown.new(model=theme_model)
        self.theme_dropdown.set_selected(self._theme_ids.index(self.theme_id))
        self.theme_dropdown.connect(
            "notify::selected",
            partial(self._on_theme_dropdown_changed, self._theme_ids),
        )
        box.append(self.theme_dropdown)

        body_font_title = Gtk.Label(label=_("Body font"), xalign=0)
        body_font_title.set_margin_top(8)
        box.append(body_font_title)

        body_font_model = Gtk.StringList()
        self._body_font_ids: list[str] = list(BODY_FONT_OPTIONS)
        for body_font_id in self._body_font_ids:
            body_font_model.append(_font_label(body_font_id, is_code=False))

        self.body_font_dropdown = Gtk.DropDown.new(model=body_font_model)
        self.body_font_dropdown.set_selected(self._body_font_ids.index(self.body_font_id))
        self.body_font_dropdown.connect(
            "notify::selected",
            partial(self._on_font_dropdown_changed, self._body_font_ids, "body"),
        )
        box.append(self.body_font_dropdown)

        code_font_title = Gtk.Label(label=_("Code font"), xalign=0)
        code_font_title.set_margin_top(8)
        box.append(code_font_title)

        code_font_model = Gtk.StringList()
        self._code_font_ids: list[str] = list(CODE_FONT_OPTIONS)
        for code_font_id in self._code_font_ids:
            code_font_model.append(_font_label(code_font_id, is_code=True))

        self.code_font_dropdown = Gtk.DropDown.new(model=code_font_model)
        self.code_font_dropdown.set_selected(self._code_font_ids.index(self.code_font_id))
        self.code_font_dropdown.connect(
            "notify::selected",
            partial(self._on_font_dropdown_changed, self._code_font_ids, "code"),
        )
        box.append(self.code_font_dropdown)

        pop.set_child(box)
        return pop

    def _persist_settings(self) -> None:
        # Merge into the freshly loaded state: only the three keys this
        # method owns may change -- the zoom/window keys must survive.
        current = load_settings(path=self.settings_path)
        current.update(
            {
                "theme": self.theme_id,
                "body_font": self.body_font_id,
                "code_font": self.code_font_id,
            }
        )
        save_settings(current, path=self.settings_path)

    def _on_close_request(self, *_args) -> bool:
        self._save_window_state()
        return False  # keep closing

    def _save_window_state(self) -> None:
        if self.get_width() <= 0:  # never mapped -- nothing to record
            return
        current = load_settings(path=self.settings_path)
        current.update(
            {
                "window_w": str(self.get_width()),
                "window_h": str(self.get_height()),
                "window_maximized": "true" if self.is_maximized() else "false",
                "zoom": str(round(self.webview.get_zoom_level(), 3)),
            }
        )
        save_settings(current, path=self.settings_path)

    def _on_system_theme_changed(self, *_args) -> None:
        # Only Auto tracks the system: explicit themes intentionally pin the
        # GTK preference themselves (which fires this same notify -- guard
        # prevents a reload loop).
        if self.theme_id == "auto":
            self.reload()

    def _apply_theme_and_font_attrs(self) -> None:
        # No `const`/`let` here: top-level lexical bindings persist across
        # evaluate_javascript() calls on the same page, so a second call
        # would die with "Identifier 'root' has already been declared" and
        # silently do nothing (found by the headless theme-matrix harness:
        # first switch worked, every later one was a no-op).
        root = "document.documentElement"
        js = (
            (
                f"{root}.setAttribute('data-theme', {json.dumps(self.theme_id)});"
                if self.theme_id != "auto"
                else f"{root}.removeAttribute('data-theme');"
            )
            + f"{root}.setAttribute('data-font-body', {json.dumps(self.body_font_id)});"
            + f"{root}.setAttribute('data-font-code', {json.dumps(self.code_font_id)});"
        )
        self.webview.evaluate_javascript(js, -1, None, None, None, None, None)

    def _on_theme_dropdown_changed(
        self, theme_ids: list[str], dropdown: Gtk.DropDown, *_pspec
    ) -> None:
        selected = dropdown.get_selected()
        if selected < 0:
            return
        self._set_theme(theme_ids[selected])

    def _on_font_dropdown_changed(
        self, font_ids: list[str], kind: str, dropdown: Gtk.DropDown, *_pspec
    ) -> None:
        selected = dropdown.get_selected()
        if selected < 0:
            return
        font_id = font_ids[selected]
        if kind == "body":
            self._set_body_font(font_id)
        else:
            self._set_code_font(font_id)

    def _set_theme(self, theme_id: str) -> None:
        theme_id = _coerce_theme(theme_id)
        if theme_id == self.theme_id:
            return

        prev_dark = is_theme_dark(self.theme_id, fallback=self.dark)
        self.theme_id = theme_id
        next_dark = is_theme_dark(self.theme_id, fallback=self.dark)

        if self.enable_mermaid and prev_dark != next_dark:
            # Mermaid SVGs bake the palette in at render time, so a
            # light<->dark flip needs a real re-render, not just a CSS flip.
            self.reload()  # also syncs the GTK chrome via _sync_theme_with_gtk
        else:
            self._apply_theme_and_font_attrs()
            self._sync_theme_with_gtk()

        self._persist_settings()

    def _set_body_font(self, body_font_id: str) -> None:
        body_font_id = _coerce_font(body_font_id, kind="body")
        if body_font_id == self.body_font_id:
            return
        self.body_font_id = body_font_id
        self._apply_theme_and_font_attrs()
        self._persist_settings()

    def _set_code_font(self, code_font_id: str) -> None:
        code_font_id = _coerce_font(code_font_id, kind="code")
        if code_font_id == self.code_font_id:
            return
        self.code_font_id = code_font_id
        self._apply_theme_and_font_attrs()
        self._persist_settings()

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
                    # Deferred: re-entering load_html synchronously from
                    # inside the policy callback is a documented-fragile
                    # WebKitGTK pattern (HANDOFF.md's "check this first").
                    GLib.idle_add(self.navigate_to, target)
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

    def _on_load_changed(self, _webview: WebKit.WebView, event: WebKit.LoadEvent) -> None:
        if event != WebKit.LoadEvent.FINISHED:
            return
        if self._pending_restore_scroll:
            self._pending_restore_scroll = False
            # Value embedded as a validated Python int -- no JS-side state,
            # clamped to the new document height (it may have shrunk).
            y = max(0, self._scroll_to_restore)
            self.webview.evaluate_javascript(
                f"window.scrollTo(0, Math.min({y}, "
                "Math.max(0, document.documentElement.scrollHeight "
                "- window.innerHeight)));",
                -1,
                None,
                None,
                None,
                None,
                None,
            )

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

    def _sync_theme_with_gtk(self) -> None:
        if self.theme_id == "auto":
            return
        Gtk.Settings.get_default().set_property(
            "gtk-application-prefer-dark-theme",
            is_theme_dark(self.theme_id, fallback=False),
        )

    def reload(self) -> bool:
        """Re-render the file, preserving the current scroll position.

        The offset is read back into Python BEFORE the new document is
        loaded: a fresh document gets a fresh JS global object, so a value
        stashed on `window` (the old `__zeileScroll` approach) is gone by
        the time the restore runs -- and reading it asynchronously means
        the actual load_html must wait for that callback, not race it.
        """

        def _got_scroll(src: WebKit.WebView, result: Gio.AsyncResult, _u) -> None:
            try:
                raw = src.evaluate_javascript_finish(result).to_string() or "0"
                self._scroll_to_restore = int(float(raw))
            except Exception:
                self._scroll_to_restore = 0
            # Re-read the desktop dark preference on every render: for the
            # "Auto" theme it decides the Mermaid palette, and the system
            # preference can flip mid-session. Explicit themes override it
            # via is_theme_dark.
            self.dark = Gtk.Settings.get_default().get_property(
                "gtk-application-prefer-dark-theme"
            )
            html_doc, toc_tokens = render(
                self.path,
                enable_mermaid=self.enable_mermaid,
                dark=self.dark,
                theme_id=self.theme_id,
                body_font_id=self.body_font_id,
                code_font_id=self.code_font_id,
            )
            self._toc_flat = flatten_toc(toc_tokens)
            self._pending_restore_scroll = True
            self.webview.load_html(html_doc, self.path.as_uri())
            self._sync_theme_with_gtk()

        self.webview.evaluate_javascript(
            "window.scrollY | 0", -1, None, None, None, _got_scroll, None
        )
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
        assert self.monitor is not None
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
    def __init__(
        self,
        path: Path | None,
        *,
        enable_mermaid: bool,
        debug: bool,
        settings: dict[str, str],
        settings_path: Path,
    ) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path
        self.enable_mermaid = enable_mermaid
        self.debug = debug
        self.settings = settings
        self.settings_path = settings_path

    def do_activate(self) -> None:
        if self.path is None:
            # Launched without a file (app menu / launcher with no %f):
            # offer a picker instead of erroring out. Cancel = quit.
            dialog = Gtk.FileDialog()
            dialog.set_title(_("Open markdown file"))

            def chosen(d: Gtk.FileDialog, result: Gio.AsyncResult) -> None:
                try:
                    gfile = d.open_finish(result)
                except GLib.Error:
                    self.quit()  # user cancelled
                    return
                self._present_path(Path(gfile.get_path()))

            dialog.open(None, None, chosen)
            return
        self._present_path(self.path)

    def _present_path(self, path: Path) -> None:
        Viewer(
            self,
            path,
            enable_mermaid=self.enable_mermaid,
            debug=self.debug,
            theme_id=self.settings["theme"],
            body_font_id=self.settings["body_font"],
            code_font_id=self.settings["code_font"],
            settings_path=self.settings_path,
        ).present()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal GTK4 markdown viewer.")
    parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        default=None,
        help="markdown file to display (omit to pick one in a dialog)",
    )
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
    parser.add_argument(
        "--theme",
        choices=THEME_OPTIONS,
        default=None,
        help="start with a theme (saved selection is used otherwise)",
    )
    parser.add_argument(
        "--body-font",
        choices=BODY_FONT_OPTIONS,
        default=None,
        help="body font selection (saved selection is used otherwise)",
    )
    parser.add_argument(
        "--code-font",
        choices=CODE_FONT_OPTIONS,
        default=None,
        help="monospace/code font selection (saved selection is used otherwise)",
    )

    args = parser.parse_args()

    if args.file is not None and not args.file.exists():
        print(f"zeile: no such file: {args.file}", file=sys.stderr)
        return 1

    debug = args.debug or bool(os.environ.get("ZEILE_DEBUG"))
    settings = load_settings()
    if args.theme is not None:
        settings["theme"] = _coerce_theme(args.theme)
    if args.body_font is not None:
        settings["body_font"] = _coerce_font(args.body_font, kind="body")
    if args.code_font is not None:
        settings["code_font"] = _coerce_font(args.code_font, kind="code")
    save_settings(settings)

    settings_path = _default_settings_path()
    return ZeileApp(
        args.file,
        enable_mermaid=args.enable_mermaid,
        debug=debug,
        settings=settings,
        settings_path=settings_path,
    ).run([])


if __name__ == "__main__":
    sys.exit(main())
