# mdview — Handoff

Created 2026-09-10.

## Current Task

Not a fresh scaffold: this is an existing, working tool ported in from a
personal laptop repo (`e14/apps/mdview`), where it started life as a small
GTK4 + WebKitGTK markdown viewer replacing a 121 MB Electron AppImage.
Mermaid diagram support was added there the same day, then the whole thing
was moved here to become a proper erdlabs product (own repo, GPL-3.0
licence, brand-promise README).

## Files Changed

Initial scaffold (README.md, LICENSE, HANDOFF.md, .gitignore,
.obsidian-doc) replaced/filled in with the real project:

- `mdview.py` — the app (SPDX header added)
- `install.sh` — installer (launcher, desktop entry, mime association)
- `assets/style.css`, `assets/mdview.svg`
- `assets/mermaid.min.js` — vendored Mermaid 12.0.0 (MIT), inlined only
  when a diagram is present in the rendered document
- `README.md` — rewritten with the erdlabs template's required sections
  (brand promise, Permissions, Licence) merged into the tool's real docs

## Decisions Made

- Application ID: `com.erdlabs.mdview` (matched what the app already used
  before the move — not a coincidence, same author/convention)
- Licence: GPL-3.0-or-later, copyright retained
- No icons/splash/colour work: this is a desktop GTK app, not a mobile
  app — the icon step in `docs/NEW-PROJECT.md` doesn't apply here, it
  already ships its own `assets/mdview.svg`

## Next Steps

1. `./install.sh` on any machine that wants it (sets `.md` as its default
   handler)
2. Decide on a GitHub remote (`DnaMes/mdview`, private, matching the other
   apps) and push — not done yet, needs explicit go-ahead
