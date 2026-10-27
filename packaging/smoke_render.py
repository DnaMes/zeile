#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Package smoke test: prove the installed viewer actually renders a document.

The existing smoke test only proves the process survives 20 s; a blank or
broken view would pass. This script builds the real app + Viewer for a small
markdown fixture, waits (bounded) for the WebKit load to finish, then queries
the live DOM through evaluate_javascript and asserts the rendered content:

  - the <h1> reads exactly "Smoke heading"
  - a `pre code` element exists and contains the code-block text
  - a `table` element exists

Prints "render OK" and exits 0 on success; exits 1 with the failing
assertion on stderr otherwise. Needs a headless wlroots compositor (see
packaging/smoke.sh). Deliberately not in plain pytest: needs a Wayland cage.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# The INSTALLED app; the repo checkout stands in via ZEILE_APP_DIR for tests.
APP_DIR = os.environ.get("ZEILE_APP_DIR", "/usr/share/zeile")
sys.path.insert(0, APP_DIR)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import GLib, WebKit  # noqa: E402

import zeile  # noqa: E402
from zeile import ZeileApp  # noqa: E402

LOAD_TIMEOUT_SECONDS = 30

DOCUMENT = (
    "# Smoke heading\n\n"
    '```python\nprint("smoke payload")\n```\n\n'
    "| A | B |\n"
    "| --- | --- |\n"
    "| 1 | 2 |\n"
)


def fail(state: dict[str, object], message: str) -> None:
    """Record the failure (once), print it, and make sure the app quits."""
    if state["done"]:
        return
    state["done"] = True
    state["ok"] = False
    state["detail"] = message
    print(f"smoke render FAILED: {message}", file=sys.stderr)
    state["app"].quit()


def probe(state: dict[str, object]) -> bool:
    """Ask the live page for h1/code/table state and assert on the answer."""

    def issued(_src: WebKit.WebView, result, _user_data) -> None:
        if state["done"]:
            return GLib.SOURCE_REMOVE
        try:
            raw = state["webview"].evaluate_javascript_finish(result).to_string() or ""
        except Exception as exc:  # noqa: BLE001
            fail(state, f"probe JS failed: {exc}")
            return GLib.SOURCE_REMOVE
        try:
            h1, code, table = json.loads(raw)
        except (ValueError, TypeError):
            fail(state, f"unexpected probe result: {raw!r}")
            return GLib.SOURCE_REMOVE
        # The h1 carries a rendered heading-anchor ('Smoke heading#').
        got_h1 = str(h1).rstrip("#").strip()
        problems = []
        if got_h1 != "Smoke heading":
            problems.append(f"h1 text {h1!r} != 'Smoke heading'")
        if not code or "smoke payload" not in code:
            problems.append(f"pre code missing or wrong: {code!r}")
        if not table:
            problems.append("no <table> element")
        if problems:
            fail(state, "; ".join(problems))
        else:
            state["done"] = True
            state["ok"] = True
            state["app"].quit()
        return GLib.SOURCE_REMOVE

    # IIFE (evaluate_javascript gets a program, not a function body); JSON so
    # the boundary cannot smuggle quotes or backslashes into the parse.
    js = (
        "(function(){"
        "var h=document.querySelector('h1');"
        "var c=document.querySelector('pre code');"
        "return JSON.stringify(["
        "h?h.textContent:'',c?c.textContent:'',!!document.querySelector('table')]);"
        "})();"
    )
    state["webview"].evaluate_javascript(js, -1, None, None, None, issued, None)
    return GLib.SOURCE_REMOVE


def main() -> int:
    state: dict[str, object] = {"done": False, "ok": False}
    with tempfile.TemporaryDirectory(prefix="zeile-smoke-render-") as td:
        tmp = Path(td)
        md = tmp / "smoke.md"
        md.write_text(DOCUMENT, encoding="utf-8")

        app = ZeileApp(
            md,
            enable_mermaid=False,
            debug=False,
            settings={"theme": "auto", "body_font": "system", "code_font": "system"},
            settings_path=tmp / "settings.json",
            launch_sequence=False,
        )
        state["app"] = app

        def on_activate(a) -> None:
            # Same construction pattern as tests/headless_gui.py; the app's
            # own _open_initial also presents the doc, that window is inert.
            win = zeile.Viewer(
                a,
                md,
                enable_mermaid=False,
                debug=False,
                theme_id="nord",
                body_font_id="ia-writer",
                code_font_id="jetbrains-mono",
                settings_path=tmp / "settings.json",
            )
            win.present()
            state["webview"] = win.webview

            def give_up() -> bool:
                fail(state, f"no load-changed FINISHED within {LOAD_TIMEOUT_SECONDS} s")
                return GLib.SOURCE_REMOVE

            GLib.timeout_add_seconds(LOAD_TIMEOUT_SECONDS, give_up)

            def on_load(_webview, event) -> None:
                if event != WebKit.LoadEvent.FINISHED or state["done"]:
                    return
                # Small grace period: FINISHED can arrive before the render
                # settles, and re-renders fire FINISHED again.
                GLib.timeout_add(300, lambda: probe(state))
                return GLib.SOURCE_REMOVE

            # Connected before present(): FINISHED can arrive in an early
            # main-loop turn.
            win.webview.connect("load-changed", on_load)

        app.connect("activate", on_activate)
        try:
            app.run([])
        finally:
            app.quit()  # never leave the process hanging on any exit path

    ok = bool(state["ok"])
    if ok:
        print("render OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
