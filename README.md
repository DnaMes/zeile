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

| Path                                                   | What                               |
| ------------------------------------------------------ | ---------------------------------- |
| `~/.local/bin/zeile`                                   | launcher (pins `/usr/bin/python3`) |
| `~/.local/share/applications/zeile.desktop`            | desktop entry + mime association   |
| `~/.local/share/icons/hicolor/scalable/apps/zeile.svg` | icon                               |
| `~/.local/share/icons/hicolor/*/apps/zeile.png`        | PNG icon sizes 16×16 to 512×512    |

Then sets itself as the default handler for `text/markdown`, so double-clicking
a `.md` file in the file manager opens it.

## Usage

```bash
zeile README.md                    # GUI window
zeile --enable-mermaid README.md   # render mermaid diagrams (needs mmdc, see below)
zeile --debug README.md            # enable WebKit developer tools
zeile --theme rose-pine README.md    # open with a specific theme (also saved)
zeile --body-font inter README.md    # set body font for this run
zeile --code-font jetbrains-mono README.md
```

`ZEILE_DEBUG=1` is equivalent to `--debug`.

| Shortcut                 | Action                                                    |
| ------------------------ | --------------------------------------------------------- |
| `Ctrl+R`                 | reload                                                    |
| `Ctrl+W` / `Ctrl+Q`      | close                                                     |
| `Ctrl++` / `Ctrl+-`      | zoom                                                      |
| `Ctrl+0`                 | reset zoom                                                |
| `Ctrl+F`                 | find in page                                              |
| `Alt+Left` / `Alt+Right` | back / forward through visited local links                |
| `Ctrl+T`                 | table of contents overlay (filter outline, stats, jump)   |
| `Ctrl+P`                 | print                                                     |
| `F11`                    | toggle fullscreen mode                                    |

The header bar also has a PDF export button (save-location picker, then
straight to a PDF file — no print dialog in between).

The file is watched, so edits in another editor re-render automatically
(debounced by 120 ms, because editors write in bursts). Clicking a link to
another local `.md` file navigates to it in the same window, with back/
forward history — the target file is watched instead, and the original stays
one `Alt+Left` away.

## Features

- GitHub-style CSS, light and dark following `prefers-color-scheme`
- 17 curated themes (GitHub Light/Dark, Catppuccin ×4, Solarized ×2,
  Gruvbox ×2, Nord, Dracula, Rosé Pine ×2, Tokyo Night ×2, Cyberpunk) plus an
  "Auto" mode following the system; pick in the header-bar palette button
  or via `--theme`. The selection persists in `~/.config/zeile/settings.json`
  (theme, fonts, zoom, window size and whether the erdlabs intro has played;
  no document content).
- Start sequence: on the first start after install the erdlabs mark fades in
  and out (about 3 s), then the zeile logo fades in and out (about 1.4 s) as a
  skippable overlay while the document window opens underneath. Both play once
  per install (`intro_seen` in `settings.json`); later starts go straight to
  the document (BRAND.md §7). Any key or click skips the whole sequence; with
  GTK animations off the frames show without fades.
  The version number appears only in the About dialog (header-bar help button).
  No sound, no network, no tracking.
- Body and code font pickers with graceful fallback stacks: Inter, Atkinson
  Hyperlegible, iA Writer Quattro, Noto Serif, IBM Plex Sans; JetBrains Mono,
  iA Writer Mono, Fira Code, Cascadia Code. Fonts are used if installed and
  silently fall back if not.
- Readability polish: color-coded heading hierarchy (`h1`–`h6`), accent-bordered
  code blocks (`3.5px solid var(--accent)`), tinted blockquotes, zebra table rows
  with accent headers, accent `hr` gradients, styled `kbd` keycaps, themed text
  selection, focus outlines, print/PDF always renders on a light palette
- Tables, footnotes, definition lists, admonitions, GFM alerts (`> [!NOTE]`, `> [!TIP]`, etc.), TOC anchors and hover `#` permalinks
- Document statistics (word count, reading time) and real-time heading filter in the TOC popover
- Copy button on every code block (top-right on hover, keyboard-focusable,
  always visible on touch): clicking it copies the block's plain text to
  the system clipboard and flashes a check mark — implemented without any
  document JavaScript (see Security)
