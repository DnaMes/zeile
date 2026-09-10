# Changelog

All notable changes to this project.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
### Changed
### Fixed
### Removed

## [0.1.0] — unreleased

First version. Reconstructed from `git log`; this project has never been
tagged or released, so the date is deliberately absent. Ported in from a
personal-laptop project (`e14/apps/mdview`) and renamed to `zeile` the same
day `mdview` collided with an existing AUR package and a 144-star GitHub
project.

### Added

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
