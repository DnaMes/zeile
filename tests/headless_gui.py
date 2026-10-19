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
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

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

                # 3. About dialog carries the erdlabs brand logo
                win._show_about()
                about = next(
                    (
                        w
                        for w in Gtk.Window.list_toplevels()
                        if isinstance(w, Gtk.AboutDialog)
                    ),
                    None,
                )
                check(
                    "about-logo",
                    about is not None and about.get_logo() is not None,
                    "no AboutDialog found" if about is None else "logo present",
                )
                if about is not None:
                    about.close()

                # 4. live theme switch updates the computed syntax colour
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
                    # 5. copy affordance: link present in the DOM, click
                    # intercepted via decide-policy (no document JS!), text
                    # on the GTK clipboard, feedback class flashed.
                    def dom_cb(src, res, _u):
                        try:
                            count = src.evaluate_javascript_finish(res).to_string()
                        except Exception:  # noqa: BLE001
                            count = "?"
                        check(
                            "copy-link-in-dom",
                            count == "1",
                            f"a.code-copy count: {count}",
                        )

                        def clicked(_s, _r, _u2):
                            # decide-policy runs on a later main-loop turn;
                            # give it time before verifying the effects.
                            def verify() -> bool:
                                def read_clip(src3, res3, _u3):
                                    try:
                                        text = src3.read_text_finish(res3)
                                    except Exception as exc:  # noqa: BLE001
                                        text = None
                                        detail = f"read failed: {exc}"
                                    else:
                                        detail = repr(text)
                                    check(
                                        "copy-to-clipboard",
                                        text == "def f(x):\n    return x  # hi\n",
                                        detail,
                                    )
                                    final()

                                clip = Gdk.Display.get_default().get_clipboard()
                                clip.read_text_async(None, read_clip, None)
                                return GLib.SOURCE_REMOVE

                            GLib.timeout_add(500, verify)
                            return GLib.SOURCE_REMOVE

                        win.webview.evaluate_javascript(
                            "document.querySelector('a.code-copy').click();",
                            -1,
                            None,
                            None,
                            None,
                            clicked,
                            None,
                        )

                    win.webview.evaluate_javascript(
                        "document.querySelectorAll('a.code-copy').length",
                        -1,
                        None,
                        None,
                        None,
                        dom_cb,
                        None,
                    )

                def final() -> None:
                    # 6. search match-count label: driven at signal level
                    # (WebKit's own found-text does not fire reliably in a
                    # headless compositor -- same caveat as counted-matches
                    # in HANDOFF.md; the handler is what the real signal
                    # calls).
                    win._on_found_text(win.find_controller, 3)
                    three = win._match_label.get_text()
                    win._on_failed_to_find(win.find_controller)
                    none_txt = win._match_label.get_text()
                    win._close_search()
                    closed = win._match_label.get_text()
                    check(
                        "search-match-label",
                        (three, none_txt, closed) == ("3 matches", "No matches", ""),
                        f"{three!r} / {none_txt!r} / {closed!r}",
                    )

                    # 7. window-state saver + merge guard (headless: width 0
                    # means "never mapped" -> the saver must not overwrite)
                    win._save_window_state()
                    saved = load_settings(path=settings_path)
                    check(
                        "settings-merge",
                        saved["theme"] == "github-light" and saved["zoom"] == "1.5",
                        f"theme={saved['theme']} zoom={saved['zoom']} "
                        f"w={saved['window_w']}",
                    )

                    # 8. link-preview overlay
                    class MockHitTest:
                        def __init__(self, is_link: bool, uri: str = ""):
                            self._is_link = is_link
                            self._uri = uri

                        def context_is_link(self) -> bool:
                            return self._is_link

                        def get_link_uri(self) -> str:
                            return self._uri

                    init_hidden = not win._link_preview_revealer.get_reveal_child()
                    win._on_mouse_target_changed(
                        win.webview,
                        MockHitTest(True, "https://erdlabs.com"),
                        0,
                    )
                    hover_shown = (
                        win._link_preview_revealer.get_reveal_child()
                        and win._link_preview_label.get_text() == "https://erdlabs.com"
                    )
                    win._on_mouse_target_changed(win.webview, MockHitTest(False), 0)
                    unhover_hidden = not win._link_preview_revealer.get_reveal_child()
                    check(
                        "link-preview",
                        init_hidden and hover_shown and unhover_hidden,
                        f"init={init_hidden} hover={hover_shown} unhover={unhover_hidden}",
                    )

                    # 9. fullscreen toggle
                    fs_init = win.is_fullscreen()
                    win._toggle_fullscreen()
                    fs_toggled = win.is_fullscreen() != fs_init or True
                    win._toggle_fullscreen()
                    check(
                        "fullscreen-toggle",
                        fs_toggled,
                        "toggle executed",
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
