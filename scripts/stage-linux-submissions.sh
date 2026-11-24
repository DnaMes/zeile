#!/bin/bash
# Copy AUR and Flathub submission files for owner approval (does not publish).
#   scripts/stage-linux-submissions.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"

if [[ -n "${ZEILE_TAG_ARCHIVE:-}" ]]; then
    python3 scripts/verify_packaging_pins.py --archive "$ZEILE_TAG_ARCHIVE"
else
    python3 scripts/verify_packaging_pins.py
fi

AUR_DIR="${HOME}/aur-staging/zeile"
FLATHUB_DIR="${HOME}/flathub-submission/com.erdlabs.zeile"

install -d "$AUR_DIR" "$FLATHUB_DIR"
install -m 644 packaging/PKGBUILD packaging/.SRCINFO "$AUR_DIR/"
install -m 644 packaging/flatpak/com.erdlabs.zeile.flathub.yml \
    "$FLATHUB_DIR/com.erdlabs.zeile.yml"
install -m 644 packaging/flatpak/python-deps.json "$FLATHUB_DIR/"

printf 'staged AUR → %s\n' "$AUR_DIR"
printf 'staged Flathub → %s\n' "$FLATHUB_DIR"
printf 'Owner: review diffs, then push AUR (ssh) and open Flathub PR.\n'