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
from markdown_ext import GfmAlertExtension, LanguageGuessExtension, MermaidExtension
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


# --- LanguageGuessPreprocessor -----------------------------------------------


def render_lang(text: str) -> str:
    """Render with the language-guess preprocessor in the pipeline, mirroring
    render_body's extension order (lang-guess is registered at priority 27,
    before mermaid at 26 and extra's fenced_code at 25)."""
    mer = MermaidExtension(enable_mermaid=False, dark=False)
    md = markdown.Markdown(
        extensions=[*EXTENSIONS, mer, LanguageGuessExtension()],
        extension_configs=EXTENSION_CONFIGS,
    )
    body = md.convert(text)
    return mer.resolve(sanitize_html(body))


def test_unlabeled_python_block_gets_highlighted():
    out = render_lang("```\ndef f():\n    return 1\n```\n")
    assert '<span class="k">def</span>' in out


def test_unlabeled_bash_block_gets_highlighted():
    out = render_lang('```\nfor f in *.md; do\n  echo "$f"\ndone\n```\n')
    assert '<span class="' in out  # pygments spans present


def test_unlabeled_prose_stays_plain():
    out = render_lang("```\nJust some prose\nwithout code\n```\n")
    assert "<pre>" in out
    assert '<span class="' not in out


def test_labeled_block_keeps_declared_language():
    out = render_lang("```bash\necho hi\n```\n")
    assert 'class="codehilite"' in out


def test_closing_fence_of_labeled_block_not_mistaken_for_open():
    """The killer state-machine case: the closer after a labeled block looks
    exactly like an unlabeled opener. It must close the python block, not
    open a new one -- and must never gain an injected alias."""
    doc = "```python\ncode\n```\n\nParagraph.\n"
    out = render_lang(doc)
    assert 'class="codehilite"' in out
    assert "<p>Paragraph.</p>" in out


def test_fence_lookalikes_inside_block_are_skipped():
    """A block containing example fence lines must be walked as one block."""
    doc = "```\nexample:\n```python\nfake\n```\nreal end\n```\n"
    out = render_lang(doc)
    assert out.count("<pre>") == 1


def test_tilde_fences_supported():
    out = render_lang("~~~\ndef f():\n    return 1\n~~~\n")
    assert '<span class="k">def</span>' in out


def test_mermaid_fence_untouched():
    out = render_lang("```mermaid\ngraph TD\nA-->B\n```\n")
    assert "mermaid-disabled" in out


def test_indented_fence_left_alone():
    """python-markdown's fenced_code only accepts column-0 fences; an
    indented fence it ignores must not be rewritten either -- the injected
    alias would leak into the paragraph as visible text."""
    out = render_lang("- item\n\n  ```\n  def f():\n      return 1\n  ```\n")
    assert "python" not in out.replace("```python", "")  # no injected alias
    assert "<li>item</li>" in out


def test_mismatched_close_left_alone():
    """A longer closing fence means fenced_code won't treat the block as a
    fence at all -- the opener must stay unrewritten."""
    out = render_lang("```\nsome text\n````\n")
    assert "```python" not in out


def test_priority_registered_before_fenced_code():
    """The preprocessor must run strictly before extra's fenced_code (25)
    and mermaid (26) or it never sees the fence lines at all."""
    md = markdown.Markdown(extensions=["extra", LanguageGuessExtension()])
    idx_guess = md.preprocessors.get_index_for_name("zeile-lang-guess")
    idx_fenced = md.preprocessors.get_index_for_name("fenced_code_block")
    # lower index == higher priority == runs first
    assert idx_guess < idx_fenced


# --- GfmAlertExtension -------------------------------------------------------


def render_alert(text: str) -> str:
    md = markdown.Markdown(
        extensions=[*EXTENSIONS, GfmAlertExtension()],
        extension_configs=EXTENSION_CONFIGS,
    )
    return sanitize_html(md.convert(text))


def test_gfm_alert_simple_note():
    doc = "> [!NOTE]\n> This is a helpful note.\n"
    out = render_alert(doc)
    assert '<div class="admonition note">' in out
    assert '<p class="admonition-title">Note</p>' in out
    assert "<p>This is a helpful note.</p>" in out
    assert "<blockquote>" not in out


def test_gfm_alert_all_five_types():
    types = ["NOTE", "TIP", "IMPORTANT", "WARNING", "CAUTION"]
    for t in types:
        doc = f"> [!{t}]\n> Body for {t}.\n"
        out = render_alert(doc)
        assert f'<div class="admonition {t.lower()}">' in out
        assert f'<p class="admonition-title">{t.capitalize()}</p>' in out
        assert f"<p>Body for {t}.</p>" in out


def test_gfm_alert_custom_title():
    doc = "> [!TIP] Pro Tip\n> You can customize titles.\n"
    out = render_alert(doc)
    assert '<div class="admonition tip">' in out
    assert '<p class="admonition-title">Pro Tip</p>' in out
    assert "<p>You can customize titles.</p>" in out


def test_gfm_alert_case_insensitive():
    doc = "> [!note]\n> Lowercase marker works.\n"
    out = render_alert(doc)
    assert '<div class="admonition note">' in out
    assert '<p class="admonition-title">Note</p>' in out


def test_gfm_alert_with_formatting_and_links():
    doc = "> [!IMPORTANT]\n> An alert with **bold**, *italic*, and [link](https://example.com).\n"
    out = render_alert(doc)
    assert '<div class="admonition important">' in out
    assert "<strong>bold</strong>" in out
    assert "<em>italic</em>" in out
    assert 'href="https://example.com"' in out
    assert ">link</a>" in out


def test_gfm_alert_multiparagraph_and_lists():
    doc = "> [!WARNING]\n>\n> First warning paragraph.\n>\n> - Item 1\n> - Item 2\n"
    out = render_alert(doc)
    assert '<div class="admonition warning">' in out
    assert '<p class="admonition-title">Warning</p>' in out
    assert "<p>First warning paragraph.</p>" in out
    assert "<ul>" in out
    assert "<li>Item 1</li>" in out


def test_regular_blockquote_untouched():
    doc = "> This is just a regular quote.\n> Second line.\n"
    out = render_alert(doc)
    assert "<blockquote>" in out
    assert "admonition" not in out
    assert "regular quote." in out

