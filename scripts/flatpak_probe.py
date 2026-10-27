#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Flatpak sandbox probe: readonly home, no network, sibling image renders.

Runs inside `flatpak run` under headless cage (see scripts/flatpak-check.sh).
argv: doc_dir port
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
from pathlib import Path

APP_DIR = os.environ.get("ZEILE_APP_DIR", "/app/share/zeile")
sys.path.insert(0, APP_DIR)

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import GLib, WebKit  # noqa: E402

import zeile  # noqa: E402
from zeile import ZeileApp  # noqa: E402

LOAD_TIMEOUT_SECONDS = 30
HEADING = "Flatpak heading"


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


def check_readonly(doc_dir: Path) -> None:
    target = doc_dir / "probe-write-test"
    try:
        target.write_text("should fail", encoding="utf-8")
    except OSError:
        print("readonly OK")
        return
    fail(f"expected write failure in read-only home, but wrote {target}")


def check_network(port: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=2):
            pass
    except OSError:
        print("network isolated OK")
        return
    fail(f"expected connection to 127.0.0.1:{port} to fail")


def fail_state(state: dict[str, object], message: str) -> None:
    if state["done"]:
        return
    state["done"] = True
    state["ok"] = False
    state["detail"] = message
    print(f"flatpak probe FAILED: {message}", file=sys.stderr)
    state["app"].quit()


def probe(state: dict[str, object]) -> bool:
    def issued(_src: WebKit.WebView, result, _user_data) -> None:
        if state["done"]:
            return GLib.SOURCE_REMOVE
        try:
            raw = state["webview"].evaluate_javascript_finish(result).to_string() or ""
        except Exception as exc:  # noqa: BLE001
            fail_state(state, f"probe JS failed: {exc}")
            return GLib.SOURCE_REMOVE
        try:
            h1, img_ok = json.loads(raw)
        except (ValueError, TypeError):
            fail_state(state, f"unexpected probe result: {raw!r}")
            return GLib.SOURCE_REMOVE
        got_h1 = str(h1).rstrip("#").strip()
        problems = []
        if got_h1 != HEADING:
            problems.append(f"h1 text {h1!r} != {HEADING!r}")
        if not img_ok:
            problems.append("sibling image not loaded")
        if problems:
            fail_state(state, "; ".join(problems))
        else:
            state["done"] = True
            state["ok"] = True
            print("sibling image OK")
            state["app"].quit()
        return GLib.SOURCE_REMOVE

    js = (
        "(function(){"
        "var h=document.querySelector('h1');"
        "var img=document.querySelector('img');"
        "return JSON.stringify(["
        "h?h.textContent:'',"
        "!!(img&&img.complete&&img.naturalWidth>0)]);"
        "})();"
    )
    state["webview"].evaluate_javascript(js, -1, None, None, None, issued, None)
    return GLib.SOURCE_REMOVE


def run_viewer(md: Path) -> bool:
    state: dict[str, object] = {"done": False, "ok": False}
    with tempfile.TemporaryDirectory(prefix="zeile-flatpak-probe-") as td:
        tmp = Path(td)
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
                fail_state(
                    state, f"no load-changed FINISHED within {LOAD_TIMEOUT_SECONDS} s"
                )
                return GLib.SOURCE_REMOVE

            GLib.timeout_add_seconds(LOAD_TIMEOUT_SECONDS, give_up)

            def on_load(_webview, event) -> None:
                if event != WebKit.LoadEvent.FINISHED or state["done"]:
                    return
                GLib.timeout_add(300, lambda: probe(state))
                return GLib.SOURCE_REMOVE

            win.webview.connect("load-changed", on_load)

        app.connect("activate", on_activate)
        try:
            app.run([])
        finally:
            app.quit()
    return bool(state["ok"])


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        fail("usage: flatpak_probe.py DOC_DIR PORT")
    doc_dir = Path(argv[1])
    try:
        port = int(argv[2])
    except ValueError:
        fail(f"invalid port: {argv[2]!r}")

    check_readonly(doc_dir)
    check_network(port)

    md = doc_dir / "doc.md"
    if not md.is_file():
        fail(f"missing document: {md}")
    if not run_viewer(md):
        return 1
    print("flatpak probe OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