- Syntax highlighting via Pygments, plus automatic language detection for
  code blocks with no language tag: a rule-based detector (shebangs, JSON/
  YAML/TOML/INI/Dockerfile/diff structure, weighted per-language indicators)
  picks the language before rendering, so untagged fences still get
  coloured. Conservative by design — ambiguous or plain-text blocks stay
  unhighlighted instead of getting a confidently wrong colour
- Find-in-page shows a live match count next to the search entry
  ("No matches" when the term isn't in the document)
- Link hover preview: hovering over a link displays its target URI in a
  subtle floating status pill at the bottom-left before clicking
- Mermaid diagrams: fenced ` ```mermaid ` blocks render as real
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

#### Print / PDF export

The print dialog and PDF export need GTK4's print backends (the `file`
backend for PDF). Recent GTK 4 releases (e.g. Arch's `gtk4 1:4.22.4`) no
longer ship them, and no follow-up package provides them — on such systems
both buttons exist but produce nothing (verified 2026-09-11). Everything
else is unaffected. View rendered markdown as PDF via any other tool in
the meantime.

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
- **The code-copy button uses no document script.** It is an `<a>` with a
  `zeile-copy://` URI injected after sanitization; the click arrives as a
  plain HTML navigation attempt in the policy handler, which puts the
  block's text on the GTK clipboard. A document forging its own
  `zeile-copy:` link can at worst copy a block of its own content.

## Internationalization

The UI is available in English and German, following your system locale
(`LANGUAGE`/`LANG`). Translations live in `po/de.po`; `install.sh` compiles
them to `locale/<lang>/LC_MESSAGES/zeile.mo` if `gettext` is available.

## Files

```
zeile.py                the app
markdown_ext.py          mermaid fence extraction + unlabeled-fence language hints (markdown preprocessor)
code_lang.py             rule-based language detection for untagged code blocks
mermaid_render.py        mmdc subprocess wrapper, content-hash cache
assets/style.css         rendering stylesheet
assets/themes.css        theme + font variable definitions
assets/zeile.svg         icon
po/de.po                 German translation
install.sh               installer (also: --uninstall)
```

## Build

There is nothing to compile for local development — `zeile.py` runs as-is via
the `/usr/bin/python3` interpreter the launcher pins. Release tags trigger
`.github/workflows/release.yml`, which validates the tag/version and publishes
a checksumed Linux source archive to the GitHub Release.

## Packaging & CI

- `packaging/PKGBUILD` — Arch/AUR package template (installs to
  `/usr/share/zeile`, never claims the markdown default handler on its
  own; users opt in via `xdg-mime`). The `source` URL resolves once the
  repository is public; until then build from a local checkout.
- `.github/workflows/ci.yml` — ruff, pytest and shellcheck on every push.
- `.github/workflows/release.yml` — validates SemVer/tag consistency, runs the
  full test/lint/package checks, and publishes `zeile-VERSION.tar.gz` plus
  `SHA256SUMS` for every `vX.Y.Z` tag.
- `scripts/check_version.py` — checks the version copies in `pyproject.toml`,
  `zeile.py` and `packaging/PKGBUILD`; the release workflow refuses drift.

## Platform support

- **Linux:** supported. The source release, `install.sh` and Arch `PKGBUILD`
  use the system GTK4/WebKitGTK 6.0 stack.
- **Windows/macOS:** no native binaries are published yet. PyGObject/GTK4
  itself is available on both platforms, but this application requires
  WebKitGTK 6.0; the current packaging sources do not provide a supported
  Windows or macOS WebKitGTK runtime. A real port needs a platform-specific
  WebView boundary (Windows WebView2 and macOS WKWebView) before installers
  can be produced. The release pipeline intentionally publishes no fake
  cross-platform artifacts.

## Licence

GPL-3.0-or-later. Copyright (c) 2026 erdlabs.

See also: [CHANGELOG.md](CHANGELOG.md), [PRIVACY.md](PRIVACY.md),
[RELEASE.md](RELEASE.md), [ASSETS.md](ASSETS.md).

Part of [erdlabs](https://erdlabs.com).
