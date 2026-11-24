#!/bin/bash
# Copy AUR and Flathub submission files for owner approval (does not publish).
#   scripts/stage-linux-submissions.sh
#   scripts/stage-linux-submissions.sh --force   # overwrite existing staged files
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"
force=0
[[ "${1:-}" == "--force" ]] && force=1

if [[ -n "${ZEILE_TAG_ARCHIVE:-}" ]]; then
    python3 scripts/verify_packaging_pins.py --archive "$ZEILE_TAG_ARCHIVE"
else
    python3 scripts/verify_packaging_pins.py
fi

AUR_DIR="${HOME}/aur-staging/zeile"
FLATHUB_DIR="${HOME}/flathub-submission/com.erdlabs.zeile"

aur_files=(packaging/PKGBUILD packaging/.SRCINFO)
flat_src=packaging/flatpak/com.erdlabs.zeile.flathub.yml
flat_dst="$FLATHUB_DIR/com.erdlabs.zeile.yml"
deps_src=packaging/flatpak/python-deps.json

if [[ $force -eq 0 ]]; then
    for f in "${aur_files[@]}"; do
        dest="$AUR_DIR/$(basename "$f")"
        if [[ -e "$dest" ]]; then
            printf 'refusing to overwrite %s (pass --force)\n' "$dest" >&2
            exit 1
        fi
    done
    if [[ -e "$flat_dst" || -e "$FLATHUB_DIR/python-deps.json" ]]; then
        printf 'refusing to overwrite files under %s (pass --force)\n' "$FLATHUB_DIR" >&2
        exit 1
    fi
fi

install -d "$AUR_DIR" "$FLATHUB_DIR"
install -m 644 "${aur_files[@]}" "$AUR_DIR/"
install -m 644 "$flat_src" "$flat_dst"
install -m 644 "$deps_src" "$FLATHUB_DIR/"

printf 'staged AUR → %s\n' "$AUR_DIR"
printf 'staged Flathub → %s\n' "$FLATHUB_DIR"
printf 'Owner: review diffs, then push AUR (ssh) and open Flathub PR.\n'
