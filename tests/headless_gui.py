#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Headless GUI verification matrix for zeile.

Run inside a headless wlroots compositor (see tests/test_headless_gui.py for
the wrapper):

    WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 cage -d python3 tests/headless_gui.py

Exercises the real GTK/WebKit widget stack -- widget state, computed page
styles and persistence -- without needing a visible window, and never
touches the operator's desktop focus. Prints one PASS/FAIL line per check
and exits 0 only if all pass.

Deliberately NOT included in plain `pytest`: this needs cage + a Wayland
session. The pytest wrapper skips when either is absent.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import GLib, Gtk  # noqa: E402

import zeile  # noqa: E402
from zeile import ZeileApp, load_settings, print_backends_available  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    results.append((tag, ok, detail))


def walk_buttons(widget) -> list[Gtk.Button]:
    found: list[Gtk.Button] = []
    if isinstance(widget, Gtk.Button):
        found.append(widget)
    child = widget.get_first_child()
    while child is not None:
        found.extend(walk_buttons(child))
        child = child.get_next_sibling()
    return found


def run() -> None:
    with tempfile.TemporaryDirectory(prefix="zeile-headless-") as td:
        tmp = Path(td)
        md = tmp / "doc.md"
        md.write_text(
            "# Headless\n\n```python\ndef f(x):\n    return x  # hi\n```\n",
            encoding="utf-8",
        )
        settings_path = tmp / "settings.json"
        settings_path.write_text(
            '{"theme": "nord", "zoom": 1.5, "window_w": 1100, "window_h": 800,'
            ' "window_maximized": false}',
            encoding="utf-8",
        )

        app = ZeileApp(
            md,
            enable_mermaid=False,
            debug=False,
            settings={"theme": "auto", "body_font": "system", "code_font": "system"},
            settings_path=settings_path,
        )

        def on_activate(a) -> None:
            win = zeile.Viewer(
                a,
                md,
                enable_mermaid=False,
                debug=False,
                theme_id="nord",
                body_font_id="ia-writer",
                code_font_id="jetbrains-mono",
                settings_path=settings_path,
            )
            win.present()

            def inspect() -> bool:
                # 1. persisted zoom/window restored from settings.json
                check(
                    "zoom-restored",
                    abs(win.webview.get_zoom_level() - 1.5) < 0.01,
                    f"zoom={win.webview.get_zoom_level()}",
                )

                # 2. print/PDF buttons degrade when GTK4 backends are absent
                degraded = [
                    b
                    for b in walk_buttons(win.get_titlebar())
                    if "print backends are missing" in (b.get_tooltip_text() or "")
                ]
                if print_backends_available():
                    check("print-buttons", True, "backends present, buttons active")
                else:
                    check(
                        "print-buttons-degraded",
                        len(degraded) == 2 and not any(b.get_sensitive() for b in degraded),
                        f"{len(degraded)} degraded buttons",
                    )

                # 3. live theme switch updates the computed syntax colour
                def style_cb(src, res, _u):
                    try:
                        colour = src.evaluate_javascript_finish(res).to_string()
                        # We switched nord -> github-light, so the keyword
                        # token must now carry GitHub-Light's #cf222e.
                        ok = colour.strip() == "rgb(207, 34, 46)"
                        check("live-theme-switch", ok, f".k colour after switch: {colour}")
                    except Exception as exc:  # noqa: BLE001
                        check("live-theme-switch", False, str(exc))
                    finish()

                win._set_theme("github-light")  # first switch after load
                win.webview.evaluate_javascript(
                    "getComputedStyle(document.querySelector('.codehilite .k')).color",
                    -1,
                    None,
                    None,
                    None,
                    style_cb,
                    None,
                )

                def finish() -> None:
                    # 4. window-state saver + merge guard (headless: width 0
                    # means "never mapped" -> the saver must not overwrite)
                    win._save_window_state()
                    saved = load_settings(path=settings_path)
                    check(
                        "settings-merge",
                        saved["theme"] == "github-light" and saved["zoom"] == "1.5",
                        f"theme={saved['theme']} zoom={saved['zoom']} "
                        f"w={saved['window_w']}",
                    )
                    a.quit()
                    return GLib.SOURCE_REMOVE

                return GLib.SOURCE_REMOVE

            GLib.timeout_add(2500, inspect)

        app.connect("activate", on_activate)
        app.run([])


def main() -> int:
    run()
    for tag, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'} {tag}  {detail}")
    failed = [r for r in results if not r[1]]
    print(f"==== {len(results) - len(failed)}/{len(results)} passed ====")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
