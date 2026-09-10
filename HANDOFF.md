# zeile — Handoff

Created 2026-09-10. Renamed from `mdview` to `zeile` same day (name collision
research: `mdview` clashes on PyPI, npm, crates.io, AUR and a 144★ GitHub
project — see the full plan).

## Current Task

Executing the plan at `~/.claude/plans/hi-hier-wa-rein-humming-kahan.md`
(security hardening, Mermaid pre-render rewrite, feature fixes, i18n,
release docs — phased so `main` stays buildable after every commit).

Ran fully autonomously per operator instruction (2026-09-10): finish all
remaining phases, commit each, no per-phase check-in, shut the machine down
when done. Git history is the source of truth for what actually landed.

**All 8 phases done, plus one post-release bug found and fixed
(2026-09-11): the operator opened a `.md` file and got a fully black
window, no content.** This is exactly the failure mode the "Not verified"
section below warned about — every phase-5-through-8 verification launched
via CLI with a `timeout`+exit-code check, never an actual screenshot. First
screenshot ever taken of this app (via `grim`) immediately showed the bug.

**Root cause** (bisected by re-implementing pieces of `Viewer.__init__` in
isolated throwaway scripts until one reproduced it): Phase 5 restructured
the window's child from a bare `Gtk.ScrolledWindow` (which a
`Gtk.ApplicationWindow` always allocates 100% of its own space to) into a
`Gtk.Box` holding the new search bar plus that same `ScrolledWindow`. Only
`box.set_vexpand(True)` was set — on the *Box*, which only affects how the
Box itself is allocated space by the window, not how the Box then
distributes that space to its own children. Without `vexpand`/`hexpand` on
the `ScrolledWindow` itself, GTK4 gives it its natural (minimum) size
inside the Box, leaving the rest of the window's area allocated to nothing
— unpainted, rendering as black. Fixed with two lines
(`scroller.set_vexpand(True)`; `scroller.set_hexpand(True)`), verified by
reproducing the black screen in isolation, applying the exact same two
lines, and confirming a real rendered document appears both in an isolated
test and in the actual `zeile.py`.

**Lesson, stated so it doesn't repeat**: "the process didn't crash" is not
"it works" for a GUI. Every future phase that touches window layout gets a
`grim` screenshot before being called done, not just a `timeout`+exit-code
check.

What's NOT done — see "Not verified, next human session" at the bottom of
this file — is everything that genuinely needed a person clicking through a
GUI or installing a 300 MB opt-in dependency, neither of which this session
could
do for itself.

## Files Changed (Phase 8 — the last one)

- `zeile.py`: `gettext` wired up (`_ = gettext.translation("zeile",
  localedir=.../locale, fallback=True).gettext` — `fallback=True` so a
  missing translation is never a hard error, just English). Every
  user-facing tooltip/dialog-title/error string wrapped in `_()`
  (`argparse` help text deliberately left English — developer/CLI-facing,
  matches the erdlabs convention that log/developer output stays English).
  `__version__ = "0.1.0"` and a `Gtk.AboutDialog` (header "About zeile"
  button) showing it, program name, licence, and a link to erdlabs.com.
- `po/zeile.pot` (extracted via `xgettext`, 10 strings — matches what was
  actually wrapped, verified by re-running `xgettext` after the code
  change and diffing), `po/de.po` (translated by hand), compiled to
  `locale/de/LC_MESSAGES/zeile.mo` via `msgfmt --check` (clean) and
  committed — so `python3 zeile.py` works with German out of the box even
  without running `install.sh` first. **Verified end-to-end, not just that
  it compiles**: `LANG=de_DE.UTF-8 LANGUAGE=de python3 -c "import zeile;
  print(zeile._('Reload (Ctrl+R)'))"` printed `Neu laden (Strg+R)`; the
  default locale on this machine printed the English original unchanged.
