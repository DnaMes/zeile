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
    # Build tools would mask missing Requires (git, rpm-build pull in typelibs), so the
    # package is installed and smoke-tested in a second, clean container.
    SCRIPT='set -euo pipefail; dnf install -y -q rpm-build gettext git >/dev/null
        packaging/rpm/build-rpm.sh'
    INSTALL_SCRIPT='set -euo pipefail; dnf install -y -q cage ./dist/zeile-*.rpm >/dev/null
        packaging/smoke.sh'
    ;;
arch)
    IMAGE=archlinux:base
    SCRIPT='set -euo pipefail; printf "%s\n" "$ARCH_MIRROR" > /etc/pacman.d/mirrorlist; for i in 1 2 3; do pacman -Syu --disable-download-timeout --noconfirm --needed base-devel git gettext cage >/dev/null && break; done
        useradd -m builder; install -d -o builder /build
        v="$(sed -n "s/^version = \"\(.*\)\"/\1/p" pyproject.toml)"
        git archive --format=tar.gz --prefix="zeile-$v/" HEAD > "/build/zeile-$v.tar.gz"
        sed "s|^source=.*|source=(\"zeile-\$pkgver.tar.gz\")|; s|^sha256sums=.*|sha256sums=(SKIP)|" \
            packaging/PKGBUILD > /build/PKGBUILD
        chown -R builder /build; cd /build
        su builder -c "makepkg -f --nodeps --noprogressbar" >/dev/null
        for i in 1 2 3; do pacman -U --disable-download-timeout --noconfirm /build/zeile-*.pkg.tar.zst >/dev/null && break; done
        cd - >/dev/null; packaging/smoke.sh'
    ;;
*)
    printf 'unknown kind: %s\n' "$KIND" >&2
    exit 2
    ;;
esac

# The clone is owned by the host user, not root: let git inside the container read it
# (an environment setting works before git is even installed in the image).
docker run --rm -v "$WORK/zeile:/src" -w /src \
    -e ARCH_MIRROR='Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch' \
    -e GIT_CONFIG_COUNT=1 -e GIT_CONFIG_KEY_0=safe.directory -e GIT_CONFIG_VALUE_0=/src \
    "$IMAGE" bash -c "$SCRIPT"
if [[ -n "${INSTALL_SCRIPT:-}" ]]; then
    docker run --rm -v "$WORK/zeile:/src" -w /src "$IMAGE" bash -c "$INSTALL_SCRIPT"
fi
