# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Launch sequence: phase plan, fade curve, once-flag persistence, version placement.

Pure-function checks, no display needed. The widget behaviour (skip by key or
click, flag set at the start) is covered in tests/headless_gui.py.
"""

import re
from pathlib import Path

import pytest

import zeile
from zeile import load_settings, phase_opacity, plan_launch_sequence, save_settings

ASSETS = Path(zeile.__file__).resolve().parent / "assets"


def test_first_start_plays_intro_then_logo():
    phases = plan_launch_sequence(intro_seen=False, animations=True)
    assert [p.asset for p in phases] == ["logo_erdlabs.png", "zeile.svg"]
    assert [p.total for p in phases] == [2800, 1400]


def test_later_starts_play_only_the_logo():
    phases = plan_launch_sequence(intro_seen=True, animations=True)
    assert [p.asset for p in phases] == ["zeile.svg"]
    assert (phases[0].fade_in, phases[0].hold, phases[0].fade_out) == (400, 600, 400)


def test_animations_off_keeps_frames_without_fades():
    for phase in plan_launch_sequence(intro_seen=False, animations=False):
        assert phase.fade_in == 0 and phase.fade_out == 0 and phase.hold > 0


def test_every_phase_asset_exists():
    for intro_seen in (False, True):
        for phase in plan_launch_sequence(intro_seen=intro_seen, animations=True):
            assert (ASSETS / phase.asset).is_file()


def test_opacity_curve():
    phase = plan_launch_sequence(intro_seen=True, animations=True)[0]  # 400/600/400
    assert phase_opacity(phase, -1) == 0.0
    assert phase_opacity(phase, 0) == 0.0
    assert phase_opacity(phase, 200) == pytest.approx(0.5)
    assert phase_opacity(phase, 400) == 1.0
    assert phase_opacity(phase, 999) == 1.0
    assert phase_opacity(phase, 1200) == pytest.approx(0.5)
    assert phase_opacity(phase, 1400) == 0.0


def test_opacity_without_fades_is_a_plain_frame():
    phase = plan_launch_sequence(intro_seen=True, animations=False)[0]
    assert phase_opacity(phase, 0) == 1.0
    assert phase_opacity(phase, phase.total - 1) == 1.0
    assert phase_opacity(phase, phase.total) == 0.0


def test_intro_seen_defaults_false_and_round_trips(tmp_path):
    path = tmp_path / "settings.json"
    assert load_settings(path=path)["intro_seen"] == "false"
    settings = load_settings(path=path)
    settings["intro_seen"] = "true"
    save_settings(settings, path=path)
    assert load_settings(path=path)["intro_seen"] == "true"


def test_intro_seen_rejects_garbage(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"intro_seen": "maybe"}', encoding="utf-8")
    assert load_settings(path=path)["intro_seen"] == "false"
    path.write_text('{"intro_seen": true}', encoding="utf-8")
    assert load_settings(path=path)["intro_seen"] == "true"


def test_other_saves_keep_the_intro_flag(tmp_path):
    # _persist_settings / _save_window_state merge into load_settings(); the
    # flag must survive a load -> update -> save round trip.
    path = tmp_path / "settings.json"
    save_settings({**load_settings(path=path), "intro_seen": "true"}, path=path)
    current = load_settings(path=path)
    current.update({"theme": "nord", "zoom": "1.5"})
    save_settings(current, path=path)
    assert load_settings(path=path)["intro_seen"] == "true"


def test_version_is_shown_only_in_the_about_dialog():
    source = Path(zeile.__file__).read_text(encoding="utf-8")
    uses = [m.start() for m in re.finditer(r"\b__version__\b", source)]
    # definition + the single About-dialog use
    assert len(uses) == 2
    about = source.index("def _show_about")
    next_def = source.index("\n    def ", about + 1)
    assert about < uses[1] < next_def
