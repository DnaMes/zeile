# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Unit tests for zeile.py's render_body/build_document/sanitize_html.

No GTK needed -- these are the pure-function pieces split out of render()
specifically so they're testable without a WebView or a display.
"""

import re
from pathlib import Path

from zeile import (
    BODY_FONT_OPTIONS,
    CODE_FONT_OPTIONS,
    READING_WIDTH_OPTIONS,
    THEME_OPTIONS,
    DocumentStats,
    _coerce_reading_width,
    build_document,
    classify_local_target,
    compute_document_stats,
    enhance_code_blocks,
    flatten_toc,
    is_theme_dark,
    load_settings,
    read_asset,
    render,
    render_body,
    sanitize_html,
    save_settings,
)


def test_frontmatter_stripped():
    doc = "---\ntitle: Test\ndate: 2026-01-01\n---\n\n# Hi\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert "title: Test" not in out
    assert "date: 2026-01-01" not in out
    assert '<h1 id="hi">Hi' in out
    assert 'class="headerlink"' in out


def test_frontmatter_absent_is_a_no_op():
    doc = "# Hi\n\nNo frontmatter here.\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert '<h1 id="hi">Hi' in out


def test_tasklist_renders_as_checkboxes():
    doc = "- [ ] todo\n- [x] done\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert "[ ] todo" not in out
    assert "[x] done" not in out
    assert out.count('type="checkbox"') == 2
    assert "checked" in out


def test_tasklist_html_structure_mixed_and_nested():
    """pymdownx.tasklist marks items so CSS can hide bullets on tasks only."""
    doc = "- [x] done\n- [ ] todo\n- plain\n    - nested plain\n    - [ ] nested task\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert 'class="task-list"' in out
    assert out.count('class="task-list-item"') == 3
    assert "<li>nested plain</li>" in out
    # Nested list stays a task-list; only the task child is marked.
    assert re.search(
        r'<li>plain<ul class="task-list">\s*'
        r"<li>nested plain</li>\s*"
        r'<li class="task-list-item">',
        out,
    )
    # Checkboxes stay disabled (read-only); checked and unchecked both present.
    attrs = re.findall(r'<li class="task-list-item"><input type="checkbox" ([^>]+)>', out)
    assert len(attrs) == 3
    assert all("disabled" in a for a in attrs)
    assert sum("checked" in a for a in attrs) == 1


def test_heading_gets_toc_anchor_id():
    out, _toc, _codes = render_body("# Section One\n", enable_mermaid=False, dark=False)
    assert 'id="section-one"' in out


def test_codehilite_preserves_pygments_class():
    doc = "```python\ndef f():\n    return 1\n```\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert 'class="codehilite"' in out
    assert 'class="k"' in out  # the `def` keyword token


def test_render_body_returns_toc_tokens():
    doc = "# Top\n\n## Child\n\nText.\n"
    _out, toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
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


def test_build_document_embeds_theme_and_font_attrs():
    doc = build_document(
        "<p>hi</p>",
        "my file.md",
        theme_id="catppuccin-mocha",
        body_font_id="ia-writer",
        code_font_id="jetbrains-mono",
    )
    assert 'data-theme="catppuccin-mocha"' in doc
    assert 'data-font-body="ia-writer"' in doc
    assert 'data-font-code="jetbrains-mono"' in doc
    assert "data-width=" not in re.search(r"<html[^>]*>", doc).group(0)


def test_build_document_embeds_reading_width_attr():
    def html_open(doc: str) -> str:
        match = re.search(r"<html[^>]*>", doc)
        assert match is not None
        return match.group(0)

    default = build_document("<p>hi</p>", "f.md")
    assert "data-width=" not in html_open(default)
    standard = build_document("<p>hi</p>", "f.md", reading_width="standard")
    assert "data-width=" not in html_open(standard)
    narrow = build_document("<p>hi</p>", "f.md", reading_width="narrow")
    assert 'data-width="narrow"' in html_open(narrow)
    wide = build_document("<p>hi</p>", "f.md", reading_width="wide")
    assert 'data-width="wide"' in html_open(wide)


def test_coerce_reading_width():
    for value in READING_WIDTH_OPTIONS:
        assert _coerce_reading_width(value) == value
    assert _coerce_reading_width("garbage") == "standard"
    assert _coerce_reading_width("") == "standard"
    assert _coerce_reading_width(None) == "standard"
    assert _coerce_reading_width(42) == "standard"
    assert _coerce_reading_width(["narrow"]) == "standard"


def test_theme_css_defines_required_vars():
    css = read_asset("themes.css")
    required = {
        "color-scheme",
        "bg",
        "fg",
        "muted",
        "border",
        "link",
        "code-bg",
        "quote-border",
        "quote-bg",
        "selection",
        "note",
        "warning",
        "danger",
        "accent",
        "focus",
        "table-zebra",
        "table-hover",
        "inline-code-bg",
        "syn-comment",
        "syn-keyword",
        "syn-type",
        "syn-string",
        "syn-number",
        "syn-name",
        "syn-function",
        "syn-class",
        "syn-builtin",
        "syn-tag",
        "syn-attr",
        "syn-operator",
        "syn-punctuation",
        "syn-error",
        "syn-added-fg",
        "syn-added-bg",
        "syn-removed-fg",
        "syn-removed-bg",
    }

    theme_blocks = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r'html\[data-theme="([^"]+)"\]\s*\{([^}]*)\}', css, flags=re.S
        )
    }

    for theme in THEME_OPTIONS:
        if theme == "auto":
            continue
        assert theme in theme_blocks
        vars_found = set(re.findall(r"--([a-z0-9-]+)\s*:", theme_blocks[theme], flags=re.I))
        missing = required - vars_found
        assert not missing, f"{theme} missing theme CSS vars: {', '.join(sorted(missing))}"


def test_load_settings_roundtrip_and_validation(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    save_settings(
        {
            "theme": "dracula",
            "body_font": BODY_FONT_OPTIONS[1],
            "code_font": CODE_FONT_OPTIONS[1],
            "reading_width": "wide",
            "zoom": "1.5",
            "window_w": "1200",
            "window_h": "800",
            "window_maximized": "true",
        },
        path=settings_path,
    )
    loaded = load_settings(path=settings_path)
    assert loaded == {
        "theme": "dracula",
        "body_font": BODY_FONT_OPTIONS[1],
        "code_font": CODE_FONT_OPTIONS[1],
        "reading_width": "wide",
        "zoom": "1.5",
        "window_w": "1200",
        "window_h": "800",
        "window_maximized": "true",
        "intro_seen": "false",
    }

    loaded["theme"] = "not-a-theme"
    loaded["body_font"] = "not-a-font"
    loaded["code_font"] = "not-a-font"
    loaded["reading_width"] = "not-a-width"
    loaded["zoom"] = "99"  # out of range -> clamped
    loaded["window_w"] = "garbage"  # unparseable -> default
    loaded["window_maximized"] = "not-a-bool"  # -> coerced to "false"
    save_settings(loaded, path=settings_path)
    clamped = load_settings(path=settings_path)
    assert clamped["theme"] == "auto"
    assert clamped["body_font"] == "system"
    assert clamped["code_font"] == "system"
    assert clamped["reading_width"] == "standard"
    assert float(clamped["zoom"]) == 3.0  # clamped to the upper bound
    assert clamped["window_w"] == "900"  # default
    assert clamped["window_maximized"] == "false"


def test_reading_width_settings_coercion_and_roundtrip(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    assert load_settings(path=settings_path)["reading_width"] == "standard"

    settings_path.write_text('{"theme": "nord"}', encoding="utf-8")
    assert load_settings(path=settings_path)["reading_width"] == "standard"

    for bad in (
        '{"reading_width": null}',
        '{"reading_width": 3}',
        '{"reading_width": "x"}',
    ):
        settings_path.write_text(bad, encoding="utf-8")
        assert load_settings(path=settings_path)["reading_width"] == "standard"

    save_settings({"reading_width": "narrow"}, path=settings_path)
    assert load_settings(path=settings_path)["reading_width"] == "narrow"
    save_settings(
        {**load_settings(path=settings_path), "theme": "nord"}, path=settings_path
    )
    assert load_settings(path=settings_path)["reading_width"] == "narrow"


def test_load_settings_returns_default_on_broken_file(tmp_path: Path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text("not-json", encoding="utf-8")
    assert load_settings(path=settings_path) == {
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


def test_theme_switch_persists_zoom_and_window_keys(tmp_path: Path):
    """_persist_settings must merge: theme/font changes may not wipe the
    zoom/window keys owned by the window-state saver."""
    settings_path = tmp_path / "settings.json"
    save_settings(
        {"zoom": "1.75", "window_w": "1400", "window_h": "900"}, path=settings_path
    )
    current = load_settings(path=settings_path)
    current.update({"theme": "nord", "body_font": "inter", "code_font": "fira-code"})
    save_settings(current, path=settings_path)
    merged = load_settings(path=settings_path)
    assert merged["zoom"] == "1.75"
    assert merged["window_w"] == "1400"
    assert merged["theme"] == "nord"


def test_render_end_to_end(tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text("# Hello\n\nSome *text*.\n", encoding="utf-8")
    out, toc, codes = render(md_file, enable_mermaid=False, dark=False)
    assert out.startswith("<!DOCTYPE html>")
    assert "Content-Security-Policy" in out
    assert '<h1 id="hello">Hello' in out
    assert 'class="headerlink"' in out
    assert flatten_toc(toc) == [(0, "hello", "Hello")]
    assert codes == []


def test_render_missing_file_shows_error_not_traceback(tmp_path: Path):
    missing = tmp_path / "does-not-exist.md"
    out, toc, codes = render(missing, enable_mermaid=False, dark=False)
    assert "Cannot read file" in out
    assert out.startswith("<!DOCTYPE html>")
    assert toc == []
    assert codes == []


def test_enhance_code_blocks_wraps_every_pre():
    body = (
        "<pre><code>a &lt; 1</code></pre>\n<p>text</p>\n<pre class='x'><code>b</code></pre>"
    )
    enhanced, texts = enhance_code_blocks(body)
    assert enhanced.count('<div class="code-block">') == 2
    assert 'href="zeile-copy://0"' in enhanced
    assert 'href="zeile-copy://1"' in enhanced
    # the original pre content survives untouched inside the wrapper
    assert "<pre><code>a &lt; 1</code></pre>" in enhanced
    assert "<p>text</p>" in enhanced
    # plain text extracted in document order, entities unescaped (the
    # synthetic input has no trailing newlines; real codehilite output
    # keeps the source's final \n before </code>)
    assert texts == ["a < 1", "b"]
    # copy + check icons are both present, and a title/aria-label exist
    assert 'class="ic ic-copy"' in enhanced
    assert 'class="ic ic-check"' in enhanced
    assert enhanced.count("aria-label=") == 2


def test_enhance_code_blocks_no_pre_is_noop():
    body = "<p>no code here</p>"
    enhanced, texts = enhance_code_blocks(body)
    assert enhanced == body
    assert texts == []


def test_render_adds_copy_links_and_code_texts(tmp_path: Path):
    md_file = tmp_path / "doc.md"
    md_file.write_text(
        "```python\nx = 1\n```\n\n```\ndef g():\n    return 2\n```\n",
        encoding="utf-8",
    )
    html_doc, _toc, codes = render(md_file, enable_mermaid=False, dark=False)
    assert 'href="zeile-copy://0"' in html_doc
    assert 'href="zeile-copy://1"' in html_doc
    assert codes == ["x = 1\n", "def g():\n    return 2\n"]


def test_unlabeled_code_block_gets_language_detected():
    doc = "```\ndef f():\n    return 1\n```\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    # python detected -> pygments spans present, not just the plain wrapper
    assert '<span class="k">def</span>' in out


def test_unlabeled_prose_stays_plain():
    doc = "```\nJust prose, nothing codey.\nNo signals at all.\n```\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert "<pre>" in out
    assert '<span class="' not in out.split("<pre>")[1].split("</pre>")[0]


def test_labeled_code_block_keeps_declared_language():
    doc = "```bash\necho hi\n```\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert 'class="codehilite"' in out


def test_mermaid_fence_still_disabled_placeholder_with_copy():
    doc = "```mermaid\ngraph TD\nA-->B\n```\n"
    out, _toc, codes = render_body(doc, enable_mermaid=False, dark=False)
    assert "mermaid-disabled" in out
    # the disabled mermaid source is itself a <pre> and gets a copy button
    assert 'href="zeile-copy://0"' in out
    assert codes == ["graph TD\nA-->B\n"]


def test_gfm_alerts_rendered_through_render_body():
    doc = "> [!NOTE]\n> Note body.\n\n> [!TIP] Pro Tip\n> Tip body.\n"
    out, _toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert '<div class="admonition note">' in out
    assert '<p class="admonition-title">Note</p>' in out
    assert "<p>Note body.</p>" in out
    assert '<div class="admonition tip">' in out
    assert '<p class="admonition-title">Pro Tip</p>' in out
    assert "<p>Tip body.</p>" in out


def test_compute_document_stats_empty():
    stats = compute_document_stats("")
    assert stats == DocumentStats(words=0, chars=0, reading_time_minutes=0)


def test_compute_document_stats_frontmatter_stripped():
    doc = (
        "---\n"
        "title: Ignore Frontmatter\n"
        "author: Someone\n"
        "---\n\n"
        "# Real Heading\n\n"
        "Some body text here.\n"
    )
    stats = compute_document_stats(doc)
    assert stats.words == 6
    assert stats.reading_time_minutes == 1


def test_compute_document_stats_reading_time_estimation():
    words = "word " * 250
    stats = compute_document_stats(words)
    assert stats.words == 250
    assert stats.reading_time_minutes == 2

    words_450 = "word " * 450
    stats_450 = compute_document_stats(words_450)
    assert stats_450.words == 450
    assert stats_450.reading_time_minutes == 3


def test_compute_document_stats_unicode():
    doc = "Schöne Grüße aus München! 42 Tests bestanden."
    stats = compute_document_stats(doc)
    assert stats.words == 7
    assert stats.reading_time_minutes == 1


def test_compute_document_stats_ignores_link_urls_and_markup():
    doc = (
        "Check [this guide](https://example.com/very/long/url/with/many/path/tokens) "
        "and <https://erdlabs.com/docs> for details.<br>Word two.\n\n"
        "![Inline diagram](https://example.com/img.png)\n"
        "![Reference diagram][ref-img]\n\n"
        "[ref-img]: https://example.com/ref.png\n"
    )
    stats = compute_document_stats(doc)
    # Visible words: "Check", "this", "guide", "and", "for", "details",
    # "Word", "two" -> 8 words
    assert stats.words == 8
    assert stats.reading_time_minutes == 1


def test_heading_anchor_permalinks():
    doc = "# Introduction\n\nParagraph\n\n## Section Two\n"
    out, toc, _codes = render_body(doc, enable_mermaid=False, dark=False)
    assert (
        '<h1 id="introduction">Introduction<a class="headerlink" href="#introduction"'
        in out
    )
    assert (
        '<h2 id="section-two">Section Two<a class="headerlink" href="#section-two"' in out
    )
    assert 'title="Link to this section"' in out
    assert flatten_toc(toc) == [
        (0, "introduction", "Introduction"),
        (1, "section-two", "Section Two"),
    ]


def test_style_css_heading_and_code_colors():
    css = read_asset("style.css")
    assert "color: var(--syn-function);" in css
    assert "color: var(--syn-type);" in css
    assert "border-left: 3.5px solid var(--accent);" in css
    assert "border-bottom: 2px solid var(--accent);" in css


def test_cyberpunk_theme_registered():
    assert "cyberpunk" in THEME_OPTIONS
    assert is_theme_dark("cyberpunk", fallback=False) is True


def test_classify_local_target(tmp_path: Path) -> None:
    doc = tmp_path / "doc.md"
    assert classify_local_target(tmp_path / "other.md", doc) == "navigate"
    assert classify_local_target(doc, doc) == "load"
    assert classify_local_target(tmp_path / "pic.PNG", doc) == "load"
    assert classify_local_target(tmp_path / "page.html", doc) == "external"
    assert classify_local_target(tmp_path / "x.svg", doc) == "external"
    assert classify_local_target(tmp_path.parent / "up.md", doc) == "external"
