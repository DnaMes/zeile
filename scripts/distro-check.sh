#!/bin/bash
# Verify zeile on one distro, inside a container: install the dependencies
# with the native package manager, run the tests and the headless GUI matrix,
# then an install/uninstall round trip into a throw-away $HOME.
#   docker run --rm -v "$PWD:/src:ro" <image> /src/scripts/distro-check.sh
set -euo pipefail

readonly SRC="${1:-/src}"
WORK="$(mktemp -d)"
readonly WORK

cp -r "$SRC/." "$WORK/zeile"
cd "$WORK/zeile"

if command -v pacman >/dev/null 2>&1; then
    pacman -Syu --noconfirm --needed gtk4 webkitgtk-6.0 python-gobject python-markdown \
        python-pygments python-nh3 python-pymdown-extensions python-pytest gettext \
        xdg-utils cage
elif command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq --no-install-recommends python3 python3-gi gir1.2-gtk-4.0 \
        gir1.2-webkit-6.0 python3-markdown python3-pygments python3-pymdownx \
        python3-pytest gettext xdg-utils cage dbus-daemon python3-pip
    # Ubuntu 24.04 has no python3-nh3; Debian 13 does.
    if ! apt-get install -y -qq --no-install-recommends python3-nh3; then
        python3 -m pip install -q --break-system-packages nh3
    fi
elif command -v dnf >/dev/null 2>&1; then
    dnf install -y -q python3 python3-gobject gtk4 webkitgtk6.0 python3-markdown \
        python3-pygments python3-pymdown-extensions python3-nh3 python3-pytest gettext \
        gobject-introspection xdg-utils cage
else
    printf 'unsupported distro\n' >&2
    exit 2
fi

printf '== pytest\n'
/usr/bin/python3 -m pytest -q

printf '== headless GUI matrix (cage)\n'
XDG_RUNTIME_DIR="$(mktemp -d)"
export XDG_RUNTIME_DIR
chmod 700 "$XDG_RUNTIME_DIR"
# WebKit's bubblewrap sandbox needs user namespaces, which containers lack; the
# test document is our own fixture, so the sandbox is switched off here only.
export WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1
WLR_BACKENDS=headless WLR_LIBINPUT_NO_DEVICES=1 WLR_RENDERER=pixman \
    cage -d -- /usr/bin/python3 tests/headless_gui.py

printf '== install / uninstall round trip\n'
HOME="$(mktemp -d)"
export HOME
./install.sh
test -x "$HOME/.local/bin/zeile"
./install.sh --uninstall
test ! -e "$HOME/.local/bin/zeile"
# shellcheck source=/dev/null
. /etc/os-release
printf 'OK: %s\n' "$PRETTY_NAME"
