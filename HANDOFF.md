# zeile — Handoff

Older sessions (2026-09-10 to 2026-10-27 morning, v0.2.0 and v0.3.x release logs) moved to
`.parachute/handoff-archive/2026-10-27.md`. Read it only on request.

## Goal

zeile (GTK4 + WebKitGTK markdown viewer, Python, GPL-3.0-or-later, public at github.com/DnaMes/zeile
since 2026-10-26) is released as v0.3.1 and packaged (tarball, .deb, .rpm, Arch PKGBUILD, Flatpak).
Owner went to bed on 2026-10-27 and asked for a fully autonomous night session: remove open items,
extend zeile, use NON-Claude lanes (DeepSeek via Command Code, OpenCode Go, OpenRouter, MiniMax) for
implementation, decide everything together with Codex. Claude weekly limit is ~94% used: keep the
orchestrator's own token use low, route work to workers.

## Current Progress (state at 2026-10-27 ~02:20)

- v0.3.1 released 2026-10-27 (tarball, deb, rpm, SHA256SUMS). Unreleased work on `main` since then
  (listed in CHANGELOG `[Unreleased]`): malformed-input recovery, Mermaid error blocks, screenshot
  failures fatal, atomic draft-then-publish release workflow, hostile-document WebView test,
  German desktop/AppStream metadata, task-list checkbox fix, overflow check, man pages (EN/DE) and
  bash/zsh/fish completions, translated `--help`, F1 shortcut overlay. `main` = c5bc73a (+ smoke commit
  in flight). 179 pytest, GUI matrix 23 checks, ruff, shellcheck all green at last run.
- IN FLIGHT: git-ops agent `aec81d744b7b5a41d` is shipping branch `feat/10-batch-d1`
  (packaging/smoke_render.py + smoke.sh + tests/test_smoke_render.py: package smoke proves the viewer renders)
  through review-gate. Check `git log origin/main`, `git branch --show-current` (checkout may still be on
  feat/10-batch-d1) and `git worktree list` first.
- IN FLIGHT: worker for the persisted reading-width setting (narrow/standard/wide) in worktree
  `~/.worktrees/zeile/feat-10-reading-width`, output file `/tmp/zeile-night/out-width.md`
  (ends with a line `exit N` when finished). Not integrated yet.
- This HANDOFF.md, `.parachute/*` and a new AGENTS.md block are UNCOMMITTED in the main checkout:
  commit them with the next git-ops ship (explicit paths).
- Issues: #9 (night hardening), #10 (reader polish + shell integration) open on DnaMes/zeile; board AB#1766.

## Next Steps (ordered)

1. Wait for the git-ops ship of d1; then run the real proof on merged main:
   `scripts/package-check.sh deb`, `rpm`, `arch` (each builds, installs, runs smoke incl. the new render check;
   Arch mirror is flaky: script already retries and disables pacman download timeouts).
2. Integrate the reading-width worker: patch from its worktree (`git -C <wt> add -N .; git -C <wt> diff`),
   `git apply --3way` onto a new branch `feat/10-batch-d2` in the main checkout, resolve po/de.po + po/zeile.pot
   conflicts by keeping both sides (check each entry has a msgstr), `msgfmt po/de.po -o locale/de/LC_MESSAGES/zeile.mo`,
   run pytest, ruff, shellcheck, GUI matrix, get a Codex review (`(echo prompt; git diff HEAD) | delegate --type review`),
   fix findings, ship via git-ops. Add CHANGELOG line.
3. New worker: `scripts/flatpak-check.sh` (build Flatpak, run packaging/smoke_render.py inside the sandbox with
   ZEILE_APP_DIR=/app/share/zeile, sibling image under `--filesystem=home:ro` loads, write to home fails, no network
   reachability to a host listener, always uninstall app + remove ~/.var/app/com.erdlabs.zeile in a trap).
4. Small follow-ups (all noted by review gates): F1 window `destroy_with_parent=True` (zeile.py ~1771);
   install.sh prints "installed" even when it skipped a foreign file; tests hard-code 18 themes;
   reconcile RELEASE.md (obsolete "private repository" lines); stretch: Mermaid network isolation (needs mmdc
   installed to verify, risk H: fail closed).
