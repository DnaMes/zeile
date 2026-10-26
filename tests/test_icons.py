# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The icon set: every declared hicolor size ships, and Icon= resolves to it.

The desktop entries from install.sh and packaging/stage.sh (deb, rpm, PKGBUILD) all say
``Icon=zeile``. That name must resolve against the hicolor tree the same
scripts install -- one PNG per fixed size plus the scalable SVG, using the
freedesktop ``<size>x<size>/apps`` directory names hicolor's index.theme
declares (a bare ``48/apps`` directory is silently ignored by GtkIconTheme).
"""

import re
import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

from build_icons import ICON_NAME, PNG_SIZES  # noqa: E402

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
HICOLOR = REPO / "icons" / "hicolor"


def png_dimensions(path: Path) -> tuple[int, int]:
    """(width, height) from the PNG IHDR chunk."""
    header = path.read_bytes()
    assert header[:8] == PNG_MAGIC, f"{path}: not a PNG"
    width, height = struct.unpack(">II", header[16:24])
    return width, height


def desktop_icon_values() -> dict[Path, str]:
    """Icon= value of every desktop entry embedded in an install script."""
    entries: dict[Path, str] = {}
    for script in (REPO / "install.sh", REPO / "packaging" / "stage.sh"):
        match = re.search(r"^Icon=(\S+)$", script.read_text(encoding="utf-8"), re.M)
        assert match, f"{script}: no Icon= line"
        entries[script] = match.group(1)
    return entries


def test_png_sizes_exist_and_are_the_declared_dimensions() -> None:
    for size in PNG_SIZES:
        path = HICOLOR / f"{size}x{size}" / "apps" / f"{ICON_NAME}.png"
        assert path.is_file(), f"missing {size} px icon: {path}"
        assert png_dimensions(path) == (size, size), f"{path}: wrong dimensions"


def test_scalable_svg_matches_assets_copy() -> None:
    scalable = HICOLOR / "scalable" / "apps" / f"{ICON_NAME}.svg"
    assert scalable.is_file(), f"missing scalable icon: {scalable}"
    assert scalable.read_bytes() == (REPO / "assets" / f"{ICON_NAME}.svg").read_bytes()


def test_desktop_icon_resolves_to_installed_icon() -> None:
    # Which hicolor files an install actually lays down (install.sh's list).
    install_sh = (REPO / "install.sh").read_text(encoding="utf-8")
    match = re.search(r"ICON_DIRS=\(([^)]*)\)", install_sh)
    assert match, "install.sh: no ICON_DIRS declaration"
    dirs = match.group(1).split()

    for script, icon in desktop_icon_values().items():
        assert icon == ICON_NAME, f"{script}: Icon={icon} != {ICON_NAME}"
        for directory in dirs:
            ext = "svg" if directory == "scalable" else "png"
            path = HICOLOR / directory / "apps" / f"{ICON_NAME}.{ext}"
            assert path.is_file(), f"{script}: Icon={icon} has no {path}"
