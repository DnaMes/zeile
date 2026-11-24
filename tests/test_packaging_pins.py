# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Packaging pin files must agree (network check is scripts/verify_packaging_pins.py)."""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VERIFY = REPO / "scripts" / "verify_packaging_pins.py"


def _load_verify():
    spec = importlib.util.spec_from_file_location("verify_packaging_pins", VERIFY)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_submission_templates_exist() -> None:
    assert (REPO / "packaging" / ".SRCINFO").is_file()
    assert (REPO / "packaging" / "flatpak" / "com.erdlabs.zeile.flathub.yml").is_file()


def test_aur_and_flathub_pins_match_each_other() -> None:
    mod = _load_verify()
    version = mod._version()
    pkg_sum, pkg_url = mod._pkgbuild_pin()
    src_sum = mod._srcinfo_pin()
    flat_sum, flat_url = mod._flathub_pin()
    expected = mod.TAG_ARCHIVE_URL.format(version=version)

    assert pkg_sum == src_sum == flat_sum
    assert pkg_url == expected
    assert flat_url == expected
    assert re.fullmatch(r"[a-f0-9]{64}", pkg_sum)


@pytest.mark.parametrize(
    "path",
    [
        REPO / "scripts" / "verify_packaging_pins.py",
        REPO / "scripts" / "stage-linux-submissions.sh",
    ],
)
def test_scripts_are_executable(path: Path) -> None:
    assert path.stat().st_mode & 0o111


def test_verify_script_help() -> None:
    subprocess.run(["python3", str(VERIFY), "--help"], check=True, capture_output=True)