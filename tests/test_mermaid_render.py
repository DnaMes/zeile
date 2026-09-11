# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Tests for mermaid_render._strip_script_vectors.

The SVG mmdc produces reaches the page un-sanitized (injected after nh3's
pass via markdown_ext's nonce mechanism), so mermaid_render strips script
vectors itself. These tests pin that behaviour without needing mmdc.

The htmlLabels/foreignObject situation is NOT tested here: empirically,
mmdc 11.17.0 / mermaid 11.17.2 ignores flowchart.htmlLabels:false (node
labels come out as <foreignObject> regardless of config or %%{init}%%
directive -- verified 2026-09-11, see mermaid_render.py's comment and
HANDOFF.md). If a future mermaid honours it again, nothing breaks either
way; the document-level walls (enable-javascript-markup=False, CSP,
decide-policy) are what actually contain SVG content.
"""

from mermaid_render import _strip_script_vectors


def test_strips_script_element():
    svg = "<svg><g><script>alert(1)</script><rect/></g></svg>"
    out = _strip_script_vectors(svg)
    assert "<script" not in out.lower()
    assert "<rect/>" in out


def test_strips_script_case_insensitive_and_multiline():
    svg = "<svg>\n<SCRIPT type='text/javascript'>\nalert(1)\n</SCRIPT>\n</svg>"
    out = _strip_script_vectors(svg)
    assert "script" not in out.lower()
    assert "alert" not in out


def test_strips_on_attributes_single_and_double_quoted():
    svg = (
        '<svg onload="evil()"><img src="x" onerror=\'boom()\' onclick=plain()><rect/></svg>'
    )
    out = _strip_script_vectors(svg)
    assert "onload" not in out
    assert "onerror" not in out
    assert "onclick" not in out
    assert "<rect/>" in out
    assert 'src="x"' in out  # benign attributes untouched


def test_preserves_normal_svg_content():
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10">'
        '<text x="1" y="2">Start</text>'
        '<rect fill="#ECECFF" stroke="#333333"/></svg>'
    )
    assert _strip_script_vectors(svg) == svg


def test_label_text_containing_on_word_survives():
    """The word 'online' as TEXT or class must not be mangled by the on*
    attribute regex -- only attribute-shaped ` on...=` matches."""
    svg = '<g class="online-mode"><text>buy online today</text></g>'
    assert _strip_script_vectors(svg) == svg
