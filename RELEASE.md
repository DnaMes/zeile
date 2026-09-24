# Release Checklist — zeile

**This project does not ship to the Play Store.** It is a Linux desktop
application distributed as source, so most of the label's release checklist
does not apply. What remains is the licensing, versioning, security, and
documentation work every erdlabs project owes before its repository goes
public.

Current version: **0.2.0** (`pyproject.toml`), release candidate prepared
2026-09-16. The tag workflow publishes a checksumed Linux source archive;
native Windows/macOS artifacts are intentionally not produced until the
WebView backend is ported (see README's Platform support section).

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
- [x] Install on a clean machine (no `python-nh3`/`python-pymdown-extensions`
      pre-installed) — CLOSED 2026-09-11 via a bubblewrap sandbox masking
      the real site-packages dirs: `install.sh` fails with the exact
      missing package name and the copy-pasteable `pacman` fix line for
      `python-markdown`, `python-nh3` and `python-pymdown-extensions`
      (exit 1, nothing written). This exposed and fixed a real gap: bare
      top-level imports (`import nh3`, `import markdown`) succeed vacuously
      as PEP 420 namespace packages when the package dir exists but is
      empty/broken — the checks now verify an attribute
      (`nh3.clean`, `markdown.markdown`), so a broken install is caught too.
      A full install/uninstall round trip was then run inside the sandbox
      into a fake `$HOME` (repo bound read-write so `msgfmt` compiles):
      launcher, desktop entry, icon and `mimeapps.list` all written, and
      `--uninstall` removes them again — the real `$HOME` untouched.
- [x] `./install.sh --uninstall` then `./install.sh` again — verified
      2026-09-11 both on the real `$HOME` and inside the sandbox (see above):
      uninstall removes launcher/desktop entry and the default handler
      reverts to the previous one; reinstall restores `zeile.desktop`.
- [ ] Actually double-click a `.md` file in a file manager after install —
      every verification so far has launched via CLI. Closest autonomous
      equivalents done 2026-09-11: `xdg-mime query default text/markdown` →
      `zeile.desktop`; `gtk-launch zeile file.md` (the exact desktop-entry
      activation path a file manager uses) spawns the real app process
      (`/usr/bin/python3 …/zeile.py file.md`), verified inside the headless
      compositor. Only the literal icon-click gesture remains human.
- [x] `LANG=de_DE.UTF-8 zeile ...` — verified 2026-09-11 in a real running
      window (headless compositor, widget-level): tooltips and titles show
      the German strings ("Theme und Schriften", "Inhaltsverzeichnis
      (Strg+T)"); the About dialog shows name/version.

## Publishing

- [x] Repository is private on GitHub (`DnaMes/zeile`) — confirmed as of
      this rename; re-check before any public-listing decision.
- [x] Tag `v0.2.0` and cut a GitHub release — done 2026-09-24
      (https://github.com/DnaMes/zeile/releases/tag/v0.2.0). Built and
      published locally (`git archive` tarball + `SHA256SUMS`, notes from
      CHANGELOG) because GitHub Actions is blocked by an account budget
      limit, which also keeps the release workflow from running. All
      checks were run locally first: 86 pytest (incl. the real headless
      GUI matrix), ruff, shellcheck, msgfmt, `check_version.py`; the
      extracted tarball passes 86 tests on its own.
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
