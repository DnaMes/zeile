# mdview

A small GTK4 markdown viewer for Linux, with Mermaid diagram support.

> **No advertising. No tracking. No analytics. No unnecessary permissions.**

## Why

Markdown viewers are either terminal-only (no diagrams), full editors, or
full note-taking apps with far more surface than "look at this file". This
one does one thing: render a `.md` file, live-reload it on save, and get out
of the way. Built on the GTK4 and WebKitGTK already on the system, so it
starts fast and stays readable — ~210 lines of Python, no bundled browser
engine.

## Install

```bash
./install.sh
```

Writes:

| Path | What |
|---|---|
| `~/.local/bin/mdview` | launcher (pins `/usr/bin/python3`) |
| `~/.local/share/applications/mdview.desktop` | desktop entry + mime association |
| `~/.local/share/icons/hicolor/scalable/apps/mdview.svg` | icon |

Then sets itself as the default handler for `text/markdown`, so double-clicking
a `.md` file in the file manager opens it.

## Usage

```bash
mdview README.md          # GUI window
```

| Shortcut | Action |
|---|---|
| `Ctrl+R` | reload |
| `Ctrl+W` / `Ctrl+Q` | close |
| `Ctrl++` / `Ctrl+-` | zoom |
| `Ctrl+0` | reset zoom |

The file is watched, so edits in another editor re-render automatically
(debounced by 120 ms, because editors write in bursts).

## Features

- GitHub-style CSS, light and dark following `prefers-color-scheme`
- Tables, footnotes, definition lists, admonitions, TOC anchors
- Syntax highlighting via Pygments
- Mermaid diagrams: fenced ```` ```mermaid ```` blocks render as real
  diagrams (mermaid.js vendored in `assets/`, only loaded into the page when
  a diagram is actually present, theme follows `prefers-color-scheme`)
- Symlinks resolved: the window shows the name you opened, but watches the
  real target — monitoring a symlink itself never reports edits to its target

## Requirements

Arch packages (`python-gobject` is usually already pulled in by the desktop):

```bash
sudo pacman -S --needed python-gobject webkitgtk-6.0 python-markdown python-pygments
```

The launcher hardcodes `/usr/bin/python3` on purpose: a `brew` or `mise`
python that comes first on `PATH` typically has no `gi` bindings, so
`import gi` fails under it.

## Permissions

None beyond reading the markdown file you open (and watching it for changes).
No network access, no other files touched.

## Files

```
mdview.py               the app
assets/style.css        rendering stylesheet
assets/mdview.svg       icon
assets/mermaid.min.js   vendored mermaid.js (pinned 12.0.0, MIT)
install.sh              installer
```

## Build

Nothing to build — `mdview.py` runs as-is via the `/usr/bin/python3`
interpreter the launcher pins.

## Licence

GPL-3.0-or-later. Copyright (c) 2026 erdlabs.

Part of [erdlabs](https://erdlabs.com).
