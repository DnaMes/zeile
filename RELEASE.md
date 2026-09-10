# Release Checklist — zeile

**This project does not ship to the Play Store.** It is a Linux desktop
application distributed as source, so most of the label's release checklist
does not apply. What remains is the licensing, versioning, security, and
documentation work every erdlabs project owes before its repository goes
public.

Current version: **0.1.0** (`pyproject.toml`). Never tagged, never released.

**Version drift risk**: `pyproject.toml`'s `version` and `zeile.py`'s
`__version__` (shown in the About dialog) are two hand-synced copies, not
one source of truth — this bare-Python project has no build step to derive
one from the other the way `docs/VERSIONING.md`'s `versionCode` derivation
does for the Android apps in this label. Check both are still equal before
tagging; a future bump script for this project should read one and write
the other, not update them independently.

---

## Blockers

- [ ] **Never tagged.** Per `docs/VERSIONING.md`, a release needs an
      annotated tag; the first one is `v0.1.0`.
- [ ] **No real Mermaid diagram has been rendered end-to-end.** `mmdc`
      (mermaid-cli) is not installed on the machine this was built on —
      it's an opt-in ~300 MB Puppeteer/Chromium dependency, and installing
      it wasn't authorized mid-implementation. Before release: install it,
      render a real diagram with `--enable-mermaid`, and visually confirm
      it displays correctly (not just that the code path doesn't crash).
- [ ] **No interactive GTK UI feature has been clicked through by a
      human.** Ctrl+F, the TOC overlay, back/forward link navigation,
      print, and PDF export were all verified via API introspection and a
      no-crash smoke test, not by a person using them. See HANDOFF.md's
      per-phase notes for exactly what was and wasn't checked.

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
- [ ] `shellcheck install.sh` — clean as of 2026-09-10, re-check after any
      further edit.
- [ ] Install on a clean machine (no `python-nh3`/`python-pymdown-extensions`
      pre-installed) — verify `install.sh` fails with the specific missing
      package name, not a generic error, and that installing the named
      package and re-running actually works.
- [ ] `./install.sh --uninstall` then `./install.sh` again — verify a full
      round trip leaves the system in the same state as a fresh install
      (tested once during Phase 8, but re-verify after any install.sh edit).
- [ ] Actually double-click a `.md` file in a file manager after install —
      every verification so far has launched via CLI.
- [ ] `LANG=de_DE.UTF-8 zeile ...` — verify the German translations
      actually appear in a real running window (verified only at the
      Python/gettext level, not by looking at the UI).

## Publishing

- [ ] Repository is private on GitHub (`DnaMes/zeile`) — confirmed as of
      this rename; re-check before any public-listing decision.
- [ ] Tag `v0.1.0` and cut a GitHub release, once the blockers above close.

## Not applicable

Play Console account, testers, AAB, target API level, Data Safety form,
content rating, store screenshots, feature graphic, F-Droid. None of these
apply to a desktop application distributed as source.
