# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Pytest wrapper for the headless GUI matrix (tests/headless_gui.py).

Runs the full GTK/WebKit widget verification inside a headless cage
compositor -- invisible, focus-safe. Skipped automatically when there is no
cage, no Wayland session, or the interpreter lacks gi bindings (CI relies on
that skip; dev machines with a desktop run it for real).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


def _can_run() -> bool:
    if not shutil.which("cage"):
        return False
    if not os.environ.get("WAYLAND_DISPLAY"):
        return False
    try:
        subprocess.run(
            [sys.executable, "-c", "import gi, gi.repository.Gtk"],
            check=True,
            capture_output=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return False
    return True


@pytest.mark.skipif(not _can_run(), reason="needs cage + Wayland session + gi")
def test_headless_gui_matrix() -> None:
    repo = Path(__file__).resolve().parent.parent
    script = repo / "tests" / "headless_gui.py"
    env = dict(
        os.environ,
        WLR_BACKENDS="headless",
        WLR_LIBINPUT_NO_DEVICES="1",
        WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS="1",
    )
    result = subprocess.run(
        ["timeout", "150", "cage", "-d", sys.executable, str(script)],
        capture_output=True,
        text=True,
        env=env,
        timeout=170,
    )
    output = f"{result.stdout[-3000:]}\n{result.stderr[-1000:]}"
    assert result.returncode == 0, f"headless GUI matrix failed:\n{output}"
    assert "FAIL" not in result.stdout
