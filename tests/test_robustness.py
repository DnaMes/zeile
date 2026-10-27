# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Malformed bytes and numbers must never stop the viewer from opening."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from documents import render
from preferences import load_settings, save_settings

DEFAULTS = {
    "theme": "auto",
    "body_font": "system",
    "code_font": "system",
    "reading_width": "standard",
    "zoom": "1.0",
    "window_w": "900",
    "window_h": "1000",
    "window_maximized": "false",
    "intro_seen": "false",
}


def test_render_invalid_utf8_document_is_replaced_not_raised(tmp_path: Path):
    doc = tmp_path / "bad.md"
    doc.write_bytes(b"# Title\n\nbroken \xff\xfe byte\n")
    html_doc, toc, _codes = render(doc, enable_mermaid=False, dark=False, theme_id="auto")
    assert "\ufffd" in html_doc
    assert "broken" in html_doc
    assert toc == [] or "id" in toc[0]


def test_render_invalid_utf8_keeps_valid_text_around_it(tmp_path: Path):
    doc = tmp_path / "mixed.md"
    doc.write_bytes("# Grüße\n\n\x80 caf\u00e9\n".encode("latin-1"))
    html_doc, _toc, _codes = render(doc, enable_mermaid=False, dark=False)
    assert "\ufffd" in html_doc
    assert "caf" in html_doc


def test_render_missing_document_still_reports_error(tmp_path: Path):
    html_doc, _toc, _codes = render(tmp_path / "gone.md", enable_mermaid=False, dark=False)
    assert "gone.md" in html_doc


def test_load_settings_invalid_utf8_returns_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_bytes(b'{"zoom": 2.0, "theme": "\xff\xfe"}')
    assert load_settings(path=path) == DEFAULTS


def test_load_settings_non_object_json_returns_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    for payload in ("[1, 2, 3]", '"text"', "42", "null", "true"):
        path.write_text(payload, encoding="utf-8")
        assert load_settings(path=path) == DEFAULTS, payload


def test_load_settings_deeply_nested_json_returns_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text("[" * 100_000 + "]" * 100_000, encoding="utf-8")
    assert load_settings(path=path) == DEFAULTS


@pytest.mark.parametrize(
    "payload",
    [
        '{"window_w": 1e309}',
        '{"window_h": -1e309}',
        '{"window_w": NaN}',
        '{"window_h": Infinity}',
        '{"window_w": "nan"}',
        '{"window_h": "inf"}',
        '{"window_w": ' + "9" * 400 + "}",  # int too large for float
        '{"zoom": 1e309}',
        '{"zoom": "nan"}',
        '{"zoom": NaN}',
        '{"zoom": ' + "9" * 400 + "}",
        '{"window_w": true, "zoom": false}',
        '{"window_w": null, "zoom": [1], "window_h": {}}',
    ],
)
def test_load_settings_non_finite_or_bogus_numbers_use_defaults(
    tmp_path: Path, payload: str
):
    path = tmp_path / "settings.json"
    path.write_text(payload, encoding="utf-8")
    assert load_settings(path=path) == DEFAULTS


def test_load_settings_negative_and_huge_window_are_clamped(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"window_w": -50, "window_h": 1e12}), encoding="utf-8")
    loaded = load_settings(path=path)
    assert loaded["window_w"] == "200"
    assert loaded["window_h"] == "10000"


def test_load_settings_zoom_is_clamped_to_allowed_range(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"zoom": -3}), encoding="utf-8")
    assert load_settings(path=path)["zoom"] == "0.4"
    path.write_text(json.dumps({"zoom": "1e100"}), encoding="utf-8")
    assert load_settings(path=path)["zoom"] == "3.0"


def test_load_settings_valid_numbers_still_pass_through(tmp_path: Path):
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"zoom": 1.5, "window_w": "1200", "window_h": 800.0}),
        encoding="utf-8",
    )
    loaded = load_settings(path=path)
    assert loaded["zoom"] == "1.5"
    assert loaded["window_w"] == "1200"
    assert loaded["window_h"] == "800"


def test_save_settings_non_finite_values_fall_back_to_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings(
        {
            "zoom": float("nan"),
            "window_w": float("inf"),
            "window_h": "nan",
        },
        path=path,
    )
    saved = load_settings(path=path)
    assert saved["zoom"] == "1.0"
    assert saved["window_w"] == "900"
    assert saved["window_h"] == "1000"


def test_save_settings_clamps_huge_and_negative_window(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings({"window_w": "1e12", "window_h": "-7"}, path=path)
    saved = load_settings(path=path)
    assert saved["window_w"] == "10000"
    assert saved["window_h"] == "200"


def test_save_settings_int_beyond_float_range_uses_defaults(tmp_path: Path):
    path = tmp_path / "settings.json"
    save_settings({"window_w": 10**400, "zoom": 10**400}, path=path)
    saved = load_settings(path=path)
    assert saved["window_w"] == "900"
    assert saved["zoom"] == "1.0"