5. Release decision: Codex said NO GO for v0.4.0 tonight by default. Rule for a tag: human-grade review done,
   full tests + real GUI/distro/package checks green, security/error findings resolved, EN/DE strings complete,
   permissions justified, versions synchronized (pyproject.toml, zeile.py `__version__`, packaging/PKGBUILD
   `pkgver`, AppStream release entry, CHANGELOG), extracted artifacts and checksums verified. Ask Codex for an
   explicit GO before tagging; `scripts/check_version.py X.Y.Z --tag vX.Y.Z` must pass.
6. Morning report to the owner (German): what shipped, what is verified, what needs the owner (below).

## Needs the owner (do NOT do autonomously)

AUR account + SSH key (files ready: `~/aur-staging/zeile/`); Flathub pull request (ready:
`~/flathub-submission/com.erdlabs.zeile/`); deploy of erdlabs.com (catalogue with zeile screenshots merged as
erdlabs.com e014761 but NOT deployed, manual `wrangler deploy`); human check of file-manager double-click and
print/PDF (zeile issue #2); any tag/release if Codex does not say GO. Never: production deploys, new accounts,
widening CSP/sanitizer/permissions, telemetry, visible windows, `git push --force` on main.

## How the night loop works (reuse it)

- Briefs live in `/tmp/zeile-night/`: `preamble.md` (rules) + `task-*.md`; start a worker per git worktree:
  `cd ~/.worktrees/zeile/<dir> && delegate "$(cat preamble.md task-X.md)" --type auto --role cheap-build > out-X.md`
  (jev picks cursor/opencode-go/glm/qwen/mimo; cap 900 s per hop; one worker hit it twice: split tasks smaller and
  forbid regenerating po/zeile.pot with xgettext). Create worktrees from main with
  `git worktree add ~/.worktrees/zeile/<branch-dashed> -b <branch> main`.
- Integrate: `git add -N .` + `git diff` in the worktree, `git apply --3way` in the main checkout on a new branch;
  `git diff --binary` is needed for binaries (the .mo is rebuilt with msgfmt instead).
- Verify yourself (worker reports are not evidence): `python3 -m pytest -q`; `~/.local/bin/ruff check . && ~/.local/bin/ruff format --check .`;
  `shellcheck install.sh scripts/*.sh packaging/*.sh packaging/*/*.sh`; GUI matrix
  `WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 cage -d -- /usr/bin/python3 tests/headless_gui.py`.
- Review: Codex via `delegate --type review` (BLOCK findings were real every time; fix, re-review). Ship: git-ops agent
  (main thread may not commit/push): commits with `Refs #N` + Claude-Session trailer, `review-gate --repo R --sha TIP`
  (fast-forward only), then cleanup of integrated worktrees/branches. Give git-ops EXACT worktrees to remove:
  its post-merge hook once removed a peer's worktree.
- Codex decisions are in `/tmp/zeile-opinions/night-codex.md` (backlog) and `night-features.md` (feature list:
  dropped --version, front matter table, emoji, open dialog/stdin, open-in-editor, recent files, link marker, wrap toggle).
- Decision recorded: Codex's finding "install.sh follows symlinked ancestors under HOME" was rejected on purpose
  (the user installer follows the user's own symlinks, e.g. dotfile managers); ownership marker
  `zeile-installer-owned` protects foreign files instead.
- Lessons: public repos must not use self-hosted runners; `gh release download/upload/view` work on DRAFT releases
  by tag; deleting a draft with `--cleanup-tag` prints a harmless 422; argparse's own "usage/options" words stay English
  under LANGUAGE=de (known limitation).

## Files changed this session (all on main unless noted)

`zeile.py` (robust settings/doc reading, `classify_local_target`, translated --help, F1 overlay, About icon fallback,
start-sequence fallback), `mermaid_render.py` + `markdown_ext.py` (error blocks), `scripts/screenshots.py`,
`scripts/package-check.sh`, `packaging/{stage.sh,smoke.sh,smoke_render.py (in flight),flatpak/*,debian/build-deb.sh,rpm/*}`,
`man/`, `completions/`, `install.sh`, `.github/workflows/{ci,release}.yml`, `assets/style.css`, `po/*`, `locale/de/.../zeile.mo`,
tests (`test_robustness`, `test_screenshots`, `test_release_workflow`, `test_packaging_metadata`, `test_shell_integration`,
`test_cli`, `headless_gui.py` checks), `README.md`, `CHANGELOG.md`, `RELEASE.md`, `PRIVACY.md`.
Outside the repo: `~/aur-staging/zeile/`, `~/flathub-submission/com.erdlabs.zeile/`; website repo erdlabs.com e014761.

generated by context-parachute v1.4.1