- `install.sh`: dependency check for `python-gobject`/`webkitgtk-6.0`/
  `python-markdown`/`python-nh3`/`python-pymdown-extensions`, each
  failure naming the exact `pacman` package to install (verified both the
  pass-silently path with all deps present, and the fail-with-clear-message
  path with a synthetic missing command); `--uninstall` (removes exactly
  the 3 files this script writes, leaves the mime default alone rather than
  guessing what to restore it to); the generated launcher now checks its
  own target file exists before exec'ing it, with a message naming the
  path, instead of a bare Python traceback if the repo ever moves; compiles
  `po/*.po` to `locale/` on install if `msgfmt` is present. **Verified with
  a real round trip**: install -> launcher runs the app with no crash ->
  uninstall removes exactly the 3 files -> reinstall works again.
  `shellcheck install.sh` clean.
- `ASSETS.md` (new), `CHANGELOG.md` (new, reconstructed from `git log`),
  `PRIVACY.md` (new — the "no network call in our own code" claim is a
  literal, currently-true `grep` command, re-run at write time to confirm),
  `RELEASE.md` (new — an honest checklist, most boxes checked, several
  explicitly left open with the reason).
- `README.md`: Internationalization section, links to the four new docs,
  `po/de.po`/`--uninstall` in the Files table.

## Not verified, next human session

Everything below needs a person, a display, or a large opt-in dependency —
none of which this autonomous pass had:

1. **Install `mmdc`** (`npm install -g @mermaid-js/mermaid-cli`, ~300 MB)
   and render a real `--enable-mermaid` diagram. Confirm it displays
   correctly, and that the `htmlLabels: false` config actually suppresses
   `<foreignObject>` (sourced from two independent external reports, never
   directly observed).
