# zeile — Continuation Prompt

> **Verify state before trusting this document.** This file was written at
> the end of a session on 2026-09-11. Before acting on anything below:
> `git status`, `git log --oneline -10`, `git tag`, `gh run list --repo DnaMes/zeile`
> and read `HANDOFF.md` (its top section is the newest session report).
> The repository may have moved on since this was written.

You are continuing work on **zeile** — a small, fast, security-hardened GTK4
markdown viewer for Linux (single-file Python app, `/usr/bin/python3`, GTK4 +
WebKitGTK 6.0, pytest suite, GPL-3.0-or-later, repo `github.com/DnaMes/zeile`,
currently PRIVATE).

## Where things stand (as of 2026-09-11, end of day)

- **`v0.1.0` is released**: annotated tag + GitHub release + CHANGELOG cut.
- **CI is green** (`.github/workflows/ci.yml`: ruff + pytest + shellcheck).
- All previously identified **1.0-readiness blockers are fixed and pushed**
  (see `HANDOFF.md` top section): file-chooser launch without argument,
  window/zoom persistence with merge-safe settings writers, Auto-theme
  mid-session sync, visible print/PDF degradation when GTK4 print backends
  are missing (Arch gtk4 4.22 ships none), decide-policy deferral,
  accessible labels on all icon-only buttons.
- `tests/headless_gui.py` + `tests/test_headless_gui.py` run the GUI
  verification matrix inside a headless cage compositor (focus-safe,
  skips without cage/Wayland). Keep this harness fed — it caught real bugs
  that introspection-level tests could not.
- `packaging/PKGBUILD` exists with the real v0.1.0 sha256; the source URL
  resolves only once the repo goes public.

## What to do next (ordered)

1. Dogfood the installed app; the remaining human verifications
   (Nautilus double-click, print on a system WITH GTK4 print backends)
   fall out of that.
2. Watch CI; bump `actions/checkout@v4` → `@v5` when convenient.
3. Cut `v1.0.0` when the owner says so — the exact mechanical steps are
   in `HANDOFF.md`, section "Next steps", item 3. Do NOT bump the version
   without updating BOTH `pyproject.toml` and `zeile.py __version__`
   (hand-synced pair).

## Ground rules for this repo

- A `.md` file is untrusted input. Never weaken the sandbox
  (`enable-javascript-markup=False`, nh3 allowlist, strict CSP, ephemeral
  NetworkSession, decide-policy gate). `HANDOFF.md` + `README.md` Security
  section document every wall — verified, not assumed.
- GUI verification uses the headless cage harness
  (`WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 cage -d python3 …`),
  never the operator's desktop focus. For WebKit content use
  `webview.get_snapshot()`, not `grim` (WebKitGTK throttles occluded
  windows — grim shows a stale frame).
- Run `ruff check` + `pytest` + `shellcheck install.sh` before any commit.
- Only commit/push/tag when the task explicitly asks for it.
