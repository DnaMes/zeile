# zeile — Handoff

Older sessions (2026-09-10 to 2026-10-27 morning, v0.2.0 and v0.3.x release logs) are in
`.parachute/handoff-archive/2026-10-27.md`. Read it only on request.

## Goal

zeile (GTK4 + WebKitGTK markdown viewer, Python, GPL-3.0-or-later) is public at github.com/DnaMes/zeile
(since 2026-10-26) and packaged for Arch, Debian, Fedora and Flatpak. Keep it small, secure and
bilingual (German + English), and keep extending it carefully.

## Current Progress (2026-10-27, after the autonomous night session)

- **Released: v0.4.1** (tarball, `.deb` Debian 13, `.rpm` Fedora 43, SHA256SUMS). v0.4.0 was released earlier
  the same night; its rpm lacked `Requires: gobject-introspection` (ImportError on minimal Fedora), fixed in 0.4.1.
- Shipped since v0.3.1 (see CHANGELOG): malformed-input recovery, Mermaid error blocks, atomic draft-then-publish
  release workflow, hostile-document WebView test, German desktop/AppStream metadata, task-list fix, overflow check,
  man pages (EN/DE) + bash/zsh/fish completions, translated `--help`, F1 shortcut overlay, persisted reading width
  (narrow/standard/wide) that keeps the reader's passage in place, package smoke test that proves rendering,
  `scripts/flatpak-check.sh` (sandbox: read-only home, no network, sibling image renders), clean-container rpm check.
- Verified at 0.4.1 (observed): pytest 186 passed / 2 skipped; GUI matrix 25 checks; hosted CI green (test + Arch,
  Debian 13, Ubuntu 24.04, Fedora 43); `scripts/package-check.sh deb|rpm|arch` exit 0; `scripts/flatpak-check.sh` exit 0;
  published assets: `sha256sum -c` OK, tarball tests pass, downloaded rpm and deb installed in clean containers and
  smoke-tested (render OK); AUR PKGBUILD builds with makepkg; Flathub manifest builds from the tag archive.
- Branch `chore/14-pkgbuild-0.4.1` (PKGBUILD checksum for 0.4.1 + this HANDOFF) may still need shipping: check
  `git branch --show-current`, `git status`, `git log origin/main`.
- Issues: #9, #10, #14 on DnaMes/zeile (close after confirming main has everything); board AB#1766.

## Needs the owner (do NOT do autonomously)

- AUR: account + SSH key; files ready in `~/aur-staging/zeile/` (PKGBUILD + .SRCINFO, 0.4.1).
- Flathub: pull request with the owner's GitHub account; ready in `~/flathub-submission/com.erdlabs.zeile/`
  (manifest with archive source v0.4.1 + `python-deps.json`; GNOME 51 runtime hint from the linter is optional).
- erdlabs.com: catalogue entry with zeile screenshots is merged (erdlabs.com e014761) but NOT deployed
  (manual `wrangler deploy` in `websites/erdlabs.com/site`).
- Human checks (zeile issue #2): file-manager double-click, print/PDF on a system with GTK print backends,
  Flatpak on a real desktop.
- Any further release: ask Codex for an explicit GO first.

## Next ideas (not started)

Mermaid network isolation (needs mmdc installed to verify; fail closed; risk high); `--version` was DROPPED on
purpose (version only in About); recent files, front-matter table, emoji, open dialog/stdin, open-in-editor,
wrap toggle were rejected by Codex (privacy/scope). Possible: Ubuntu package route for nh3, Nix/COPR/PPA only on demand,
GNOME 51 runtime for the Flatpak, keycap styling for the F1 overlay.

## How to work on this repo (recipe that worked)

- Workers on non-Claude lanes in PLAIN CLONES (not `git worktree`): the git-ops post-merge hook removes worktrees of
  merged branches, which killed one worker. `git clone -q . ~/.worktrees/zeile-work/<name>`;
  `cd <clone> && delegate "$(cat preamble.md task.md)" --type auto --role cheap-build > out.md` (briefs from this
  night were in `/tmp/zeile-night/`: they are gone after a reboot; the rules are: one bounded deliverable, no commit,
  tests for every change, strings via gettext + po/de.po, no xgettext regeneration, cap 900 s per hop).
- Integrate: `git add -N .` + `git diff` in the clone, `git apply --3way` on a new branch in the main checkout
  (exclude binaries: rebuild `locale/de/LC_MESSAGES/zeile.mo` with `msgfmt po/de.po -o ...`; keep both sides in
  po/ conflicts and check every entry has a msgstr).
- Verify yourself: `python3 -m pytest -q`; `~/.local/bin/ruff check . && ~/.local/bin/ruff format --check .`;
  `shellcheck install.sh scripts/*.sh packaging/*.sh packaging/*/*.sh`; GUI matrix
  `WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 cage -d -- /usr/bin/python3 tests/headless_gui.py`;
  `scripts/package-check.sh deb|rpm|arch`; `scripts/flatpak-check.sh` (refuses to run over an installed
  com.erdlabs.zeile or existing `~/.var/app/com.erdlabs.zeile`).
- Review with Codex: `(echo prompt; git diff HEAD) | delegate --type review` (its BLOCKs were real every time);
  ship through the git-ops agent (main thread may not commit/push) with `review-gate`; ALWAYS wait for hosted CI on
  main afterwards. Do not trust "gate APPROVE" alone: CI failed three times after gate approvals tonight.
- Lessons: hosted CI installs deps with `pip --user` and tests that set HOME to a temp dir lose them (pass
  PYTHONUSERBASE); WebKitGTK scroll anchoring differs between Arch and Debian/Ubuntu/Fedora (negative controls must
  be run on the distro matrix, not only on the laptop); installing a package in the same container as build tools
  masks missing Requires; `pkill -f <pattern>` can kill your own shell when the pattern is in the command line;
  public repos must not use self-hosted runners; `gh release download/upload/view` work on DRAFT releases by tag.

generated by context-parachute v1.4.1
