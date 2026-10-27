#!/bin/bash
# Build zeile_<version>_all.deb into dist/ (run on Debian/Ubuntu, needs dpkg-deb and gettext).
# The version comes from pyproject.toml, so there is no third hand-synced copy.
# Depends python3-nh3 exists on Debian 13 but not on Ubuntu 24.04 (see README).
set -euo pipefail

cd "$(dirname "$0")/../.."
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
readonly VERSION
STAGE="$(mktemp -d)"
readonly STAGE
chmod 755 "$STAGE"  # mktemp gives 700; the package root must be world-readable

packaging/stage.sh "$STAGE" /usr
install -d "$STAGE/DEBIAN" "$STAGE/usr/share/doc/zeile"
cp LICENSE "$STAGE/usr/share/doc/zeile/copyright"
cat > "$STAGE/DEBIAN/control" <<CONTROL
Package: zeile
Version: $VERSION
Section: text
Priority: optional
Architecture: all
Depends: python3 (>= 3.11), python3-gi, gir1.2-gtk-4.0, gir1.2-webkit-6.0, python3-markdown, python3-pygments, python3-pymdownx, python3-nh3
Recommends: librsvg2-common, xdg-utils
Maintainer: erdlabs <https://erdlabs.com>
Homepage: https://github.com/DnaMes/zeile
Description: Small, fast GTK4 markdown viewer with live reload
 zeile renders a markdown file, reloads it on save and has 20 themes, syntax
 highlighting and optional Mermaid diagrams. Document JavaScript is disabled,
 the HTML is sanitized and there is no network access.
CONTROL

install -d dist
dpkg-deb --root-owner-group --build "$STAGE" "dist/zeile_${VERSION}_all.deb"
