#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Headless GUI verification matrix for zeile.

Run inside a headless wlroots compositor (see tests/test_headless_gui.py for
the wrapper):

    WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 cage -d python3 tests/headless_gui.py

Exercises the real GTK/WebKit widget stack -- widget state, computed page
styles and persistence -- without needing a visible window, and never
touches the operator's desktop focus. The final check builds a Viewer from a
deliberately hostile document (raw <script>/<svg onload>/<a href=javascript:>
... aimed at a live local TCP listener) and proves the WebView contains it:
no script execution, no dangerous markup in the DOM, zero listener
connections. Prints one PASS/FAIL line per check and exits 0 only if all
pass.

Deliberately NOT included in plain `pytest`: this needs cage + a Wayland
session. The pytest wrapper skips when either is absent.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import gi  # noqa: E402

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("WebKit", "6.0")

from gi.repository import Gdk, GLib, Gtk, WebKit  # noqa: E402

import zeile  # noqa: E402
from zeile import ZeileApp, load_settings, print_backends_available  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    results.append((tag, ok, detail))


class PwnListener:
    """Tiny TCP listener on 127.0.0.1 that only counts accepted connections.

    Network oracle for the hostile-document check: if the WebView so much
    as dials this port, count stops being 0 and the check fails.
    """

    def __init__(self) -> None:
        self.count = 0
        self._lock = threading.Lock()
        self.port = 0
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(1.0)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(8)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(
            target=self._serve, name="zeile-pwn-listener", daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        assert self._sock is not None
        while self._sock is not None:
            try:
                conn, _addr = self._sock.accept()
            except TimeoutError:
                continue  # listener stops via .stop() -- keep waiting
            except OSError:
                return  # socket closed -- listener stopping
            conn.close()
            with self._lock:
                self.count += 1

    def settled_count(self) -> int:
        """Connections seen so far, after letting a just-accepted one be counted."""
        time.sleep(0.3)  # accept() returns at once for a pending connection
        with self._lock:
            return self.count

    def stop(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            sock.close()


def evaluated(webview: WebKit.WebView, js: str, callback: Callable[..., None]) -> None:
    """Evaluate `js` on `webview` and deliver the result to ``callback``.

    Same evaluate_javascript pattern the matrix uses inline (e.g. the copy
    and theme checks); shared so the hostile-document probe stays readable.
    """

    def issued(src: WebKit.WebView, result, _user_data) -> None:
        callback(src.evaluate_javascript_finish(result))

    webview.evaluate_javascript(js, -1, None, None, None, issued, None)


def run_hostile_document_check(app, tmp: Path, settings_path: Path) -> None:
    """Open a raw-hostile markdown document and prove the WebView contains it.

    Starts a local TCP listener, writes markdown full of script vectors
    aimed at it, renders it in a fresh Viewer, then -- load finished plus
    1.5 s -- asks the page live: did any payload run or survive in the DOM,
    did anything reach the listener?
    """
    listener = PwnListener()
    listener.start()
    base = f"http://127.0.0.1:{listener.port}"
    md = tmp / "hostile.md"
    # Raw HTML markdown (not fenced) -- the sanitizer sees it as-is.
    md.write_text(
        "# Hostile\n\n"
        f"<script>window.__pwn=1</script>\n\n"
        f'<img src="{base}/a.png" onerror="window.__pwn=2">\n\n'
        f'<iframe src="{base}/f"></iframe>\n\n'
        f'<svg onload="window.__pwn=3"><script>window.__pwn=4</script></svg>\n\n'
        f'<a href="javascript:window.__pwn=5">x</a>\n\n'
        f"<style>@import url({base}/s.css);</style>\n\n"
        f'<link rel="stylesheet" href="{base}/l.css">\n\n'
        f'<object data="{base}/o"></object>\n\n'
        f'<form action="{base}/p"><input></form>\n\n',
        encoding="utf-8",
    )
    win = zeile.Viewer(
        app,
        md,
        enable_mermaid=False,
        debug=False,
        theme_id="nord",
        body_font_id="ia-writer",
        code_font_id="jetbrains-mono",
        settings_path=settings_path,
    )

    state = {"done": False}

    def give_up() -> bool:
        # A WebView that never finishes loading must fail the check, not hang the matrix.
        if not state["done"]:
            state["done"] = True
            check("hostile-document-contained", False, "WebView never finished loading")
            listener.stop()
            app.quit()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(30, give_up)

    def on_load(_webview, event) -> None:
        if event != WebKit.LoadEvent.FINISHED:
            return
        GLib.timeout_add(1500, probe)
        return GLib.SOURCE_REMOVE

    def probe() -> bool:
        # IIFE, const-free (same redeclaration trap the copy wording in
        # zeile.py shies away from): collects leftover dangerous elements,
        # attributes that still point at the listener, javascript: anchors,
        # and window.__pwn's type. img[src] on its own is tolerated -- nh3's
        # default allowlist keeps an img spec, CSP img-src 'self' kills any
        # fetch, and the listener count below is what proves that.
        prefix = json.dumps(f"{base}/")
        # Wrapped in an IIFE so 'return' is legal (evaluate_javascript gets a
        # program, not a function body).
        js = (
            "(function(){"
            f"var p={prefix},leaks=[];"
            "var ban="
            "document.querySelectorAll('script,iframe,object,link[rel=stylesheet]');"
            "for(var i=0;i<ban.length;i++)leaks.push(ban[i].tagName.toLowerCase());"
            "var els=document.querySelectorAll('[src],[href],[action]');"
            "for(var j=0;j<els.length;j++){"
            "var el=els[j],tag=el.tagName.toLowerCase();"
            "var names=['src','href','action'];"
            "for(var k=0;k<names.length;k++){"
            "var v=el.getAttribute(names[k]);"
            "if(!v)continue;"
            "if(v.indexOf(p)===0&&!(tag==='img'&&names[k]==='src'))"
            "leaks.push(tag+'['+names[k]+']');"
            "}"
            "if(tag==='a'&&el.hasAttribute('href')&&"
            "el.getAttribute('href').toLowerCase().indexOf('javascript:')===0)"
            "leaks.push('a[javascript]');"
            "}"
            "var all=document.querySelectorAll('*');"
            "for(var n=0;n<all.length;n++){"
            "var at=all[n].attributes;"
            "for(var m=0;m<at.length;m++){"
            "if(/^on/i.test(at[m].name))"
            "leaks.push(all[n].tagName.toLowerCase()+'['+at[m].name+']');"
            "}"
            "}"
            "return (typeof window.__pwn)+'|'+leaks.join(',');"
            "})();"
        )

        def probe_cb(value) -> None:
            try:
                raw = value.to_string() or ""
            except Exception as exc:  # noqa: BLE001
                problems = [f"probe JS failed: {exc}"]
            else:
                # Format: "<pwn-type>|<leak tokens CSV>" -- the CSV never
                # contains '|', so a plain split is unambiguous.
                pwn, _, leaks = raw.partition("|")
                problems = []
                if pwn != "undefined":
                    problems.append(f"window.__pwn is {pwn!r}, undefined expected")
                if leaks:
                    problems.append(f"dangerous markup survived: {leaks}")
            seen = listener.settled_count()
            if seen != 0:
                problems.append(f"listener accepted {seen} connection(s)")
            state["done"] = True
            check(
                "hostile-document-contained",
                not problems,
                "; ".join(problems) if problems else "script off, DOM clean, 0 fetches",
            )
            listener.stop()
            app.quit()

        evaluated(win.webview, js, probe_cb)
        return GLib.SOURCE_REMOVE

    # Connected before present(): FINISHED can arrive in an early main-loop
    # turn, and a missed probe means a stuck matrix.
    win.webview.connect("load-changed", on_load)
    win.present()


def run_tasklist_no_bullet_check(
    app, tmp: Path, settings_path: Path, then: Callable[[], None]
) -> None:
    """Task items hide bullets; plain siblings (incl. nested) keep theirs."""
    md = tmp / "tasklist.md"
    md.write_text(
        "- [x] done\n- [ ] todo\n- plain\n    - nested plain\n    - [ ] nested task\n",
        encoding="utf-8",
    )
    win = zeile.Viewer(
        app,
        md,
        enable_mermaid=False,
        debug=False,
        theme_id="nord",
        body_font_id="ia-writer",
        code_font_id="jetbrains-mono",
        settings_path=settings_path,
    )
    state = {"done": False}

    def give_up() -> bool:
        if not state["done"]:
            state["done"] = True
            check("tasklist-no-bullet", False, "WebView never finished loading")
            then()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(30, give_up)

    def on_load(_webview, event) -> None:
        if event != WebKit.LoadEvent.FINISHED or state["done"]:
            return
        state["done"] = True  # arm once; FINISHED can repeat on re-render
        GLib.timeout_add(500, probe)
        return GLib.SOURCE_REMOVE

    def probe() -> bool:
        js = (
            "(function(){"
            "var tasks=document.querySelectorAll('li.task-list-item');"
            "var plains=document.querySelectorAll("
            "'ul.task-list > li:not(.task-list-item)');"
            "var out=[],ok=true;"
            "if(tasks.length<2||plains.length<2)return 'count';"
            "for(var i=0;i<tasks.length;i++){"
            "var t=getComputedStyle(tasks[i]).listStyleType;"
            "out.push('t:'+t);if(t!=='none')ok=false;"
            "}"
            "var bullets={disc:1,circle:1,square:1};"
            "for(var j=0;j<plains.length;j++){"
            "var p=getComputedStyle(plains[j]).listStyleType;"
            "out.push('p:'+p);if(!bullets[p])ok=false;"
            "}"
            "return (ok?'ok':'bad')+'|'+out.join(',');"
            "})();"
        )

        def probe_cb(value) -> None:
            try:
                raw = value.to_string() or ""
            except Exception as exc:  # noqa: BLE001
                ok, detail = False, f"probe JS failed: {exc}"
            else:
                status, _, detail = raw.partition("|")
                ok = status == "ok"
                if not detail:
                    detail = raw
            check("tasklist-no-bullet", ok, detail)
            then()

        evaluated(win.webview, js, probe_cb)
        return GLib.SOURCE_REMOVE

    win.webview.connect("load-changed", on_load)
    win.present()


def run_overflow_contained_check(
    app, tmp: Path, settings_path: Path, then: Callable[[], None]
) -> None:
    """Wide table + long code must scroll inside, not widen the document."""
    md = tmp / "overflow.md"
    cols = 30
    headers = "| " + " | ".join(f"C{i:02d}" for i in range(cols)) + " |"
    sep = "| " + " | ".join(["---"] * cols) + " |"
    row = "| " + " | ".join(f"cell{i:02d}" for i in range(cols)) + " |"
    code_line = "x" * 500
    md.write_text(
        f"# Overflow\n\n{headers}\n{sep}\n{row}\n\n```\n{code_line}\n```\n",
        encoding="utf-8",
    )
    win = zeile.Viewer(
        app,
        md,
        enable_mermaid=False,
        debug=False,
        theme_id="nord",
        body_font_id="ia-writer",
        code_font_id="jetbrains-mono",
        settings_path=settings_path,
    )
    state = {"done": False, "armed": False, "problems": []}
    widths = (480, 1280)

    def give_up() -> bool:
        if not state["done"]:
            state["done"] = True
            check("overflow-contained", False, "WebView never finished loading")
            then()
        return GLib.SOURCE_REMOVE

    GLib.timeout_add_seconds(30, give_up)

    def finish() -> None:
        if state["done"]:
            return
        state["done"] = True
        problems = state["problems"]
        check(
            "overflow-contained",
            not problems,
            "; ".join(problems) if problems else f"ok at {widths}",
        )
        then()

    def probe_at(width: int, next_cb: Callable[[], None]) -> None:
        win.set_default_size(width, 800)

        def after_resize() -> bool:
            js = (
                "(function(){"
                "var de=document.documentElement;"
                "var docOk=de.scrollWidth<=de.clientWidth;"
                "function scrollable(el){"
                "if(!el)return 'missing';"
                "var ox=getComputedStyle(el).overflowX;"
                "if(!(ox==='auto'||ox==='scroll'))return 'overflowX='+ox;"
                "if(el.scrollWidth<=el.clientWidth)"
                "return 'no-scroll sw='+el.scrollWidth+' cw='+el.clientWidth;"
                "return 'ok';"
                "}"
                "var t=scrollable(document.querySelector('table'));"
                "var c=scrollable(document.querySelector('pre'));"
                "return [docOk?'docOk':'docWide',"
                "de.clientWidth,de.scrollWidth,'table:'+t,'pre:'+c].join('|');"
                "})();"
            )

            def probe_cb(value) -> None:
                try:
                    raw = value.to_string() or ""
                except Exception as exc:  # noqa: BLE001
                    state["problems"].append(f"w={width}: probe JS failed: {exc}")
                else:
                    parts = raw.split("|")
                    if parts[0] != "docOk":
                        state["problems"].append(f"w={width}: document overflow {raw}")
                    for part in parts[3:]:
                        if not part.endswith(":ok"):
                            state["problems"].append(f"w={width}: {part}")
                next_cb()

            evaluated(win.webview, js, probe_cb)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(400, after_resize)

    def on_load(_webview, event) -> None:
        if event != WebKit.LoadEvent.FINISHED or state["armed"] or state["done"]:
            return
        state["armed"] = True  # FINISHED can repeat on re-render

        def start() -> bool:
            if state["done"]:
                return GLib.SOURCE_REMOVE

            def step(i: int) -> None:
                if i >= len(widths):
                    finish()
                    return
                probe_at(widths[i], lambda: step(i + 1))

            step(0)
            return GLib.SOURCE_REMOVE

        GLib.timeout_add(500, start)
        return GLib.SOURCE_REMOVE

    win.webview.connect("load-changed", on_load)
    win.present()


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
                            # 12-14. tasklist / overflow / hostile Viewers
                            # chain; hostile owns the quit.
                            run_tasklist_no_bullet_check(
                                a,
                                tmp,
                                settings_path,
                                lambda: run_overflow_contained_check(
                                    a,
                                    tmp,
                                    settings_path,
                                    lambda: run_hostile_document_check(
                                        a, tmp, settings_path
                                    ),
                                ),
                            )
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
