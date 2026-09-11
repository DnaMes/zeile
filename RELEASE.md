# Release Checklist — zeile

**This project does not ship to the Play Store.** It is a Linux desktop
application distributed as source, so most of the label's release checklist
does not apply. What remains is the licensing, versioning, security, and
documentation work every erdlabs project owes before its repository goes
public.

Current version: **0.1.0** (`pyproject.toml`), tagged and released 2026-09-11.

**Version drift risk**: `pyproject.toml`'s `version` and `zeile.py`'s
`__version__` (shown in the About dialog) are two hand-synced copies, not
one source of truth — this bare-Python project has no build step to derive
one from the other the way `docs/VERSIONING.md`'s `versionCode` derivation
does for the Android apps in this label. Check both are still equal before
tagging; a future bump script for this project should read one and write
the other, not update them independently.

---

## Blockers

- [x] **Never tagged.** CLOSED 2026-09-11: annotated tag `v0.1.0` created
      and pushed; GitHub release cut with CHANGELOG-derived notes
      (https://github.com/DnaMes/zeile/releases/tag/v0.1.0).
- [x] **No real Mermaid diagram has been rendered end-to-end.** CLOSED
      2026-09-11: `mmdc` 11.17.0 installed (`npm install -g --allow-scripts=
puppeteer @mermaid-js/mermaid-cli`), a real flowchart rendered through
      `mermaid_render.render_svg()` in both light and dark, the exact SVG
      zeile injects rasterized at full size (`rsvg-convert`) and verified —
      383 distinct colours, node fills (#ECECFF), strokes, all labels
      present. In the running app (headless cage): `.mermaid-diagram svg`
      with 5 nodes, 14 rects, 0 `<script>`. Also found and handled: mermaid
      11.17.2 **ignores** `flowchart.htmlLabels:false` (labels come out as
      `<foreignObject>` via config file, `%%{init}%%` directive AND
      `defaultRenderer:"native"` — the old comment's claim was never true
      on this version); containment is the document-level walls plus a new
      `_strip_script_vectors()` pass (tested in `tests/test_mermaid_render.py`).
- [ ] **No interactive GTK UI feature has been clicked through by a
      human.** LARGELY CLOSED 2026-09-11 by autonomous headless verification
      (real signal paths, real widget state, WebKit snapshots — see
      HANDOFF.md): find-in-page scrolls to the match; the TOC jump lands
      exactly on the row's heading (delta 0); the German UI shows live
      ("Theme und Schriften", "Inhaltsverzeichnis (Strg+T)"); the About
      dialog opens with name/version and closes; theme/font switching works
      across unlimited switches; scroll position survives reload end-to-end.
      Remaining, needing a person: the print dialog and PDF export are
      **unverifiable on this machine** (GTK4 4.22 ships no print backends —
      see README; the buttons no-op), a literal file-manager double-click,
      and `wtype`-driven keyboard input is unexercised.

## Licensing and provenance

- [x] `LICENSE` present — GPL-3.0-or-later, copyright retained.
- [x] SPDX header + copyright line in every `.py` file.
- [x] `ASSETS.md` accounts for the one shipped asset (`assets/zeile.svg`)
      and documents the vendored-then-removed `mermaid.min.js`.
- [x] No vendored third-party code remains in the repository.

## Documentation

- [x] `README.md` documents every flag, shortcut, and the full security
      architecture.
- [x] `PRIVACY.md` — written 2026-09-10, verified against the source
      (`grep` for network-call patterns, checked at write time).
- [x] `CHANGELOG.md` — written 2026-09-10 from `git log`.
- [x] `README.md` links `PRIVACY.md`/`CHANGELOG.md`/`RELEASE.md`/`ASSETS.md`.

## Verification before release

- [x] `ruff check` + `ruff format --check` clean.
- [x] `pytest` — 22/22 passing (`tests/`).
- [x] `shellcheck install.sh` — clean as of 2026-09-10, re-check after any
      further edit; re-checked clean 2026-09-11.
- [ ] Install on a clean machine (no `python-nh3`/`python-pymdown-extensions`
      pre-installed) — verify `install.sh` fails with the specific missing
      package name, not a generic error, and that installing the named
      package and re-running actually works.
- [x] `./install.sh --uninstall` then `./install.sh` again — verified
      2026-09-11: uninstall removes launcher/desktop entry and the default
      handler reverts to the previous one; reinstall restores `zeile.desktop`.
- [ ] Actually double-click a `.md` file in a file manager after install —
      every verification so far has launched via CLI. Closest autonomous
      equivalent done 2026-09-11: `xdg-mime query default text/markdown` →
      `zeile.desktop`, and the installed launcher
      (`~/.local/bin/zeile file.md` — the desktop entry's exact Exec) runs
      the app end-to-end inside a headless compositor.
- [x] `LANG=de_DE.UTF-8 zeile ...` — verified 2026-09-11 in a real running
      window (headless compositor, widget-level): tooltips and titles show
      the German strings ("Theme und Schriften", "Inhaltsverzeichnis
      (Strg+T)"); the About dialog shows name/version.

## Publishing

- [x] Repository is private on GitHub (`DnaMes/zeile`) — confirmed as of
      this rename; re-check before any public-listing decision.
- [x] Tag `v0.1.0` and cut a GitHub release — done 2026-09-11
      (`5ac2795`, https://github.com/DnaMes/zeile/releases/tag/v0.1.0),
      with the print/PDF platform limitation stated in the release notes.
      The two remaining verification items above (literal file-manager
      double-click, clean-machine install) are recorded as follow-ups, not
      release blockers, by owner decision 2026-09-11.

## Not applicable

Play Console account, testers, AAB, target API level, Data Safety form,
content rating, store screenshots, feature graphic, F-Droid. None of these
apply to a desktop application distributed as source.
