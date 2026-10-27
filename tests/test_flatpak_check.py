# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Unit checks for the Flatpak sandbox integration scripts (no flatpak, no display)."""

from __future__ import annotations

import py_compile
import stat
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
CHECK_SH = SCRIPTS / "flatpak-check.sh"
PROBE_PY = SCRIPTS / "flatpak_probe.py"


def test_flatpak_scripts_are_executable() -> None:
    for path in (CHECK_SH, PROBE_PY):
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"{path.name} must be executable"


def test_flatpak_probe_compiles() -> None:
    py_compile.compile(str(PROBE_PY), doraise=True)


def test_flatpak_check_sh_syntax_and_shape() -> None:
    subprocess.run(["bash", "-n", str(CHECK_SH)], check=True)
    text = CHECK_SH.read_text(encoding="utf-8")
    assert "trap cleanup EXIT" in text
    assert "PASS: imports" in text
    assert "PASS: probe" in text
    assert "PASS: network isolation" in text


def test_flatpak_check_exits_2_when_tools_missing() -> None:
    result = subprocess.run(
        [str(CHECK_SH)],
        env={"PATH": "", "HOME": str(REPO)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    combined = result.stdout + result.stderr
    assert "flatpak-check requires flatpak, flatpak-builder and cage on PATH" in combined
