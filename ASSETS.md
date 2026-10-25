# Assets

Zeile is a bare-Python GTK app, not an Android/Flutter project — the shared
`scripts/write-assets-md.sh`/`asset-intake.sh` pipeline from the erdlabs meta
repo does not apply here. This file is maintained by hand.

## Shipped

| Path                | What                                                  | Provenance                                                                                                                                                                 |
| ------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `assets/zeile.svg`  | Application icon (512×512 source of truth)            | Own-made, regenerated 2026-10-25 by `scripts/build_icons.py` (rsvg-convert/LibreTexts librsvg): erdlabs label mark embedded from `brand/logo/logo.svg` plus a text-line/caret motif (zeile = "line"), colours read from `brand/colors/palette.json`. Licence: own-made, GPL-3.0-or-later like the rest of the app; it replaces the pre-rename `mdview` icon that was carried over in `4a6825f`. |
| `icons/hicolor/**` | Installed icon set: `scalable/apps/zeile.svg` plus one PNG per fixed size (`16x16` … `512x512`) | Generated 2026-10-25 from `assets/zeile.svg` by `scripts/build_icons.py`; hicolor layout as freedesktop declares it (`<size>x<size>/apps`). Licence: own-made (label mark from `brand/logo/logo.svg`); re-run the script after any brand change. |
| `assets/logo_erdlabs.png` | erdlabs brand mark, shown in the About dialog (`_show_about`) and as the first-start intro (`LaunchSplash`) | Copied from `erdlabs/brand/logo/icon_xxxhdpi_192.png` (2026-09-11) — the meta-repo's own generated brand asset, not third-party.                                    |
| `icons/hicolor/512x512/apps/zeile.png` | Product logo on the launch overlay (first start only) | Same provenance as the icon set above; `launch_asset_path()` resolves this file for `LaunchSplash`. |
| `assets/style.css`  | Rendering stylesheet                                  | Original work, written for this project.                                                                                                                                   |
| `assets/themes.css` | Theme + font variable blocks (16 themes, font stacks) | Original work; colour values transcribed from each theme's official published palette (Catppuccin, Solarized, Gruvbox, Nord, Dracula, Rosé Pine, Tokyo Night, GitHub).     |

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
