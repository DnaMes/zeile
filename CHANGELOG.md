# Changelog

All notable changes to this project.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.5.0] — 2026-10-27

### Added

- Three new popular dark themes: `vscode-dark` (VS Code Dark+), `one-dark` (Atom One Dark), and `monokai` (Monokai Pro/Classic). Zeile now ships 20 curated themes.
- Dedicated heading color hierarchy: explicit CSS variables (`--h1-color` through `--h6-color`, `--h1-border`, `--h2-border`) across all 20 themes, giving distinctive and readable hierarchy colors to Cyberpunk, Tokyo Night, Solarized Dark, Dracula, Nord, Gruvbox, and others.
- Enhanced blockquote styling: introduced `--quote-fg` alongside theme-tuned quote borders and backgrounds for clear, readable callouts.
- Shell completions (bash, fish, zsh) updated with the new theme choices.

## [0.4.1] — 2026-10-27

### Fixed

- The Fedora `.rpm` now requires `gobject-introspection`: on a minimal system the viewer failed to
  start with "Typelib file for namespace 'cairo' not found" (found by installing the published
  0.4.0 package in a clean container).
- The Flatpak check reports network isolation only when the probe really attempted the connection.
- Documentation: `PRIVACY.md` states the `--enable-mermaid` exception where it describes network
  activity; `RELEASE.md` no longer carries outdated test counts or print wording.

## [0.4.0] — 2026-10-27

### Added

- `F1` opens a small list of the keyboard shortcuts (Escape or `F1` closes it).
- Reading width: narrow, standard or wide document column, chosen in the theme and fonts popover and remembered (`reading_width` in `settings.json`; unknown values fall back to standard).
- Man pages in English and German and completions for bash, zsh and fish (`man zeile`); the user
  installer writes the man pages and the bash and fish completions and removes only files it wrote.
- `zeile --help` is translated (German with `LANGUAGE=de`).
- German desktop entries and AppStream metadata for the packages.

### Fixed

- A document with invalid UTF-8 opens (the bad bytes show as U+FFFD); a damaged `settings.json`
  or out-of-range window and zoom values fall back to defaults instead of failing.
- When Mermaid fails (timeout, helper missing, non-zero exit, empty or oversized output) the
  document shows a translated, escaped error block instead of breaking.
- Task list items (`- [x]`) show only the checkbox, without a bullet next to it.

### Changed

- Releases are published only after the `.deb` and `.rpm` are attached (draft first).
- Screenshot generation fails loudly when a PNG cannot be written.

## [0.3.1] — 2026-10-27

### Added

- Flatpak manifest (`packaging/flatpak/`, GNOME 50 runtime, read-only access to the home
  directory, no network), AppStream metainfo and a desktop entry under the id `com.erdlabs.zeile`.
- Debian/Ubuntu `.deb` and Fedora `.rpm` build scripts (`packaging/debian/`, `packaging/rpm/`);
  all system packages share one layout (`packaging/stage.sh`).
- `scripts/package-check.sh` builds a package in a clean container, installs it and starts the viewer.

### Fixed

- The first-start logo was missing in installed packages (it was only found in a source
  checkout); packages now ship it, and a missing image skips the start sequence instead of
  raising an error.

## [0.3.0] — 2026-10-26

### Added

- Start sequence: the first time zeile starts after install, the erdlabs mark fades in and out (about 3 seconds), then the zeile logo fades in and out (about 1.4 seconds) as a skippable overlay while the viewer opens behind it; later starts show no title card (BRAND.md §7). Press any key or click to skip all of it; with GTK animations turned off the frames show without fades. Screen readers get “Start sequence” and “Press any key or click to skip”. The version number is shown only in the About dialog.
- Cyberpunk theme: vivid neon-accented dark theme featuring cyan, magenta, and electric
  green accents against a deep dark navy background.
- Enhanced heading color hierarchy & section separation: headings `h1`–`h6` now use
  theme syntax tokens (`--syn-function`, `--syn-type`, `--syn-keyword`, `--syn-builtin`)
  with clean `h1`/`h2` bottom borders and generous vertical spacing for effortless section scanning.
- Styled code blocks and table headers: `<pre>` code blocks feature an accent-colored
  left border (`3.5px solid var(--accent)`), inline code snippets are distinctively badged
  with subtle borders, table headers feature an accent bottom line, and `hr` dividers use
  an accent gradient.
- Document reading statistics: Table of Contents (`Ctrl+T`) popover displays total
  word count, section count, and estimated reading time (`~X min read`) at the top
  of the outline.
- Filterable Table of Contents: an instant search filter in the TOC popover allows
  quickly filtering through headings in long outlines, with `Enter` jumping directly
  to the first match. Friendly empty state placeholder when no headings exist.
