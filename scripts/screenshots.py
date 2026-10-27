#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Render README screenshots of the real viewer window, headless.

    WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 \\
        cage -d -- /usr/bin/python3 scripts/screenshots.py docs/screenshots

Writes one PNG per theme in THEMES. Invisible and focus-safe: it runs inside
the headless cage compositor, like tests/headless_gui.py.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import zeile  # noqa: E402

THEMES = ("github-light", "github-dark", "catppuccin-mocha", "cyberpunk")

SAMPLE = """\
# zeile

A small markdown viewer for Linux. It live-reloads on save.

> [!TIP]
> Press `Ctrl+T` for the outline, `Ctrl+F` to search, `F11` for fullscreen.

## Code, tables, alerts

```python
def greet(name: str) -> str:
    return f"Hello, {name}!"
```

| Feature | Status |
| ------- | ------ |
| Themes  | 20     |
| Network | none   |

- [x] No advertising, no tracking
- [x] German and English
"""


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def write_png(texture: Gdk.Texture, path: Path) -> None:
    """Save the texture, trusting only a verified PNG on disk when it returns.

    save_to_png quietly returns False on failure, so the result is judged by
    what actually landed on disk: present, non-empty, and PNG-headed.
    """
    path.unlink(missing_ok=True)  # a stale PNG must not make a no-op save look successful
    if not texture.save_to_png(str(path)):
        raise RuntimeError(f"save_to_png({path}) returned False")
    try:
        data = path.read_bytes()
    except OSError as exc:  # the renderer can also leave nothing behind
        raise RuntimeError(f"{path}: not written after save ({exc})") from exc
    if not data:
        raise RuntimeError(f"{path}: empty file after save")
    if data[:8] != PNG_SIGNATURE:
        raise RuntimeError(f"{path}: not a PNG (bad signature)")
    if len(data) < 33 or data[12:16] != b"IHDR":  # signature + a complete IHDR chunk
        raise RuntimeError(f"{path}: truncated PNG (no complete IHDR)")


def save_window(win: Gtk.Window, out: Path) -> None:
    width, height = win.get_width(), win.get_height()
    paintable = Gtk.WidgetPaintable.new(win)
    snapshot = Gtk.Snapshot()
    paintable.snapshot(snapshot, width, height)
    node = snapshot.to_node()
    if node is None:
        raise RuntimeError(f"empty render node for a {width}x{height} window")
    texture = win.get_native().get_renderer().render_texture(node, None)
    write_png(texture, out)


def main() -> int:
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.TemporaryDirectory(prefix="zeile-shots-")
    md = Path(tmp.name) / "zeile.md"
    md.write_text(SAMPLE, encoding="utf-8")
    settings_path = Path(tmp.name) / "settings.json"
    settings_path.write_text(
        '{"zoom": 0.85, "window_maximized": false, "intro_seen": true}',
        encoding="utf-8",
    )
    failures: list[str] = []

    app = zeile.ZeileApp(
        md,
        enable_mermaid=False,
        debug=False,
        settings={"theme": "auto", "body_font": "system", "code_font": "system"},
        settings_path=settings_path,
        launch_sequence=False,
    )

    def on_activate(a: zeile.ZeileApp) -> None:
        a.hold()  # the app quits when its last window closes; we close them one by one
        for stale in a.get_windows():  # the app's own initial window would cover ours
            stale.destroy()
        themes = [THEMES[0], *THEMES]  # the first window under cage never maps: discard it
        discard = True

        def next_theme() -> bool:
            nonlocal discard
            if not themes:
                a.release()
                a.quit()
                return False
            theme = themes.pop(0)
            win = zeile.Viewer(
                a,
                md,
                enable_mermaid=False,
                debug=False,
                theme_id=theme,
                body_font_id="system",
                code_font_id="system",
                settings_path=settings_path,
            )
            win.present()

            attempts = 0
            warm_up, discard = discard, False

            def shoot() -> bool:
                nonlocal attempts
                if warm_up:
                    win.destroy()
                    GLib.timeout_add(200, next_theme)
                    return False
                attempts += 1
                target = out_dir / f"{theme}.png"
                try:
                    save_window(win, target)
                    print(f"wrote {target}")
                except RuntimeError as exc:
                    if attempts < 5:  # the first window maps late under cage
                        return True
                    failures.append(f"{theme}: {exc}")
                except (GLib.Error, AttributeError) as exc:
                    failures.append(f"{theme}: {exc}")
                win.destroy()
                GLib.timeout_add(200, next_theme)
                return False

            GLib.timeout_add(2500, shoot)  # let WebKit finish the first paint
            return False

        next_theme()

    app.connect("activate", on_activate)
    app.run([])
    for failure in failures:
        print(f"FAIL {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
