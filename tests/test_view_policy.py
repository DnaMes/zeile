# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The link policy every web view backend enforces (view.decide), and that it ships."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from view import Action, decide

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def doc(tmp_path: Path) -> Path:
    (tmp_path / "sub").mkdir()
    path = tmp_path / "a b.md"
    path.write_text("# x\n")
    return path


def test_same_document_and_local_image_load(doc: Path) -> None:
    assert decide(doc.as_uri() + "#top", doc).action is Action.LOAD
    assert decide((doc.parent / "pic.PNG").as_uri(), doc).action is Action.LOAD


def test_other_markdown_navigates_with_its_resolved_path(doc: Path) -> None:
    target = doc.parent / "sub" / "b.md"
    decision = decide(target.as_uri(), doc)
    assert (decision.action, decision.target) == (Action.NAVIGATE, target.resolve())


@pytest.mark.parametrize(
    "uri",
    [
        "https://example.com/",
        "http://example.com/a.md",
        "javascript:alert(1)",
        "mailto:a@b.c",
        "file://otherhost/etc/passwd",
        "file:///etc/passwd",
        "file:///tmp/../etc/passwd",
        "",
    ],
)
def test_everything_else_is_external(doc: Path, uri: str) -> None:
    assert decide(uri, doc).action is Action.EXTERNAL


def test_local_html_and_svg_never_load(doc: Path) -> None:
    for name in ("x.html", "x.svg"):
        assert decide((doc.parent / name).as_uri(), doc).action is Action.EXTERNAL


def test_copy_links(doc: Path) -> None:
    assert decide("zeile-copy://3", doc).copy_index == 3
    assert decide("zeile-copy://3", doc).action is Action.COPY
    assert decide("zeile-copy://x", doc).copy_index is None


@pytest.mark.parametrize(
    "staging", ["packaging/stage.sh", "packaging/flatpak/com.erdlabs.zeile.yml"]
)
def test_every_top_level_module_is_packaged(staging: str) -> None:
    """A module missing from a staging list is an ImportError in the installed app."""
    text = (REPO / staging).read_text(encoding="utf-8")
    for module in sorted(p.name for p in REPO.glob("*.py")):
        assert re.search(rf"(?<![\w]){re.escape(module)}\b", text), (
            f"{module} not in {staging}"
        )
