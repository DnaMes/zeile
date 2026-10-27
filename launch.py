# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The launch sequence: which logo frame plays when, and how it fades.

Pure planning code, kept out of the GTK shell so a Windows or macOS shell can
reuse the same sequence once it grows a splash of its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class LaunchPhase:
    """One frame of the launch sequence; durations in milliseconds."""

    asset: str
    fade_in: int
    hold: int
    fade_out: int

    @property
    def total(self) -> int:
        return self.fade_in + self.hold + self.fade_out


# docs/SPLASH.md + BRAND.md §7: the erdlabs mark and product logo play once
# per install (~2.8 s + 1.4 s); later native starts show nothing.
_INTRO_PHASE = LaunchPhase("logo_erdlabs.png", 800, 1200, 800)
_LOGO_PHASE = LaunchPhase("zeile.png", 400, 600, 400)


def launch_asset_path(asset: str) -> Path:
    """Resolve a launch-sequence image; product logo lives in the icon set."""
    root = Path(__file__).resolve().parent
    if asset == "zeile.png":
        return root / "icons" / "hicolor" / "512x512" / "apps" / "zeile.png"
    return root / "assets" / asset


def plan_launch_sequence(*, intro_seen: bool, animations: bool) -> list[LaunchPhase]:
    """Phases to play on first start only; with animations off the fades go."""
    if intro_seen:
        return []
    phases = [_INTRO_PHASE, _LOGO_PHASE]
    if animations:
        return phases
    return [LaunchPhase(p.asset, 0, p.hold, 0) for p in phases]


def phase_opacity(phase: LaunchPhase, t_ms: float) -> float:
    """Linear fade in, hold, fade out; 0 outside the phase."""
    if t_ms < 0 or t_ms >= phase.total:
        return 0.0
    if phase.fade_in and t_ms < phase.fade_in:
        return t_ms / phase.fade_in
    if t_ms < phase.fade_in + phase.hold:
        return 1.0
    if phase.fade_out:
        return (phase.total - t_ms) / phase.fade_out
    return 0.0
