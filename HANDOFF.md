# zeile — Handoff

Created 2026-09-10. Renamed from `mdview` to `zeile` same day (name collision
research: `mdview` clashes on PyPI, npm, crates.io, AUR and a 144★ GitHub
project — see the full plan).

## Current Task

Executing the plan at `~/.claude/plans/hi-hier-wa-rein-humming-kahan.md`
(security hardening, Mermaid pre-render rewrite, feature fixes, i18n,
release docs — phased so `main` stays buildable after every commit).

**Phase 1 (rename) done, this commit.** Phase 2 (security + Mermaid rewrite)
is next.

## Files Changed

- `mdview.py` → `zeile.py`: `APP_ID` → `com.erdlabs.zeile`, internal
  `MDVIEW-MERMAID-*` stash marker → `ZEILE-MERMAID-*`, `window.__mdviewScroll`
  → `window.__zeileScroll`, `MdviewApp` class → `ZeileApp`, CLI error message
  updated. No behavioural change — pure rename.
- `assets/mdview.svg` → `assets/zeile.svg`
- `install.sh`: launcher/desktop-entry/icon name, `StartupWMClass`, comment
- `README.md`: title, paths, usage example, Files section
- `HANDOFF.md`: this file

## Decisions Made

- Application ID: `com.erdlabs.zeile` (renamed from `com.erdlabs.mdview`)
- Name `zeile`: verified clean across PyPI, npm, crates.io, AUR,
  Debian/Ubuntu, Flathub, GitHub search, domains — see plan for full research.
  One unresolved weak signal (an unclear Shenzhen `ZEILE` trademark) —
  acceptable for a private repo, needs a real DPMA/EUIPO check before any
  public listing.
- Licence: GPL-3.0-or-later, copyright retained (unchanged)
- GitHub remote already renamed `DnaMes/zeile` (private) before this session

## Next Steps

Per the plan's phasing (each step its own commit):

1. ~~Rename (`mdview` → `zeile` everywhere)~~ — done, this commit
2. **Security + Mermaid rewrite, together, one commit**: `nh3` HTML
   sanitizer (with the explicit attribute allowlist — ammonia's default
   strips `class`/`id`, breaking Pygments highlighting and TOC anchors),
   `enable-javascript-markup = False` (kills document `<script>` execution
   while keeping the app's own `evaluate_javascript()` for scroll-restore/
   TOC-jump), CSP header, ephemeral `WebKit.NetworkSession` +
   `decide-policy` scheme allowlist, HTML5 storage off, `enable_developer_extras`
   behind `--debug`/`ZEILE_DEBUG`. Mermaid moves from live vendored-JS render
   to `mmdc` subprocess pre-render to static SVG, cached by content hash,
   gated behind `--enable-mermaid` (default off, keeps base install
   Node-free). First thing in this phase: verify `nh3`'s attribute-allowlist
   behaviour empirically (not yet runtime-tested) before building on it.
3. Fix confirmed-broken renders: frontmatter leak, `pymdownx.tasklist`
4. Split `render()` into `render_body`/`build_document` + I/O shell, add
   `pytest` unit tests
5. Ctrl+F find-in-page, local `.md` link navigation with back/forward history
6. TOC overlay (Ctrl+T), Print/PDF export
7. Theme: full Pygments token coverage, VSCode Dark+/Light+ heading palette
8. i18n (gettext DE/EN), version-visible About dialog, CHANGELOG/PRIVACY/
   RELEASE/ASSETS.md, `install.sh` uninstall + dependency check

Full detail, rationale, and verification plan for every phase: the plan file
above.
