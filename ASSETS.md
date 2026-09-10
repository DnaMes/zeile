# Assets

Zeile is a bare-Python GTK app, not an Android/Flutter project — the shared
`scripts/write-assets-md.sh`/`asset-intake.sh` pipeline from the erdlabs meta
repo does not apply here. This file is maintained by hand.

## Shipped

| Path | What | Provenance |
|---|---|---|
| `assets/zeile.svg` | Application icon | Carried over from `mdview` at the 2026-09-10 rename (`4a6825f`); original authorship predates this repository, from the `e14/apps/mdview` project this was ported in from. |
| `assets/style.css` | Rendering stylesheet | Original work, written for this project. |

## Removed

- `assets/mermaid.min.js` (vendored Mermaid 12.0.0, MIT) — shipped at the
  initial import, removed in `8f2f129` (Phase 2 of the security-hardening
  plan) when Mermaid rendering moved from an in-page live JS renderer to an
  opt-in `mmdc` subprocess pre-render to static SVG. No vendored third-party
  code remains in this repository.

## Third-party dependencies (not vendored, not bundled)

`mmdc` (`@mermaid-js/mermaid-cli`, opt-in via `--enable-mermaid`) is invoked
as an external subprocess the user installs separately (`npm install -g
@mermaid-js/mermaid-cli`) — it is never copied into this repository or the
built application.
