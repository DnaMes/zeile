# Windows, macOS and Linux breadth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build zeile for Windows, macOS and every Linux distribution from one platform-neutral core, without giving up the security model or the small download.

**Architecture:** Three layers. A platform-neutral core (`documents.py`, `preferences.py`, `launch.py`) that never imports `gi` and holds the markdown pipeline, the settings store and the launch plan. A Linux shell (`zeile.py`, GTK4 + WebKitGTK 6.0, unchanged) that stays the primary target. A second shell (`zeile_desktop.py`, pywebview) that drives the operating system's own webview — WebView2 on Windows, WKWebView on macOS — so no browser engine is bundled.

**Tech Stack:** Python 3.11+, python-markdown, nh3, Pygments, pymdown-extensions (core); GTK4/PyGObject/WebKitGTK 6.0 (Linux shell); pywebview 6.x + pythonnet/WinForms (Windows), pyobjc/Cocoa (macOS); PyInstaller for binaries; pytest; GitHub Actions standard runners (`ubuntu-latest`, `windows-latest`, `macos-latest`).

**Spec:** issue #21 (evaluation, facts and the rejected routes: Windows containers on a Linux host, Docker-OSX, MSYS2/gvsbuild WebKitGTK, Homebrew `webkitgtk`).

## Global Constraints

- Document JavaScript never runs. The invariant is enforced by three independent layers and each one is tested: native webview setting where a platform exposes it, `nh3` sanitizer allowlist, and the document's own Content-Security-Policy (`default-src 'none'; img-src 'self' data:; font-src 'self' data:; style-src 'unsafe-inline'`).
- No network egress. CSP `default-src 'none'` blocks `connect-src`, `img-src 'self' data:` blocks beacons; the navigation policy denies everything except the current file and an explicit external open.
- No advertising, no telemetry, no crash reporting that leaves the device.
- English is the template language; German ships in the same change (`po/de.po`, `values`-free: the app uses `gettext`).
- Core modules import only the standard library plus `markdown`, `nh3`, `pymdown-extensions`, `pygments`. `import gi` is forbidden outside `zeile.py`; the same goes for `webview` outside `zeile_desktop.py`. `tests/test_core_isolation.py` enforces this.
- Version lives in three places (`pyproject.toml`, `zeile.py`, `packaging/PKGBUILD`) and is bumped only by `scripts/bump-version.sh`-equivalent edits plus `scripts/check_version.py`.
- No cross-compiled or emulated artefacts. A package is built on the platform it targets, on a native runner.
- Every release artefact is built from a `vX.Y.Z` tag and only after `ruff check .`, `ruff format --check .`, `pytest` and `shellcheck` pass.

## Review Focus

- A markdown file whose name starts with `-` or contains a newline is opened from a shell or a file manager: the path must reach the viewer as one argument, on all three platforms (`argv` handling differs: Windows has no shebang and no `--` conventions in `.lnk` targets).
- A 40 MB markdown file with a mermaid fence and 2000 code blocks: the first paint must not block on `mmdc`, and the document must not be rendered twice when the file changes mid-render.
- A `.md` file with a Windows path (`C:\Users\…`) inside a link: navigation must not treat the colon as a URI scheme and hand the path to the browser.
- The file watcher on macOS (FSEvents) and Windows (`ReadDirectoryChangesW`) reports edits as rename+create or as two events: the view must not flicker to a blank page between them.
- A user with no WebView2 runtime on Windows 10 and no `mmdc` anywhere: the app must start, explain the one missing dependency in German and English, and stay usable.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `documents.py` | markdown → HTML: frontmatter, sanitizer allowlist, CSP, code-block enhancement, document stats, TOC, `render()`, link classification |
| `preferences.py` | settings store and option tables: theme, fonts, reading width, window state; tolerant load/save |
| `launch.py` | launch sequence plan, phase opacity, intro-seen flag |
| `zeile.py` | Linux shell: GTK4 window, WebKitGTK view, menus, search bar, splash, print |
| `zeile_desktop.py` | Windows/macOS shell: pywebview window, native menus, platform webview hardening |
| `tests/test_core_isolation.py` | guards: no `gi`/`webview` import outside the shells |

