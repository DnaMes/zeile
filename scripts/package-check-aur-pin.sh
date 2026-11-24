#!/bin/bash
# Build and smoke-test using packaging/PKGBUILD against the pinned GitHub tag archive.
#   scripts/package-check-aur-pin.sh
set -euo pipefail

cd "$(dirname "$0")/.."
version="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
# Optional offline pin: ZEILE_TAG_ARCHIVE=/path/to/vX.Y.Z.tar.gz
# Without it, verify_packaging_pins.py downloads the tag archive itself.
if [[ -n "${ZEILE_TAG_ARCHIVE:-}" ]]; then
  python3 scripts/verify_packaging_pins.py --archive "$ZEILE_TAG_ARCHIVE"
else
  python3 scripts/verify_packaging_pins.py
fi

WORK="$(mktemp -d)"
readonly WORK
install -d "$WORK"
install -m 644 packaging/PKGBUILD packaging/.SRCINFO "$WORK/"

docker run --rm -v "$WORK:/build" -w /build \
    -e "ZEILE_VERSION=$version" \
    -e ARCH_MIRROR='Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch' \
    archlinux:base \
    bash -c 'set -euo pipefail
printf "%s\n" "$ARCH_MIRROR" > /etc/pacman.d/mirrorlist
for i in 1 2 3; do pacman -Syu --disable-download-timeout --noconfirm --needed base-devel gettext cage >/dev/null && break; done
useradd -m builder
chown builder /build
cd /build
su builder -c "makepkg -f --nodeps --noprogressbar"
for i in 1 2 3; do pacman -U --disable-download-timeout --noconfirm /build/zeile-*.pkg.tar.zst >/dev/null && break; done
cd "/build/src/zeile-${ZEILE_VERSION}"
packaging/smoke.sh'

printf 'aur-pin-check OK\n'