2. **Click through the GUI**: Ctrl+F search, the TOC overlay, a real local
   `.md`-to-`.md` link click (does it actually navigate and does
   Alt+Left actually go back?), Ctrl+P, the PDF export button, the About
   dialog, `LANG=de_DE.UTF-8 zeile ...` and actually read the German UI.
   Every one of these was verified at the API-call level (introspection)
   and the app launches without a traceback against a crafted test
   document, but nobody has watched any of it happen on screen.

   **Check this specific one first**: `_on_decide_policy` calls
   `self.navigate_to(target)` — which calls `self.reload()`, which calls
   `self.webview.load_html()` — synchronously, from inside the
   `decide-policy` signal handler, while WebKit is still resolving that
   very policy decision. Re-entering `load_html()` mid-callback is a known
   fragile pattern in WebKitGTK. If clicking a local `.md` link misbehaves
   (doesn't navigate, freezes, or double-loads), defer the call with
   `GLib.idle_add(lambda: self.navigate_to(target))` instead of calling it
   directly, and see if that's the fix before looking anywhere else.
3. **Look at a rendered document.** Partially done 2026-09-11 while fixing
   the black-screen bug above: a real screenshot (`grim` — available on
   this machine, Wayland/Hyprland) confirms basic markdown (headings, text,
   blockquote) now renders correctly. Still unseen: the h3/h4 colour
   accent, the mermaid container, tables, code blocks, task lists, and
   anything needing mouse/keyboard interaction (`wtype` is available for
   keyboard input if a future pass wants to script that; no mouse-click
   simulation tool was found).
4. **Double-click a `.md` file in an actual file manager** after
   `./install.sh` — every test this session ran launched via CLI.
5. Tag `v0.1.0` once the above close — see `RELEASE.md` for the full
   checklist.

## Files Changed (Phase 7)

- `assets/style.css`: full Pygments token coverage. Verified by actually
  running Pygments' `HtmlFormatter` over python/bash/json/yaml/html/diff
  samples and diffing the emitted `class="..."` values against what had a
  CSS rule — `ch`/`fm`/`gu`/`kc`/`na`/`ne`/`nt`/`nv`/`sa`/`si` were
  confirmed missing (matches the plan's own count of 13 unstyled classes)
  and now have rules in both the light and dark blocks; a script re-run
  after the fix confirms zero missing classes across those 6 languages
  (`w`/Text.Whitespace deliberately left unstyled). Added `.footnote`
  (previously unstyled despite the extension being active), `.toc` (for a
  document that uses python-markdown's own `[TOC]` marker — separate from
  the Ctrl+T overlay, which is a native GTK popover and doesn't touch this
  CSS at all), an `h3`/`h4` colour accent (the user's own ask for a
  document-reading theme, explicitly scoped apart from erdlabs brand
  tokens per BRAND.md), and a proper container (background/padding) for
  `.mermaid-diagram` beyond Phase 2's bare fallback.
- **Not verified**: no real Mermaid SVG has been rendered through this CSS
  (same caveat as every phase since 2 — `mmdc` isn't installed), and the
  heading colour choice hasn't been looked at on screen, only reasoned
  about — flag if it needs revisiting once someone actually looks at a
  rendered document.

## Files Changed (Phase 6)

- `zeile.py`: `render_body()`/`render()` now return `(html_or_body,
  toc_tokens)` instead of a bare string — `toc_tokens` is the `toc`
  extension's already-computed heading tree, previously discarded. New
  `flatten_toc()` turns that nested structure into a flat `(depth, id,
  name)` list for the overlay. `Ctrl+T` opens a `Gtk.Popover`/`Gtk.ListBox`
  built from that list; clicking an entry calls `evaluate_javascript(
  "document.getElementById(...).scrollIntoView()")` with the heading id
  passed through `json.dumps()` rather than f-string interpolation (the one
  value here that comes from document content). `Ctrl+P` opens
  `WebKit.PrintOperation.run_dialog()` (the interactive OS print dialog); a
  header "Export PDF…" button uses `Gtk.FileDialog.save()` for a
  destination, then `WebKit.PrintOperation.print_()` with
  `Gtk.PrintSettings` keys `output-uri`/`output-file-format=pdf` set via the
  generic `.set()` — confirmed via introspection there's no
  `set_export_filename` on `WebKitPrintOperation` (that's a
  `GtkPrintOperation` method, the plan's own warning turned out accurate).
- `tests/test_zeile.py`: updated for the new tuple return, plus 2 new tests
  for `flatten_toc()` (flat and nested cases) and a toc-tokens assertion in
  the end-to-end `render()` test. 22/22 passing.
- `README.md`: new shortcuts, PDF export mention.

## Files Changed (Phase 5)

- `zeile.py`: `Ctrl+F` find-in-page via `WebKit.FindController` + a
  `Gtk.SearchBar`/`Gtk.SearchEntry` revealed above the document (Enter/
  Shift+Enter or the entry's built-in next/previous-match signals step
  through matches, Escape closes and clears). Local `.md`/`.markdown` link
  navigation: `_on_decide_policy` now distinguishes a local markdown link
  (re-enters the renderer via the new `navigate_to()`, pushing history)
  from any other local file:// link (an image, say — still loads directly
  in the WebView as before) from everything else (unchanged: handed to the
  system's default opener). `navigate_to()`/`go_back()`/`go_forward()` with
  `_back_stack`/`_forward_stack`, back/forward header buttons
  (`go-previous-symbolic`/`go-next-symbolic`, sensitivity follows the
  stacks) plus `Alt+Left`/`Alt+Right`. `_watch()` is now safely re-callable
  (cancels the previous file's monitor first) so navigating away doesn't
  leave a stale monitor still firing reloads for the old file.
- `README.md`: new shortcuts, local-link navigation behaviour.

## Files Changed (Phase 4)

- `zeile.py`: `render()` split into `render_body(text, *, enable_mermaid,
  dark)` (pure — no file I/O, no GTK) and `build_document(body, title)`
  (wraps body in the CSP/stylesheet shell), with `render()` now a thin I/O
  shell calling both.
- `tests/` (new): `conftest.py` (repo root on `sys.path`, since these are
  scripts, not a package), `test_markdown_ext.py` (7 tests: fence-in-list,
  nonce-collision safety, disabled-mode escaping, `MermaidUnavailable`
  error path — skipped automatically if `mmdc` happens to be installed),
  `test_zeile.py` (13 tests: frontmatter strip, tasklist, codehilite/toc/
  footnote sanitizer preservation, script/onerror/javascript:/style
  stripping, CSP presence, end-to-end `render()` incl. the missing-file
  path). 20/20 pass.
- System dependency installed: `python-pytest` (pacman, `extra` repo).
- `.gitignore`: `.pytest_cache/`, `.ruff_cache/`.

## Files Changed (Phase 3)

- `zeile.py`: `_strip_frontmatter()` (regex-strips a leading YAML frontmatter
  block, anchored to document start, before markdown ever sees the text —
  confirmed broken before this: rendered as a literal `<hr>` + raw
  `key: value` paragraph). Added `pymdownx.tasklist` to `EXTENSIONS`
  (confirmed broken before: `- [ ]`/`- [x]` rendered as literal bracket
  text). Sanitizer allowlist extended: `input` tag (`type`/`disabled`/
  `checked`, for the tasklist's read-only checkboxes), `ul`/`li` gained
  `class` (tasklist's `task-list`/`task-list-item` classes).
- System dependency installed: `python-pymdown-extensions` (pacman, `extra`
  repo).
- `README.md`: Requirements line.

## Files Changed (Phase 2)

- `zeile.py`: `nh3` sanitizer (`sanitize_html()`) with an explicit tag/
  attribute allowlist on top of nh3's defaults — confirmed empirically that
  nh3's own defaults strip `class`/`id`, which would silently break
  codehilite spans, heading anchors, and footnote id/href pairs; CSP meta
  tag (`default-src 'none'`); WebView now built with an ephemeral
  `WebKit.NetworkSession`; `enable-javascript-markup=False` (document script
  structurally dead, `evaluate_javascript()` from the app itself still
  works); HTML5 local storage + database off; `enable_developer_extras` now
  gated behind `--debug`/`ZEILE_DEBUG` instead of always on; a `decide-policy`
  handler that only allows `file://` navigation under the open document's
  directory, handing everything else to the system's default opener.
  `extract_mermaid()`/`MERMAID_FENCE` removed (replaced below).
- `markdown_ext.py` (new): `MermaidExtension`, a real python-markdown
  preprocessor for ```` ```mermaid ```` fences. Fixes two confirmed bugs from
  the old raw-text-regex approach: a fence indented inside a list/blockquote
  is now correctly extracted (the old column-0-anchored regex silently
  missed it), and a document containing predictable marker-like text can no
  longer hijack a diagram slot (each diagram gets a `secrets.token_hex(16)`
  nonce). Deliberately does NOT hand the sanitizer any SVG/diagram markup —
  it stashes the nonce, not the rendered content, and the caller
  (`zeile.py`'s `render()`) substitutes the real fragment back in only
  *after* `sanitize_html()` has run. This means the nh3 allowlist never had
  to grow SVG tags/attributes at all (a design correction mid-implementation
  — the first draft tried allowlisting `<svg>`/`<path>`/etc. globally in nh3,
  which would have also let a malicious `.md`'s own raw `<svg>`/`<style>`
  HTML survive sanitization; the nonce-deferred-substitution approach avoids
  that entirely).
- `mermaid_render.py` (new): `mmdc` (mermaid-cli) subprocess wrapper,
  content-hash cache (keyed by `(source, dark)`), `MermaidUnavailable`
  raised when `mmdc` isn't on `PATH`. Passes `-c` a config JSON disabling
  `htmlLabels` for flowchart/class/state diagrams so mmdc doesn't emit
  `<foreignObject>` (confirmed via mermaid-cli issue #691 and independent
  reports) — belt-and-suspenders alongside the sanitizer never seeing SVG at
  all.
- `assets/style.css`: minimal `.mermaid-diagram`/`.mermaid-disabled`/
  `.mermaid-error` rules (full theming is Phase 7).
- `assets/mermaid.min.js` removed (5.5 MB vendored copy, replaced by the
  opt-in `mmdc` subprocess path).
- `README.md`: Security section (documents what's now actually true, fixing
  the two previously-false claims), Requirements (`python-nh3`, optional
  `mmdc`), Usage (`--enable-mermaid`, `--debug`), Files.
- System dependency installed: `python-nh3` (pacman, `extra` repo).

## Decisions Made (Phase 2, beyond what the plan specified)

- **A priority collision was found and fixed**: `extra`'s
  `fenced_code_block` preprocessor also registers at priority 25 in
  python-markdown 3.10.3, and registers first (since `EXTENSIONS` lists
  `"extra"` before the Mermaid extension), so equal-priority ties went to it
  — a `` ```mermaid `` fence was being silently consumed as an ordinary code
  block before `MermaidPreprocessor` ever ran. Fixed by registering at
  priority 26. Found via direct reproduction, not assumed — confirmed
  `md.preprocessors._priority` shows the collision, confirmed the fix by
  re-running the failing case.
- **A block-nesting bug was found and fixed**: since the preprocessor only
  stashes a nonce (plain hex text, not HTML), markdown's own paragraph
  processor wraps it as `<p>{nonce}</p>` — substituting a block-level
  fragment (`<pre>`/`<div>`) directly into that produces invalid `<div>`
  inside `<p>` nesting. `MermaidExtension.resolve()` now strips the `<p>...
  </p>` wrapper when present before substituting, falling back to a bare
  substitution otherwise.
- **Known, accepted limitation, not yet fixed**: a mermaid fence nested
  inside a list item extracts and renders correctly now (the original "fence
  destroyed" bug is fixed), but python-markdown splits the surrounding list
  into two separate `<ol>`/`<ul>` fragments around the diagram rather than
  keeping it visually nested inside the list item — a list-continuation
  quirk in python-markdown's own block parser, out of scope for this pass.
- **Not runtime-verified**: no real Mermaid diagram has been rendered
  through `mmdc` — it is not installed on this machine (opt-in, ~300 MB
  Puppeteer/Chromium pull) and installing it wasn't authorized mid-pass.
  What IS verified: the `MermaidUnavailable` error path (confirmed clear
  error text), the extraction/nonce/sanitizer pipeline end-to-end using the
  `enable_mermaid=False` placeholder path (no `mmdc` call needed for that),
  and the `htmlLabels: false` config key's shape (via two independent
  external reports, not first-hand). If `mmdc` gets installed later, verify
  an actual diagram renders and displays correctly before trusting this
  further.
- **nh3 attribute allowlist confirmed empirically** exactly as the plan
  anticipated: default `nh3.clean()` strips heading `id`, codehilite `span`
  `class`, and footnote `id`/`href`; the explicit override in `zeile.py`
  preserves all three while still stripping `<script>`, `onerror=`,
  `javascript:` hrefs, and `<style>` blocks — verified with a crafted test
  string before wiring it into `render()`.
- **Live smoke test**: `zeile.py` launched against a crafted test document
  (relative image, inline `<script>`, `onerror=`, a `javascript:` href, a
  disabled-mode mermaid fence, an external link) for several seconds with no
  traceback. No screenshot/visual verification was done (no headless-display
  tooling set up this pass) — this confirms the app doesn't crash, not that
  every element renders correctly on screen.
- pytest is still not installed (that's Phase 4's job per the plan); Phase 2
  correctness was verified with a throwaway ad-hoc script instead
  (`/tmp/.../scratchpad/verify_phase2.py` — not part of the repo, gone once
  the scratchpad is cleaned).

## Next Steps

Per the plan's phasing (each step its own commit):

1. ~~Rename (`mdview` → `zeile` everywhere)~~ — done
2. ~~Security + Mermaid rewrite~~ — done, see above
3. ~~Fix confirmed-broken renders: frontmatter leak, `pymdownx.tasklist`~~ — done
4. ~~Split render()/add pytest~~ — done, 20/20 passing
5. ~~Ctrl+F, local-link navigation + history~~ — done. Not interactively
   verified (no mouse-driven GTK UI test tooling available this pass): API
   calls were verified individually via introspection (FindController,
   SearchBar/SearchEntry signals) and the app was smoke-tested against a
   real two-page link setup with no crash, but nobody has actually clicked
   the link or typed into the search box and watched it work.
6. ~~TOC overlay (Ctrl+T), Print/PDF export~~ — done. Same caveat as Phase
   5: every individual API call (Popover/ListBox/MenuButton,
   PrintOperation, FileDialog, PrintSettings key-based set/get) was verified
   via introspection and the app launches without a traceback, but nobody
   has clicked through the TOC, printed, or exported a real PDF and checked
   the output.
7. ~~Theme: Pygments coverage, headings, footnote/toc/mermaid CSS~~ — done,
   see above
8. ~~i18n, About dialog, release docs, install.sh polish~~ — done, see above

Full detail, rationale, and verification plan for every phase: the plan file
above. See "Not verified, next human session" above for what to check first.
