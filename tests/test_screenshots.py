# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""write_png must fail loudly when a screenshot cannot actually be written.

The GTK renderer's save_to_png quietly returns False on failure, so the helper
verifies what landed on disk: present, non-empty, and carrying the PNG magic.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import pytest  # noqa: E402
from screenshots import PNG_SIGNATURE, write_png  # noqa: E402


class FakeTexture:
    """Stand-in for Gdk.Texture; save_to_png writes whatever the mode says."""

    def __init__(self, mode: str) -> None:
        self.mode = mode

    def save_to_png(self, target: str) -> bool:
        if self.mode == "refuse":
            return False
        if self.mode == "garbage":
            Path(target).write_bytes(b"<html>not a png</html>")
        elif self.mode == "empty":
            Path(target).write_bytes(b"")
        elif self.mode == "missing":
            pass  # reports success, writes nothing
        elif self.mode == "valid":
            ihdr = b"\x00\x00\x00\x0dIHDR" + b"\x00" * 13 + b"\x00" * 4
            Path(target).write_bytes(PNG_SIGNATURE + ihdr)
        elif self.mode == "signature-only":
            Path(target).write_bytes(PNG_SIGNATURE)
        return True


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("refuse", "returned False"),
        ("garbage", "not a PNG (bad signature)"),
        ("empty", "empty file after save"),
        ("signature-only", "truncated PNG"),
        ("missing", "not written after save"),
    ],
)
def test_write_png_raises_on_bad_saves(mode: str, message: str, tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=message.replace("(", "\\(").replace(")", "\\)")):
        write_png(FakeTexture(mode), tmp_path / "theme.png")


def test_write_png_accepts_a_real_png(tmp_path: Path) -> None:
    path = tmp_path / "theme.png"
    write_png(FakeTexture("valid"), path)
    assert path.is_file()
    assert path.read_bytes()[:8] == PNG_SIGNATURE


def test_stale_png_does_not_hide_a_failed_save(tmp_path: Path) -> None:
    target = tmp_path / "shot.png"
    target.write_bytes(PNG_SIGNATURE + b"stale")
    with pytest.raises(RuntimeError):
        write_png(FakeTexture("missing"), target)