- Heading anchor permalinks: headings (`h1`–`h6`) display a subtle `#` anchor link on hover,
  matching the GitHub/GitLab reading experience.
- Clean intra-document link previews: hovering over heading anchors or internal hash links
  displays a clean `#section-name` in the bottom link preview pill rather than full file URIs.
- GitHub-Flavored Markdown (GFM) Alerts: blockquotes formatted with `> [!NOTE]`,
  `> [!TIP]`, `> [!IMPORTANT]`, `> [!WARNING]`, and `> [!CAUTION]` render as
  styled admonition containers with theme-matching SVG icons, distinct left
  accent borders, and optional custom titles.
- Link hover URL preview: hovering over any link reveals a floating status
  pill at the bottom-left showing the destination URI before clicking, providing
  clear visual feedback for external vs. local document links.
- Fullscreen mode: toggle fullscreen view with `F11` for focused, distraction-free
  reading.
- Freedesktop app icon set: PNG icons from 16×16 up to 512×512 and a scalable
  SVG under `icons/hicolor/`, installed by `install.sh` and packaged in
  `packaging/PKGBUILD`.

### Security

- A link to a local file other than a markdown file or an image (for example `.html`
  or `.svg`) is now handed to the system opener instead of being loaded inside the
  viewer, where it would have rendered without the document's Content-Security-Policy.

### Changed

- `install.sh` prints the fix line for apt and dnf as well as pacman, and no longer
  fails when `xdg-mime` is missing.
- The Arch `PKGBUILD` now installs under `$pkgdir` (it wrote to the build host before).
- Release checksums (`SHA256SUMS`) list bare file names, so `sha256sum -c` works
  next to the downloaded archive.
- CI runs on GitHub-hosted runners and tests Arch, Debian 13, Ubuntu 24.04 and Fedora 43.
- About dialog now shows the app icon, the current version, and the erdlabs
  logo, replacing the stock About dialog.


## [0.2.0] — 2026-09-16

### Added

- Copy button on every code block: hover the block (or focus the button
  with the keyboard; always visible on touch) and a small copy affordance
  appears top-right — click copies the block's plain text to the system
  clipboard and flashes a check mark. Implemented entirely without document
  JavaScript: the button is an `<a href="zeile-copy://N">` whose click is
  intercepted in the WebKit policy handler (verified end-to-end in the
  headless GUI matrix: click → clipboard round trip).
- Automatic language detection for code blocks without a language tag.
  Pygments' `guess_lexer` was measured to misfire badly on realistic
  snippet sizes (Python → "Tera Term macro", JSON/SQL → plain text,
  PythonLexer scoring 1.0 _on JavaScript_), so detection is a new
  rule-based module (`code_lang.py`): shebang fast paths, JSON/YAML/TOML/
  INI/Dockerfile/diff structure checks, weighted per-language indicators
  with threshold + runner-up margin. Untagged fences now highlight;
  ambiguous or prose blocks deliberately stay plain.
- Find-in-page shows a live match count next to the search entry, with a
  clear "No matches" state (closes a HANDOFF backlog item).
- Launching without a file (app menu / launcher) now opens a markdown file
  chooser instead of exiting with a usage error.
- Window size, maximized state and zoom level persist across sessions
  (`settings.json`); theme/font changes merge into the saved state instead
  of resetting it.
- "Auto" theme follows mid-session system light/dark switches immediately,
  including the Mermaid palette.
- Print and PDF-export buttons degrade visibly when GTK4 print backends
  are missing (insensitive + explanatory tooltip) instead of silently
  no-oping.
- About dialog now shows the erdlabs brand mark.

### Changed

- Local `.md` link navigation defers the document switch out of the WebKit
  policy callback (`GLib.idle_add`), closing the re-entrancy risk flagged
  in HANDOFF.md.

## [0.1.0] — 2026-09-11

First tagged release. Ported in from a personal-laptop project
(`e14/apps/mdview`) and renamed to `zeile` the same day `mdview` collided
with an existing AUR package and a 144-star GitHub project.

### Added

- 16 curated document themes plus system-following "Auto": GitHub Light/Dark,
  Catppuccin (Latte, Frappé, Macchiato, Mocha), Solarized Light/Dark,
  Gruvbox Light/Dark, Nord, Dracula, Rosé Pine/Dawn, Tokyo Night/Day — each
  with its own full Pygments syntax palette, selectable live from a new
  header-bar popover (`--theme` also works from the CLI).
