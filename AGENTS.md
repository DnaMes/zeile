# zeile

## Context

A small GTK4 markdown viewer for Linux with optional Mermaid diagram support.
It renders a `.md` file, watches it for changes and re-renders on save. A
markdown file is treated as untrusted (the app is the default `text/markdown`
handler), so rendering runs with document JavaScript disabled, an explicit
HTML sanitizer allowlist, no persistent storage and no network access.

## Stack

- Python 3.11+ (`requires-python = ">=3.11"`)
- GTK4 via PyGObject, WebKitGTK 6.0
- python-markdown, Pygments, nh3 (ammonia), pymdown-extensions
- Ruff (lint, line-length 92), pytest, shellcheck
- Optional: `@mermaid-js/mermaid-cli` (`mmdc`) for `--enable-mermaid`

## Commands

- Run: `./install.sh` then `zeile README.md` (the launcher pins `/usr/bin/python3`)
- Test: `pytest`
- Lint: `ruff check .`
- Version consistency: `python3 scripts/check_version.py`
- Release: push a `vX.Y.Z` tag; `.github/workflows/release.yml` validates and publishes

## Layout

- `zeile.py` — the application
- `markdown_ext.py` — mermaid fence extraction and unlabeled-fence hints
- `code_lang.py` — rule-based language detection for untagged code blocks
- `mermaid_render.py` — `mmdc` subprocess wrapper with content-hash cache
- `assets/` — `style.css`, `themes.css`, icon
- `po/`, `locale/` — German translation source and compiled catalogs
- `tests/` — pytest suite, including headless GTK checks
- `packaging/PKGBUILD`, `scripts/check_version.py`, `.github/workflows/`

## Conventions

- See `~/projects/docs/agent-policy.md` for the binding policy.
- Branches: `<typ>/<issue-nr>-<topic>` (issue number required).
- Conventional Commits: feat:, fix:, chore:, docs:, refactor:, test:.
- Keep the three version copies (`pyproject.toml`, `zeile.py`, `packaging/PKGBUILD`) in sync; the release workflow refuses drift.
- Update CHANGELOG.md (Keep a Changelog) and keep SemVer.
- Linux is the only supported release target; do not produce fake Windows/macOS artifacts.

## Don't

- Do not commit secrets (`.env`, `*.pem`, `*.key`).
- Do not re-enable document JavaScript or widen the sanitizer allowlist without a security review.
- Do not force-push to main/master.
