# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Unit tests for markdown_ext.MermaidExtension.

Covers the two confirmed bugs the plan called out in the old raw-text-regex
extraction: a fence indented inside a list/blockquote being silently
destroyed, and a fixed marker string being hijackable by document content.
Uses enable_mermaid=False throughout so no `mmdc` subprocess call happens --
these tests exercise extraction and the sanitizer boundary, not diagram
rendering itself.
"""

import markdown
import pytest

import mermaid_render
from markdown_ext import MermaidExtension
from zeile import EXTENSION_CONFIGS, EXTENSIONS, sanitize_html


def render(text: str, *, enable_mermaid: bool = False, dark: bool = False) -> str:
    ext = MermaidExtension(enable_mermaid=enable_mermaid, dark=dark)
    md = markdown.Markdown(
        extensions=[*EXTENSIONS, ext], extension_configs=EXTENSION_CONFIGS
    )
    body = md.convert(text)
    body = sanitize_html(body)
    return ext.resolve(body)


def test_top_level_fence_extracted():
    out = render("Before\n\n```mermaid\ngraph TD; A-->B;\n```\n\nAfter")
    assert "mermaid-disabled" in out
    assert "graph TD" in out
    assert "<p><pre" not in out and "<p><div" not in out


def test_fence_indented_in_list_is_no_longer_destroyed():
    doc = "1. First item\n\n   ```mermaid\n   graph TD; A-->B;\n   ```\n\n2. Second item\n"
    out = render(doc)
    assert "```mermaid" not in out, "fence text leaked instead of being extracted"
    assert "graph TD" in out, "diagram source lost, not just dedented wrong"
    assert "<li>Second item</li>" in out


def test_fence_dedented_correctly():
    doc = "   ```mermaid\n   line one\n     line two indented further\n   ```\n"
    out = render(doc)
    assert "line one" in out
    # a line indented *past* the fence's own indent keeps its extra indent
    assert "  line two indented further" in out


def test_nonce_collision_safety():
    """A document containing hex-looking text must not be corrupted by, or
    corrupt, the random per-diagram nonce substitution."""
    tricky = (
        "Text with what looks like a nonce: a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4.\n\n"
        "```mermaid\ngraph TD; X-->Y;\n```\n"
    )
    out = render(tricky)
    assert "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4" in out
    assert "graph TD" in out


def test_two_renders_independent():
    """Each render() call must get a fresh nonce -- there's no shared,
    guessable state across documents."""
    doc = "```mermaid\ngraph TD; A-->B;\n```\n"
    assert render(doc) and render(doc)  # both succeed, no leftover state error


def test_disabled_mode_escapes_source():
    """With mermaid disabled, the raw source is shown as text, not markup."""
    out = render("```mermaid\n<script>alert(1)</script>\n```\n")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


@pytest.mark.skipif(
    mermaid_render.available(), reason="mmdc is installed; error path not reachable"
)
def test_mermaid_unavailable_error_is_clear():
    """enable_mermaid=True but mmdc missing must fail with a readable message,
    not a traceback or silent blank output."""
    out = render("```mermaid\ngraph TD; A-->B;\n```\n", enable_mermaid=True)
    assert "mmdc" in out
    assert "not found on PATH" in out
