#!/bin/bash
# Build one package in a clean container, install it and run packaging/smoke.sh.
#   scripts/package-check.sh deb|rpm|arch      (needs docker; run from a clean, committed tree)
set -euo pipefail

readonly KIND="${1:?usage: package-check.sh deb|rpm|arch}"
cd "$(dirname "$0")/.."
WORK="$(mktemp -d)"
readonly WORK
git worktree list >/dev/null  # fail early outside a git checkout
git clone -q . "$WORK/zeile"

# The container scripts below are single-quoted on purpose: they expand inside the container.
# shellcheck disable=SC2016
case "$KIND" in
deb)
    IMAGE=debian:13
    SCRIPT='set -euo pipefail; export DEBIAN_FRONTEND=noninteractive; apt-get update -qq
        apt-get install -y -qq --no-install-recommends gettext cage desktop-file-utils >/dev/null
        packaging/debian/build-deb.sh
        apt-get install -y -qq --no-install-recommends ./dist/zeile_*_all.deb >/dev/null
        packaging/smoke.sh'
    ;;
rpm)
    IMAGE=fedora:43
    SCRIPT='set -euo pipefail; dnf install -y -q rpm-build gettext git cage >/dev/null
        packaging/rpm/build-rpm.sh
        dnf install -y -q ./dist/zeile-*.rpm >/dev/null
        packaging/smoke.sh'
    ;;
arch)
    IMAGE=archlinux:base
    SCRIPT='set -euo pipefail; pacman -Syu --noconfirm --needed base-devel git gettext cage >/dev/null 2>&1
        useradd -m builder; install -d -o builder /build
        v="$(sed -n "s/^version = \"\(.*\)\"/\1/p" pyproject.toml)"
        git archive --format=tar.gz --prefix="zeile-$v/" HEAD > "/build/zeile-$v.tar.gz"
        sed "s|^source=.*|source=(\"zeile-\$pkgver.tar.gz\")|; s|^sha256sums=.*|sha256sums=(SKIP)|" \
            packaging/PKGBUILD > /build/PKGBUILD
        chown -R builder /build; cd /build
        su builder -c "makepkg -f --noprogressbar" >/dev/null
        pacman -U --noconfirm /build/zeile-*.pkg.tar.zst >/dev/null 2>&1
        cd - >/dev/null; packaging/smoke.sh'
    ;;
*)
    printf 'unknown kind: %s\n' "$KIND" >&2
    exit 2
    ;;
esac

docker run --rm -v "$WORK/zeile:/src" -w /src "$IMAGE" bash -c "$SCRIPT"
