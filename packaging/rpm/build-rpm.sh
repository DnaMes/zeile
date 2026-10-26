#!/bin/bash
# Build the noarch rpm into dist/ (run on Fedora, needs rpm-build and gettext). The
# source tarball comes from `git archive`, so it contains exactly the committed tree.
set -euo pipefail

cd "$(dirname "$0")/../.."
VERSION="$(sed -n 's/^version = "\(.*\)"/\1/p' pyproject.toml)"
readonly VERSION
TOP="$(mktemp -d)"
readonly TOP

mkdir -p "$TOP/SOURCES"
git archive --format=tar.gz --prefix="zeile-$VERSION/" HEAD > "$TOP/SOURCES/zeile-$VERSION.tar.gz"
rpmbuild -bb --define "_topdir $TOP" --define "zeile_version $VERSION" packaging/rpm/zeile.spec
install -d dist
cp "$TOP"/RPMS/noarch/zeile-*.rpm dist/
