# zeile — Handoff

Created 2026-09-10. Renamed from `mdview` to `zeile` same day (name collision
research: `mdview` clashes on PyPI, npm, crates.io, AUR and a 144★ GitHub
project — see the full plan).

## Current Task

Executing the plan at `~/.claude/plans/hi-hier-wa-rein-humming-kahan.md`
(security hardening, Mermaid pre-render rewrite, feature fixes, i18n,
release docs — phased so `main` stays buildable after every commit).

Running fully autonomously per operator instruction (2026-09-10): finish all
remaining phases, commit each, no per-phase check-in. Claude Max hit its 5h
usage limit mid-session — if this file says a phase is unfinished and the
session has gone idle, that's why; git history is the source of truth for
what actually landed.

**Phases 1-2 done.** Phase 3 (frontmatter/tasklist fixes) is next.

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
3. Fix confirmed-broken renders: frontmatter leak, `pymdownx.tasklist`
   (needs `python-pymdown-extensions`, not yet installed)
4. Split `render()` into `render_body`/`build_document` + I/O shell, add
   `pytest` unit tests (install `python-pytest`)
5. Ctrl+F find-in-page, local `.md` link navigation with back/forward history
6. TOC overlay (Ctrl+T), Print/PDF export
7. Theme: full Pygments token coverage, VSCode Dark+/Light+ heading palette,
   proper mermaid diagram theming (beyond the minimal Phase 2 CSS)
8. i18n (gettext DE/EN), version-visible About dialog, CHANGELOG/PRIVACY/
   RELEASE/ASSETS.md, `install.sh` uninstall + dependency check

Full detail, rationale, and verification plan for every phase: the plan file
above.
