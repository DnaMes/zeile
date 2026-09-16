#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Check that zeile's hand-maintained version copies agree.

The application intentionally remains a dependency-light script rather than a
Python package with a build backend, so the version appears in three files:
the project metadata, the About dialog, and the Arch package recipe. This
script makes the old release-checklist warning machine-checkable and is used
by the release workflow before an artifact is published.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_versions() -> dict[str, str]:
    values: dict[str, str] = {}
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    zeile = (ROOT / "zeile.py").read_text(encoding="utf-8")
    pkgbuild = (ROOT / "packaging" / "PKGBUILD").read_text(encoding="utf-8")

    for name, pattern, text in (
        ("pyproject.toml", r'^version\s*=\s*"([^"]+)"$', pyproject),
        ("zeile.py", r'^__version__\s*=\s*"([^"]+)"$', zeile),
        ("packaging/PKGBUILD", r"^pkgver=([^\n]+)$", pkgbuild),
    ):
        match = re.search(pattern, text, re.MULTILINE)
        if match is None:
            raise ValueError(f"could not find version in {name}")
        values[name] = match.group(1)
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expected", help="expected SemVer, e.g. 0.2.0")
    parser.add_argument(
        "--tag",
        help="optional tag to validate as well, e.g. v0.2.0",
    )
    args = parser.parse_args()

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", args.expected):
        parser.error(f"not a SemVer-like version: {args.expected!r}")
    if args.tag is not None and args.tag != f"v{args.expected}":
        print(
            f"version/tag mismatch: expected v{args.expected}, got {args.tag}",
            file=sys.stderr,
        )
        return 1

    try:
        versions = read_versions()
    except (OSError, ValueError) as exc:
        print(f"version check failed: {exc}", file=sys.stderr)
        return 1

    distinct = set(versions.values())
    if distinct != {args.expected}:
        details = ", ".join(f"{path}={version}" for path, version in versions.items())
        print(f"version drift: {details}; expected {args.expected}", file=sys.stderr)
        return 1

    print(f"version {args.expected} consistent across {len(versions)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
