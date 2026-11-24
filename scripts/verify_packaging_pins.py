#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Verify AUR and Flathub pins against the GitHub tag archive (not the release tarball).

Arch and Flathub fetch https://github.com/DnaMes/zeile/archive/refs/tags/vX.Y.Z.tar.gz.
The workflow's dist/zeile-X.Y.Z.tar.gz is a different object (git archive at the tag commit).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKGBUILD = ROOT / "packaging" / "PKGBUILD"
SRCINFO = ROOT / "packaging" / ".SRCINFO"
FLATHUB = ROOT / "packaging" / "flatpak" / "com.erdlabs.zeile.flathub.yml"
TAG_ARCHIVE_URL = (
    "https://github.com/DnaMes/zeile/archive/refs/tags/v{version}.tar.gz"
)


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if match is None:
        raise ValueError("pyproject.toml: missing version")
    return match.group(1)


def _pkgbuild_pin() -> tuple[str, str]:
    text = PKGBUILD.read_text(encoding="utf-8")
    ver_m = re.search(r"^pkgver=([^\n]+)$", text, re.MULTILINE)
    sum_m = re.search(r"^sha256sums=\(\'([a-f0-9]{64})\'", text, re.MULTILINE)
    url_m = re.search(r'source=\([^:]+::(https://[^"\)]+)', text, re.MULTILINE)
    if not (ver_m and sum_m and url_m):
        raise ValueError("packaging/PKGBUILD: could not parse pkgver, sha256sums or source URL")
    return sum_m.group(1), url_m.group(1).replace("$pkgver", ver_m.group(1))


def _srcinfo_pin() -> str:
    text = SRCINFO.read_text(encoding="utf-8")
    match = re.search(r"^\s*sha256sums = ([a-f0-9]{64})", text, re.MULTILINE)
    if match is None:
        raise ValueError("packaging/.SRCINFO: could not parse sha256sums")
    return match.group(1)


def _flathub_pin() -> tuple[str, str]:
    text = FLATHUB.read_text(encoding="utf-8")
    url_m = re.search(r"^\s+url:\s*(\S+)", text, re.MULTILINE)
    sum_m = re.search(r"^\s+sha256:\s*([a-f0-9]{64})", text, re.MULTILINE)
    if not (url_m and sum_m):
        raise ValueError("com.erdlabs.zeile.flathub.yml: could not parse archive url or sha256")
    return sum_m.group(1), url_m.group(1)


def _flathub_install_paths() -> list[str]:
    for line in FLATHUB.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- install -m 644 "):
            continue
        if not stripped.endswith(" /app/share/zeile/"):
            continue
        payload = stripped.removeprefix("- install -m 644 ").removesuffix(" /app/share/zeile/")
        return payload.split()
    raise ValueError("flathub manifest: could not parse zeile.py install line")


def _assert_archive_contains(archive: Path, version: str, names: list[str]) -> None:
    prefix = f"zeile-{version}/"
    with tarfile.open(archive, "r:gz") as tar:
        members = {m.name for m in tar.getmembers()}
        missing = [name for name in names if f"{prefix}{name}" not in members]
        if missing:
            raise ValueError(f"tag archive missing files for Flathub install: {', '.join(missing)}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_tag_archive(version: str, dest: Path) -> None:
    url = TAG_ARCHIVE_URL.format(version=version)
    with urllib.request.urlopen(url, timeout=120) as resp:
        data = resp.read()
    # Refuse to follow a symlink at dest (predictable /tmp races).
    if dest.exists() or dest.is_symlink():
        dest.unlink()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    fd = os.open(dest, flags, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive",
        type=Path,
        help="use this tag archive instead of downloading (for offline runs)",
    )
    args = parser.parse_args()

    version = _version()
    expected_url = TAG_ARCHIVE_URL.format(version=version)
    pkg_sum, pkg_url = _pkgbuild_pin()
    src_sum = _srcinfo_pin()
    flat_sum, flat_url = _flathub_pin()

    pins = {
        "packaging/PKGBUILD": pkg_sum,
        "packaging/.SRCINFO": src_sum,
        "packaging/flatpak/com.erdlabs.zeile.flathub.yml": flat_sum,
    }
    distinct = set(pins.values())
    if len(distinct) != 1:
        detail = ", ".join(f"{name}={value}" for name, value in pins.items())
        print(f"pin drift: {detail}", file=sys.stderr)
        return 1
    if pkg_url != expected_url or flat_url != expected_url:
        print(
            f"URL mismatch: expected {expected_url}; PKGBUILD={pkg_url}; flathub={flat_url}",
            file=sys.stderr,
        )
        return 1

    owned_temp: Path | None = None
    archive = args.archive
    try:
        if archive is None:
            fd, name = tempfile.mkstemp(prefix=f"zeile-v{version}-", suffix=".tar.gz")
            os.close(fd)
            owned_temp = Path(name)
            archive = owned_temp
            print(f"downloading {expected_url} ...")
            _download_tag_archive(version, archive)
        elif not archive.is_file():
            print(f"missing archive: {archive}", file=sys.stderr)
            return 1

        measured = _sha256_file(archive)
        pinned = distinct.pop()
        try:
            _assert_archive_contains(archive, version, _flathub_install_paths())
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1
        if measured != pinned:
            print(
                f"tag archive sha256 mismatch: measured {measured}, pinned {pinned}",
                file=sys.stderr,
            )
            return 1

        print(f"packaging pins OK for v{version} ({pinned})")
        return 0
    finally:
        if owned_temp is not None:
            owned_temp.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())