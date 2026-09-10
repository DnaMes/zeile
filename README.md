# zeile

A small GTK4 markdown viewer for Linux, with Mermaid diagram support.

> **No advertising. No tracking. No analytics. No unnecessary permissions.**

## Why

Markdown viewers are either terminal-only (no diagrams), full editors, or
full note-taking apps with far more surface than "look at this file". This
one does one thing: render a `.md` file, live-reload it on save, and get out
of the way. Built on the GTK4 and WebKitGTK already on the system, so it
starts fast and stays readable, no bundled browser engine.

A `.md` file is untrusted content by the time it reaches this app (it's the
double-click default handler for `text/markdown`), so the rendered document
runs with document JavaScript structurally disabled, an explicit HTML
sanitizer allowlist, no persistent storage, and no network access beyond
handing a clicked link to your actual browser. See Security below.

## Install

```bash
./install.sh
```

Writes:

| Path | What |
|---|---|
| `~/.local/bin/zeile` | launcher (pins `/usr/bin/python3`) |
| `~/.local/share/applications/zeile.desktop` | desktop entry + mime association |
| `~/.local/share/icons/hicolor/scalable/apps/zeile.svg` | icon |

Then sets itself as the default handler for `text/markdown`, so double-clicking
a `.md` file in the file manager opens it.

## Usage

```bash
zeile README.md                    # GUI window
zeile --enable-mermaid README.md   # render mermaid diagrams (needs mmdc, see below)
zeile --debug README.md            # enable WebKit developer tools
```

`ZEILE_DEBUG=1` is equivalent to `--debug`.

| Shortcut | Action |
|---|---|
| `Ctrl+R` | reload |
| `Ctrl+W` / `Ctrl+Q` | close |
| `Ctrl++` / `Ctrl+-` | zoom |
| `Ctrl+0` | reset zoom |
| `Ctrl+F` | find in page |
| `Alt+Left` / `Alt+Right` | back / forward through visited local links |
| `Ctrl+T` | table of contents overlay (click a heading to jump to it) |
| `Ctrl+P` | print |

The header bar also has a PDF export button (save-location picker, then
straight to a PDF file — no print dialog in between).

The file is watched, so edits in another editor re-render automatically
(debounced by 120 ms, because editors write in bursts). Clicking a link to
another local `.md` file navigates to it in the same window, with back/
forward history — the target file is watched instead, and the original stays
one `Alt+Left` away.

## Features

- GitHub-style CSS, light and dark following `prefers-color-scheme`
- Tables, footnotes, definition lists, admonitions, TOC anchors
- Syntax highlighting via Pygments
- Mermaid diagrams: fenced ```` ```mermaid ```` blocks render as real
  diagrams, opt-in via `--enable-mermaid`. Pre-rendered to static SVG by the
  `mmdc` CLI (`@mermaid-js/mermaid-cli`) at render time, cached by content
  hash, so the document view itself never runs a live JS diagram renderer —
  off by default so the base install needs no Node.js.
- Symlinks resolved: the window shows the name you opened, but watches the
  real target — monitoring a symlink itself never reports edits to its target

## Requirements

Arch packages (`python-gobject` is usually already pulled in by the desktop):

```bash
sudo pacman -S --needed python-gobject webkitgtk-6.0 python-markdown python-pygments python-nh3 python-pymdown-extensions
```

The launcher hardcodes `/usr/bin/python3` on purpose: a `brew` or `mise`
python that comes first on `PATH` typically has no `gi` bindings, so
`import gi` fails under it.

`--enable-mermaid` additionally needs `mmdc` on `PATH`:

```bash
npm install -g @mermaid-js/mermaid-cli
```

This pulls a headless Chromium via Puppeteer (roughly 300 MB) — that's why
it's a separate opt-in step and not part of the base install. Without
`--enable-mermaid`, fenced ` ```mermaid ` blocks render as plain text instead
of a diagram; with `--enable-mermaid` but no `mmdc` on `PATH`, they render a
clear error instead of silently failing.

## Security

A markdown file you open here is not assumed to be something you wrote or
trust — it's whatever a double-click on `.md` handed to this app. That
shapes every decision below, each one verified against the real WebKitGTK
API, not assumed:

- **Document JavaScript is structurally disabled** (`enable-javascript-markup
  = False`), so a `<script>` or `onerror=` embedded in the source cannot run,
  independent of the sanitizer below. The app's own `evaluate_javascript()`
  calls (scroll position) still work — they never evaluate anything sourced
  from the document.
- **The converted HTML is sanitized** (`nh3`/ammonia) with an explicit
  attribute allowlist: `<script>`, all `on*` handlers, `javascript:`/`data:`
  URLs, `<iframe>`/`<object>`/`<embed>`, and `<style>` blocks are stripped
  from anything the markdown source embeds directly, while headings keep
  their anchor `id`, code blocks keep their Pygments `class`, and footnotes
  keep their `id`/`href` pairs.
- **A Content-Security-Policy** (`default-src 'none'`) is set on the
  generated document, closing the one vector that needs no script at all —
  an `<img src=http://tracker/pixel>` beacon.
- **No network access.** The WebView uses an ephemeral `NetworkSession` (no
  persisted cookies or cache), and a navigation-policy handler only allows
  `file://` links under the open document's own directory — anything else
  (`http(s)`, or a `file://` path outside that tree) is handed to your
  system's default opener instead of being loaded in this window.
- **No persistent storage** — HTML5 local storage and the HTML5 database are
  both off, so a `.md` file can't plant an identifier that survives across
  opens.
- **Developer tools are off by default**, behind `--debug`/`ZEILE_DEBUG`.

## Internationalization

The UI is available in English and German, following your system locale
(`LANGUAGE`/`LANG`). Translations live in `po/de.po`; `install.sh` compiles
them to `locale/<lang>/LC_MESSAGES/zeile.mo` if `gettext` is available.

## Files

```
zeile.py                the app
markdown_ext.py          mermaid fence extraction (python-markdown preprocessor)
mermaid_render.py        mmdc subprocess wrapper, content-hash cache
assets/style.css         rendering stylesheet
assets/zeile.svg         icon
po/de.po                 German translation
install.sh               installer (also: --uninstall)
```

## Build

Nothing to build — `zeile.py` runs as-is via the `/usr/bin/python3`
interpreter the launcher pins.

## Licence

GPL-3.0-or-later. Copyright (c) 2026 erdlabs.

See also: [CHANGELOG.md](CHANGELOG.md), [PRIVACY.md](PRIVACY.md),
[RELEASE.md](RELEASE.md), [ASSETS.md](ASSETS.md).

Part of [erdlabs](https://erdlabs.com).
