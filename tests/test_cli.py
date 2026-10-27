# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Tests for the translated CLI --help output.

`zeile.py --help` must exit 0 in both locales, show every option, translate
into German under LANGUAGE=de, and never touch the settings file (argparse
exits before main() loads settings).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_OPTIONS = [
    "--help",
    "--enable-mermaid",
    "--debug",
    "--theme",
    "--body-font",
    "--code-font",
]


def _run_help(language: str, tmp_path: Path) -> subprocess.CompletedProcess[bytes]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in {"LANGUAGE", "LC_ALL", "LC_MESSAGES", "LANG"}
    }
    env["LC_ALL"] = "C.UTF-8"
    env["LANGUAGE"] = language
    env["HOME"] = str(tmp_path)
    env["XDG_CONFIG_HOME"] = str(tmp_path / "config")
    return subprocess.run(
        [sys.executable, str(REPO / "zeile.py"), "--help"],
        capture_output=True,
        env=env,
        timeout=30,
    )


def test_help_en_lists_all_options(tmp_path: Path) -> None:
    proc = _run_help("en", tmp_path)
    assert proc.returncode == 0
    out = proc.stdout.decode()
    for opt in _OPTIONS:
        assert opt in out
    assert "Minimal GTK4 markdown viewer" in out
    assert "--version" not in out


def test_help_de_translated_and_lists_all_options(tmp_path: Path) -> None:
    proc = _run_help("de", tmp_path)
    assert proc.returncode == 0
    out = proc.stdout.decode()
    for opt in _OPTIONS:
        assert opt in out
    # Own word from the new German strings; argparse wraps at whitespace only.
    assert "Fließtext" in out
    assert "Markdown-Betrachter" in out


def test_help_does_not_create_settings(tmp_path: Path) -> None:
    config = tmp_path / "config"
    _run_help("de", tmp_path)
    assert not (config / "zeile" / "settings.json").exists()
    assert not list(config.rglob("settings.json"))