---

### Task 1: Extract the platform-neutral core

**Files:**
- Create: `documents.py`, `preferences.py`, `launch.py`
- Modify: `zeile.py:1-800` (delete the moved code, import instead), `zeile.py:919` onward untouched
- Test: `tests/test_zeile.py`, `tests/test_robustness.py`, `tests/test_launch_sequence.py` (import from the new modules), `tests/test_core_isolation.py` (new)

**Interfaces:**
- Consumes: nothing.
- Produces: `documents.render(text, *, theme, body_font, code_font, reading_width, source_name, base_dir, toc=None) -> str`, `documents.build_document(...) -> str`, `documents.sanitize_html(body: str) -> str`, `documents.enhance_code_blocks(body: str) -> tuple[str, list[str]]`, `documents.read_asset(name: str) -> str`, `documents.compute_document_stats(text: str) -> DocumentStats`, `documents.flatten_toc(tokens, depth=2) -> list[tuple[int, str, str]]`, `documents.classify_local_target(target: Path, document: Path) -> str`, `documents.CSP`, `documents.ALLOWED_*`; `preferences.load_settings(*, path=None) -> dict[str, str]`, `preferences.save_settings(settings, *, path=None) -> None`, `preferences.THEME_OPTIONS` and the other option tables, `preferences.is_theme_dark(theme_id, *, fallback) -> bool`; `launch.LaunchPhase`, `launch.plan_launch_sequence(*, intro_seen, animations) -> list[LaunchPhase]`, `launch.phase_opacity(phase, t_ms) -> float`, `launch.launch_asset_path(asset) -> Path`.

- [x] **Step 1: Write the failing isolation test**

```python
# tests/test_core_isolation.py
"""The core must import on Windows and macOS: no gi, no webview, ever."""
import re
from pathlib import Path

CORE = ("documents.py", "preferences.py", "launch.py")
GUI_ONLY = re.compile(r"^\s*(import|from)\s+(gi|webview)\b", re.MULTILINE)

def test_core_modules_do_not_import_a_gui_toolkit() -> None:
    for name in CORE:
        source = Path(name).read_text(encoding="utf-8")
        assert not GUI_ONLY.search(source), f"{name} imports a GUI toolkit"
```

- [x] **Step 2: Run it, expect failure**

Run: `pytest tests/test_core_isolation.py -v` — Expected: FAIL, `FileNotFoundError: documents.py`.

- [x] **Step 3: Create `documents.py`** by moving `zeile.py` lines for `_strip_frontmatter`, `_visible_text`, `DocumentStats`, `compute_document_stats`, `_CSP`, `_ALLOWED_TAGS`, `_ALLOWED_ATTRIBUTES`, `sanitize_html`, `_PRE_BLOCK_RE`, `_COPY_ICONS`, `_pre_plain_text`, `enhance_code_blocks`, `read_asset`, `render_body`, `build_document`, `render`, `flatten_toc`, `_MARKDOWN_SUFFIXES`, `_DIRECT_LOAD_SUFFIXES`, `classify_local_target`, plus `EXTENSIONS`/`EXTENSION_CONFIGS` and the `gettext` setup they need.

- [x] **Step 4: Create `preferences.py`** with the settings block (`_default_settings_path`, `_coerce_theme`, `_coerce_font`, `_coerce_reading_width`, `_as_finite_float`, `_coerce_number`, `is_theme_dark`, `load_settings`, `save_settings`, `THEME_OPTIONS`, `BODY_FONT_OPTIONS`, `CODE_FONT_OPTIONS`, `READING_WIDTH_OPTIONS`, `_DEFAULT_SETTINGS`, `_theme_label`, `_font_label`).

