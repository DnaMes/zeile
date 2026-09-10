# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Unit tests for zeile.py's render_body/build_document/sanitize_html.

No GTK needed -- these are the pure-function pieces split out of render()
specifically so they're testable without a WebView or a display.
"""

from pathlib import Path

from zeile import build_document, flatten_toc, render, render_body, sanitize_html


def test_frontmatter_stripped():
    doc = "---\ntitle: Test\ndate: 2026-01-01\n---\n\n# Hi\n"
    out, _toc = render_body(doc, enable_mermaid=False, dark=False)
    assert "title: Test" not in out
    assert "date: 2026-01-01" not in out
    assert '<h1 id="hi">Hi</h1>' in out


def test_frontmatter_absent_is_a_no_op():
    doc = "# Hi\n\nNo frontmatter here.\n"
    out, _toc = render_body(doc, enable_mermaid=False, dark=False)
    assert '<h1 id="hi">Hi</h1>' in out


def test_tasklist_renders_as_checkboxes():
    doc = "- [ ] todo\n- [x] done\n"
    out, _toc = render_body(doc, enable_mermaid=False, dark=False)
    assert "[ ] todo" not in out
    assert "[x] done" not in out
    assert out.count('type="checkbox"') == 2
    assert "checked" in out


def test_heading_gets_toc_anchor_id():
    out, _toc = render_body("# Section One\n", enable_mermaid=False, dark=False)
    assert 'id="section-one"' in out


def test_codehilite_preserves_pygments_class():
    doc = "```python\ndef f():\n    return 1\n```\n"
    out, _toc = render_body(doc, enable_mermaid=False, dark=False)
    assert 'class="codehilite"' in out
    assert 'class="k"' in out  # the `def` keyword token


def test_render_body_returns_toc_tokens():
    doc = "# Top\n\n## Child\n\nText.\n"
    _out, toc = render_body(doc, enable_mermaid=False, dark=False)
    flat = flatten_toc(toc)
    assert flat == [(0, "top", "Top"), (1, "child", "Child")]


def test_flatten_toc_nested():
    tokens = [
        {
            "level": 1,
            "id": "a",
            "name": "A",
            "children": [{"level": 2, "id": "b", "name": "B", "children": []}],
        },
        {"level": 1, "id": "c", "name": "C", "children": []},
    ]
    assert flatten_toc(tokens) == [(0, "a", "A"), (1, "b", "B"), (0, "c", "C")]


def test_sanitizer_strips_script_tag():
    out = sanitize_html("<p>hi</p><script>alert(1)</script>")
    assert "<script>" not in out
    assert "alert(1)" not in out


def test_sanitizer_strips_event_handler():
    out = sanitize_html('<img src="x" onerror="alert(1)">')
    assert "onerror" not in out


def test_sanitizer_strips_javascript_href():
    out = sanitize_html('<a href="javascript:alert(1)">x</a>')
    assert "javascript:" not in out


def test_sanitizer_strips_style_block():
    out = sanitize_html("<style>body{color:red}</style><p>hi</p>")
    assert "<style>" not in out
    assert "color:red" not in out


def test_sanitizer_preserves_footnote_anchors():
    out = sanitize_html('<sup id="fnref:1"><a href="#fn:1">1</a></sup>')
    assert 'id="fnref:1"' in out
    assert 'href="#fn:1"' in out


def test_build_document_has_csp_and_title():
    doc = build_document("<p>hi</p>", "my file.md")
    assert doc.startswith("<!DOCTYPE html>")
    assert "Content-Security-Policy" in doc
    assert "default-src 'none'" in doc
    assert "<title>my file.md</title>" in doc
    assert "<p>hi</p>" in doc


def test_render_end_to_end(tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Hello\n\nSome *text*.\n", encoding="utf-8")
    out, toc = render(md_file, enable_mermaid=False, dark=False)
    assert out.startswith("<!DOCTYPE html>")
    assert "Content-Security-Policy" in out
    assert '<h1 id="hello">Hello</h1>' in out
    assert flatten_toc(toc) == [(0, "hello", "Hello")]


def test_render_missing_file_shows_error_not_traceback(tmp_path: Path):
    missing = tmp_path / "does-not-exist.md"
    out, toc = render(missing, enable_mermaid=False, dark=False)
    assert "Cannot read file" in out
    assert out.startswith("<!DOCTYPE html>")
    assert toc == []