- Body- and code-font pickers (Inter, Atkinson Hyperlegible, iA Writer,
  Noto Serif, IBM Plex Sans; JetBrains Mono, iA Writer Mono, Fira Code,
  Cascadia Code) with system-fallback stacks (`--body-font`/`--code-font`).
- Theme and font selections persist to `~/.config/zeile/settings.json`
  (defensively parsed; invalid values fall back to defaults).
- Readability polish: tinted blockquotes, zebra + hover table rows, themed
  text selection, `accent-color` task checkboxes, `kbd` keycap styling,
  link focus outlines, print/PDF output forced to a light palette.
- Render a `.md` file in a GTK4 + WebKitGTK window, live-reloading on save
  (debounced 120 ms).
- GitHub-style CSS, light and dark following the system theme, with a
  VSCode-inspired colour accent on headings.
- Tables, footnotes, definition lists, admonitions, task lists
  (`- [ ]`/`- [x]` as real disabled checkboxes), TOC anchors, full Pygments
  syntax-highlighting token coverage.
- YAML frontmatter is stripped before rendering instead of leaking into the
  document as raw text.
- Mermaid diagrams: fenced ` ```mermaid ` blocks, opt-in via
  `--enable-mermaid`, pre-rendered to static SVG by the `mmdc` CLI and
  cached by content hash — the document view itself never runs a live JS
  diagram renderer.
- Find in page (`Ctrl+F`), a table-of-contents overlay (`Ctrl+T`), and
  local `.md`/`.markdown` link navigation with back/forward history
  (`Alt+Left`/`Alt+Right`).
- Print (`Ctrl+P`) and a header button to export straight to PDF.
- An About dialog showing the current version.
- German and English UI strings via `gettext` (`po/de.po`).
- `install.sh`: launcher, desktop entry, mime association, a dependency
  check that names the exact missing `pacman` package, and `--uninstall`.

### Changed

- All colours in `assets/style.css` (including the previously hardcoded
  Pygments token blocks) now flow through CSS variables; themes are pure
  variable blocks in `assets/themes.css`, switched via `data-theme` /
  `data-font-*` attributes on `<html>` — instant, no re-render, scroll and
  zoom preserved. Only a Mermaid light↔dark flip triggers a real reload.
- Choosing a dark theme also prefers the dark GTK style, so the header bar
  matches the document.

### Fixed

- Theme/font switching was a silent no-op after the first switch on a page:
  the injected JS used `const root = …`, whose top-level binding persists
  across `evaluate_javascript()` calls, so every later call died with a
  SyntaxError nothing surfaced. Now uses direct `documentElement` calls.
- Scroll position is actually restored after a reload now — and the original
  approach was doubly broken: `__zeileScroll` was stashed on the page being
  replaced (gone with the fresh document's fresh JS global) and the save
  raced the immediately-following `load_html`. The offset is now read into
  Python first, and restored after WebKit's `load-changed` FINISHED, clamped
  to the new document height.
- Mermaid output is defensively stripped of `<script>` elements and `on*=`
  handler attributes in `mermaid_render` before it reaches the page:
  empirically, mmdc 11.17.0 / mermaid 11.17.2 ignores the
  `flowchart.htmlLabels:false` config (labels arrive as `<foreignObject>`
  HTML), so the previously assumed suppression does not hold and the SVG
  — which is injected after the nh3 pass — now gets its own pass. Covered
  by `tests/test_mermaid_render.py`.
- Known platform limitation documented: on GTK 4.22 (Arch `gtk4 1:4.22.4`)
  the print dialog and PDF export no-op because GTK4 no longer ships print
  backends and no follow-up package provides them.
- `codehilite` line-number/token styles: `.gu` (Generic.Subheading) keeps a
  theme-relative colour instead of a hardcoded one; `.mi`/`.mf` numbers
  share the numeric token colour consistently.

### Security

A `.md` file is untrusted content by the time it reaches this app (it is
the default handler for `text/markdown`). The document WebView runs with:

- Document JavaScript structurally disabled
  (`enable-javascript-markup=False`) — a `<script>` or `onerror=` in the
  source cannot run.
- The converted HTML run through an explicit `nh3` sanitizer allowlist —
  `<script>`, event handlers, `javascript:`/`data:` URLs, `<iframe>`/
  `<object>`/`<embed>`, and `<style>` blocks are stripped.
- A Content-Security-Policy (`default-src 'none'`).
- An ephemeral `WebKit.NetworkSession` and a navigation-policy handler that
  only allows `file://` links under the open document's own directory —
  everything else is handed to the system's default opener instead of
  being loaded in this window.
- No persistent storage (HTML5 local storage and database both off).
- Developer tools off by default, behind `--debug`/`ZEILE_DEBUG`.