- [x] **Step 5: Create `launch.py`** with `LaunchPhase`, `launch_asset_path`, `plan_launch_sequence`, `phase_opacity`, `_INTRO_PHASE`, `_LOGO_PHASE`.

- [x] **Step 6: Make `zeile.py` a shell** — import the moved names (`from documents import …`, `from preferences import …`, `from launch import …`) so every existing `zeile.X` reference, including the ones in tests and `install.sh`'s launcher assumptions, keeps working.

- [x] **Step 7: Point the pure tests at the new modules** (`test_zeile.py`, `test_robustness.py`, `test_launch_sequence.py`) so they no longer need `gi`.

- [x] **Step 8: Run the suite** — Expected: 186 passed, 2 skipped, plus the new isolation test.

- [x] **Step 9: Commit** — `refactor: split the platform-neutral core out of the GTK shell`.

### Task 2: Prove the core on Windows and macOS in CI

**Files:**
- Modify: `.github/workflows/ci.yml` (new job `core`)
- Test: the same suite, on runners that are not Linux

**Interfaces:**
- Consumes: Task 1's modules.
- Produces: a green `core (windows-latest)` and `core (macos-latest)` job — the first real platform signal for every later task.

- [x] **Step 1: Add the job** — matrix `os: [ubuntu-latest, windows-latest, macos-latest]`, `pip install markdown nh3 pymdown-extensions pygments pytest`, then `pytest tests/test_zeile.py tests/test_robustness.py tests/test_launch_sequence.py tests/test_code_lang.py tests/test_markdown_ext.py tests/test_mermaid_render.py tests/test_core_isolation.py -q`.
- [x] **Step 2: Watch it fail on something real** (encoding, path separator, `gettext`) and fix only what is genuinely platform-specific.
- [x] **Step 3: Commit** — `ci: run the platform-neutral core tests on Windows and macOS`.

### Task 3: Draw the view boundary (interface, no second shell yet)

**Files:**
- Create: `view.py` (protocol + shared navigation policy decisions)
- Modify: `documents.py` (nothing), `zeile.py` (implement the protocol)
- Test: `tests/test_view_policy.py`

**Interfaces:**
- Consumes: `documents.classify_local_target`.
- Produces: `view.View` protocol with `show_document(html: str) -> None`, `set_title(text: str) -> None`, `run_script(js: str) -> None`, `show_error(message: str) -> None`, `quit() -> None`; `view.NavigationDecision` (`load`, `navigate`, `external`, `ignore`); `view.decide(uri: str, document: Path) -> NavigationDecision`.

- [ ] **Step 1: Write `tests/test_view_policy.py`** pinning the five decisions (current file, other local `.md`, local image, remote URL, `zeile-copy://`, `javascript:`).
- [ ] **Step 2: Implement `view.decide`** and make `zeile.py`'s policy handler delegate to it; the GTK handler keeps only the GTK part.
- [ ] **Step 3: Run the suite**, expect the existing GUI tests still green (the policy moved, the behaviour did not).
- [ ] **Step 4: Commit** — `refactor: move the navigation policy behind a tested boundary`.

### Task 4: The Windows/macOS shell

**Files:**
- Create: `zeile_desktop.py`, `tests/test_desktop_shell.py` (pure parts only), `packaging/desktop/zeile.spec` (PyInstaller)
- Modify: `install.sh` (unchanged on Linux), `po/zeile.pot` + `po/de.po`

**Interfaces:**
- Consumes: `documents`, `preferences`, `launch`, `view.decide`.
- Produces: `zeile_desktop.main(argv: list[str]) -> int`; an entry point that the PyInstaller spec and the installers call instead of `zeile.py`.

