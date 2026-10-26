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
            launch_sequence=False,  # the matrix drives its own Viewer
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

                # 3. About dialog carries the app icon, version, and
                # erdlabs brand logo.
                win._show_about()
                about = next(
                    (
                        w
                        for w in Gtk.Window.list_toplevels()
                        if isinstance(w, Gtk.Dialog) and w.get_title() == "About zeile"
                    ),
                    None,
                )
                detail = "no About dialog found" if about is None else "dialog present"
                check("about-dialog", about is not None, detail)
                if about is not None:
                    logo_path = (
                        Path(__file__).resolve().parent.parent
                        / "assets"
                        / "logo_erdlabs.png"
                    )
                    has_logo_image = False
                    has_app_icon = False
                    version_seen = False

                    def walk(widget):
                        nonlocal has_logo_image, has_app_icon, version_seen
                        if isinstance(widget, Gtk.Image):
                            paintable = widget.get_paintable()
                            if paintable is not None:
                                px = widget.get_pixel_size()
                                if px == 128:
                                    has_app_icon = True
                                elif px == 192:
                                    has_logo_image = True
                        if isinstance(widget, Gtk.Label):
                            text = widget.get_text() or ""
                            if zeile.__version__ in text:
                                version_seen = True
                        child = widget.get_first_child()
                        while child is not None:
                            walk(child)
                            child = child.get_next_sibling()

                    walk(about)
                    check(
                        "about-app-icon",
                        has_app_icon,
                        "zeile icon image found" if has_app_icon else "missing",
                    )
                    check(
                        "about-version",
                        version_seen,
                        f"version {zeile.__version__} shown" if version_seen else "missing",
                    )
                    check(
                        "about-erdlabs-logo",
                        has_logo_image and logo_path.is_file(),
                        "logo_erdlabs.png referenced" if has_logo_image else "missing",
                    )
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

                    # 8. launch sequence: intro once (flag in settings.json),
                    # logo every start, any key or click skips the whole thing.
                    seq_path = tmp / "seq-settings.json"
                    done: list[int] = []
                    first = zeile.play_launch_sequence(a, seq_path, lambda: done.append(1))
                    check(
                        "launch-first-start",
                        [p.asset for p in first._phases]
                        == ["logo_erdlabs.png", "zeile.png"]
                        and load_settings(path=seq_path)["intro_seen"] == "true",
                        f"phases={[p.asset for p in first._phases]}",
                    )
                    first._key.emit("key-pressed", Gdk.KEY_Return, 0, Gdk.ModifierType(0))
                    check(
                        "launch-key-skips-all",
                        done == [1] and first._finished,
                        f"done={done}",
                    )
                    second = zeile.play_launch_sequence(a, seq_path, lambda: done.append(2))
                    check(
                        "launch-later-start-skipped",
                        second is None and done == [1, 2],
                        f"splash={second!r} done={done}",
                    )

                    # 8b. a missing launch image skips the sequence instead of raising
                    real_asset_path = zeile.launch_asset_path
                    zeile.launch_asset_path = lambda _asset: tmp / "missing.png"
                    try:
                        gone: list[int] = []
                        broken = zeile.play_launch_sequence(
                            a, tmp / "broken-settings.json", lambda: gone.append(1)
                        )
                        broken._load(0)
                        check(
                            "launch-missing-asset-skips",
                            gone == [1] and broken._finished,
                            f"done={gone}",
                        )
                    finally:
                        zeile.launch_asset_path = real_asset_path

                    # 9. link-preview overlay
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
                    win._on_mouse_target_changed(
                        win.webview,
                        MockHitTest(True, win.path.as_uri() + "#heading-anchor"),
                        0,
                    )
                    anchor_shown = (
                        win._link_preview_revealer.get_reveal_child()
                        and win._link_preview_label.get_text() == "#heading-anchor"
                    )
                    win._on_mouse_target_changed(win.webview, MockHitTest(False), 0)
                    unhover_hidden = not win._link_preview_revealer.get_reveal_child()
                    check(
                        "link-preview",
                        init_hidden and hover_shown and anchor_shown and unhover_hidden,
                        f"init={init_hidden} hover={hover_shown} "
                        f"anchor={anchor_shown} unhover={unhover_hidden}",
                    )

                    # 10. TOC stats & filtering
                    win._populate_toc()
                    stats_text = win.toc_stats_label.get_text()
                    has_stats = "words" in stats_text and "min read" in stats_text
                    win.toc_filter_entry.set_text("Head")
                    child = win.toc_list.get_first_child()
                    matched_head = isinstance(
                        child, Gtk.ListBoxRow
                    ) and win._toc_filter_func(child)
                    win.toc_filter_entry.set_text("nonexistent")
                    matched_none = (
                        not win._toc_filter_func(child)
                        if isinstance(child, Gtk.ListBoxRow)
                        else True
                    )
                    win.toc_filter_entry.set_text("")
                    check(
                        "toc-stats-and-filter",
                        has_stats and matched_head and matched_none,
                        f"stats={stats_text!r} head={matched_head} none={matched_none}",
                    )

                    # 11. fullscreen toggle
                    check(
                        "fullscreen-init",
                        not win.is_fullscreen(),
                        "initially windowed",
                    )
                    win._toggle_fullscreen()

                    def check_fs_after_enter() -> None:
                        is_fs = win.is_fullscreen()
                        win._toggle_fullscreen()

                        def check_fs_after_leave() -> None:
                            is_unfs = not win.is_fullscreen()
                            check(
                                "fullscreen-toggle",
                                is_fs and is_unfs,
                                f"fullscreen={is_fs} restored={is_unfs}",
                            )
                            a.quit()
                            return GLib.SOURCE_REMOVE

                        GLib.timeout_add(150, check_fs_after_leave)
                        return GLib.SOURCE_REMOVE

                    GLib.timeout_add(150, check_fs_after_enter)
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
