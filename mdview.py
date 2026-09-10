#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""A small, fast GTK4 markdown viewer.

Renders a markdown file with python-markdown into a WebKitGTK view and
reloads it whenever the file changes on disk. Symlinks are resolved so
that watching a link follows its target.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

import markdown  # noqa: E402
from gi.repository import Gio, GLib, Gtk, WebKit  # noqa: E402

APP_ID = "com.erdlabs.mdview"
MERMAID_FENCE = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.S | re.M)

EXTENSIONS = [
    "extra",           # tables, fenced_code, footnotes, def_list, abbr, attr_list
    "admonition",
    "codehilite",
    "sane_lists",
    "smarty",
    "toc",
]

EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False, "noclasses": False},
    "toc": {"permalink": False},
}


def read_asset(name: str) -> str:
    """Return the contents of an asset shipped next to this script."""
    return (Path(__file__).resolve().parent / "assets" / name).read_text(encoding="utf-8")


def extract_mermaid(text: str) -> tuple[str, list[str]]:
    """Pull ```mermaid fences out of the source before markdown sees them.

    codehilite has no pygments lexer for "mermaid", so it silently drops the
    language tag on fallback and the rendered HTML has no way to tell a
    mermaid block apart from any other unhighlighted code block. Extracting
    the diagram source first and re-inserting it after conversion sidesteps
    that entirely.
    """
    diagrams: list[str] = []

    def stash(match: re.Match[str]) -> str:
        diagrams.append(match.group(1))
        return f"\n\nMDVIEW-MERMAID-{len(diagrams) - 1}\n\n"

    return MERMAID_FENCE.sub(stash, text), diagrams


def render(path: Path) -> str:
    """Convert a markdown file to a full HTML document."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        body = f"<h1>Cannot read file</h1><pre>{html.escape(str(exc))}</pre>"
        diagrams: list[str] = []
    else:
        text, diagrams = extract_mermaid(text)
        md = markdown.Markdown(
            extensions=EXTENSIONS,
            extension_configs=EXTENSION_CONFIGS,
        )
        body = md.convert(text)
        for i, source in enumerate(diagrams):
            body = body.replace(
                f"<p>MDVIEW-MERMAID-{i}</p>",
                f"<pre class='mermaid'>{html.escape(source)}</pre>",
            )

    mermaid_js = (
        f"<script>{read_asset('mermaid.min.js')}</script>"
        "<script>mermaid.initialize({startOnLoad: true, "
        "theme: window.matchMedia('(prefers-color-scheme: dark)').matches "
        "? 'dark' : 'default'});</script>"
        if diagrams
        else ""
    )

    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{html.escape(path.name)}</title>"
        f"<style>{read_asset('style.css')}</style>"
        f"</head><body><article class='markdown-body'>{body}</article>{mermaid_js}"
        "</body></html>"
    )


class Viewer(Gtk.ApplicationWindow):
    def __init__(self, app: Gtk.Application, path: Path) -> None:
        super().__init__(application=app, title=path.name)
        self.set_default_size(900, 1000)

        # Show the name the user opened, but watch the real file: monitoring a
        # symlink itself never reports edits made to its target.
        self.display_name = path.name
        self.path = path.resolve()
        self.monitor: Gio.FileMonitor | None = None
        self._reload_source: int | None = None

        self.webview = WebKit.WebView()
        settings = self.webview.get_settings()
        settings.set_enable_developer_extras(True)

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
            "window.__mdviewScroll = window.scrollY;", -1, None, None, None, None, None
        )
        self.webview.load_html(render(self.path), self.path.as_uri())
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


class MdviewApp(Gtk.Application):
    def __init__(self, path: Path) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.path = path

    def do_activate(self) -> None:
        Viewer(self, self.path).present()


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal GTK4 markdown viewer.")
    parser.add_argument("file", type=Path, help="markdown file to display")
    args = parser.parse_args()

    if not args.file.exists():
        print(f"mdview: no such file: {args.file}", file=sys.stderr)
        return 1

    return MdviewApp(args.file).run([])


if __name__ == "__main__":
    sys.exit(main())