- [ ] **Step 1: Write the failing test** — `tests/test_desktop_shell.py` asserts `zeile_desktop.build_html(path)` returns the same bytes as `documents.render` for the same input, and that `zeile_desktop.menu_items()` is identical on both platforms (one menu definition, two renderings).
- [ ] **Step 2: Implement the shell** with pywebview: `webview.create_window(..., html=…)`, native menu, keyboard shortcuts (open, reload, find, zoom, theme, print), file watcher via `watchdog`-free polling on a `threading.Timer` (Windows/macOS watcher semantics differ; polling a `st_mtime_ns` is the boring, correct answer for one file).
- [ ] **Step 3: Harden the platform webview** — Windows: `CoreWebView2Settings.IsScriptEnabled = False`, `AreHostObjectsAllowed = False`, `IsWebMessageEnabled = False`, `AreDefaultContextMenusEnabled = False`; macOS: `WKWebpagePreferences.allowsContentJavaScript = False`. Set them through `window.native` and fail closed: if the attribute is missing, refuse to render the document and show the error in German and English.
- [ ] **Step 4: Verify the invariant on real machines** — a CI test renders a document containing `<script>window.__pwned=1</script>` and a `<img src="http://127.0.0.1:9/x.png">`, then asserts no script ran and no request was made (local test server counts hits).
- [ ] **Step 5: Commit** — `feat: a Windows and macOS shell that drives the system webview`.

### Task 5: Packages on native runners

**Files:**
- Create: `.github/workflows/build-desktop.yml`, `packaging/windows/README.md`, `packaging/macos/README.md`
- Modify: `.github/workflows/release.yml` (attach the artefacts on `v*` tags)

**Interfaces:**
- Consumes: Task 4's entry point.
- Produces: `zeile-<version>-windows-x64.zip` and `zeile-<version>-macos-arm64.dmg`, built on `windows-latest` and `macos-latest`, attached to the release by the existing `packages` flow.

- [ ] **Step 1: Windows job** — PyInstaller one-dir build, zip artefact. Document the two honest consequences of shipping unsigned: SmartScreen warns until the binary has reputation, and a code-signing certificate is optional, not required.
- [ ] **Step 2: macOS job** — PyInstaller `.app`, DMG via `hdiutil`, arm64 and universal2 as separate artefacts. Document notarisation: needs the Apple Developer Program (99 USD/yr); without it Gatekeeper requires `xattr -d com.apple.quarantine`.
- [ ] **Step 3: Wire it into the release** — the release workflow downloads both artefacts and uploads them with `SHA256SUMS`, exactly like the deb/rpm job does today.
- [ ] **Step 4: Update the docs** — README "Platform support", `PRIVACY.md` (WebView2 and WKWebView have their own storage and telemetry defaults; state which are disabled), CHANGELOG.
- [ ] **Step 5: Commit** — `feat: build Windows and macOS packages on native runners`.

### Task 6: Linux breadth

**Files:**
- Create: `packaging/appimage/build-appimage.sh`
- Modify: `packaging/stage.sh` (reuse it), README (distribution table), `.github/workflows/release.yml`

- [ ] **Step 1: AppImage** — stage with the existing `packaging/stage.sh`, wrap with `appimagetool` in a Debian 13 container, verify it starts under `cage` in the same container (`packaging/smoke.sh` already does this for the installed tree).
- [ ] **Step 2: Publish Flatpak** — the manifest exists (`packaging/flatpak/`); Flathub needs the owner's account, so this stays a documented manual step.
- [ ] **Step 3: State the coverage in the README** — Arch/AUR, Debian/Ubuntu, Fedora/RHEL/openSUSE (rpm), Flatpak, AppImage, source tarball.
- [ ] **Step 4: Commit** — `feat: ship an AppImage for distributions without a package`.

---

## Verification

- `ruff check .`, `ruff format --check .`, `pytest`, `shellcheck install.sh scripts/*.sh packaging/*.sh packaging/*/*.sh`
- `.github/workflows/ci.yml` green on `ubuntu-latest`, `windows-latest`, `macos-latest`
- A real, unsigned build installed on a real Windows 10 machine and a real Mac (or the closest available: a Windows VM here, and the macOS runner's own smoke step — no macOS VM on this host is legal)
- The script invariant test fails loudly if a future webview upgrade stops honouring the setting
