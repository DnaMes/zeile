# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Markdown to HTML: the platform-neutral heart of zeile.

Nothing in here imports a GUI toolkit, so the same document a Linux WebKitGTK
window renders is the one a Windows WebView2 or macOS WKWebView window
renders, and the whole pipeline is testable without a display.

Three independent layers keep a document from doing anything but being read:

1. the nh3 sanitizer allowlist below strips <script>, on* handlers and
   javascript:/data: URLs outright,
2. the document carries its own Content-Security-Policy (CSP below), which
   every engine enforces -- including a WebView whose scripting setting a
   future upgrade might get wrong,
3. each shell additionally turns document script off in the webview itself
   where the platform exposes such a setting.

Layer 3 is platform-specific and can regress silently with a toolkit upgrade;
layers 1 and 2 cannot, which is why they live here.
"""

from __future__ import annotations

import html
import math
import re
from dataclasses import dataclass
from pathlib import Path

import markdown
import nh3

from i18n import _
from markdown_ext import (
    GfmAlertExtension,
    LanguageGuessExtension,
    MermaidExtension,
)
from preferences import (
    _coerce_font,
    _coerce_reading_width,
    _coerce_theme,
    is_theme_dark,
)

EXTENSIONS = [
    "extra",  # tables, fenced_code, footnotes, def_list, abbr, attr_list
    "admonition",
    "codehilite",
    "sane_lists",
    "smarty",
    "toc",
    "pymdownx.tasklist",
]

EXTENSION_CONFIGS = {
    "codehilite": {"guess_lang": False, "noclasses": False},
    "toc": {"permalink": "#", "permalink_title": _("Link to this section")},
    "pymdownx.tasklist": {"custom_checkbox": False},
}


# A YAML frontmatter block, stripped before conversion -- python-markdown has
# no opinion on frontmatter, so left alone it renders as a literal <hr> plus
# a paragraph of raw "key: value" text, confirmed broken. Anchored to the
# very start of the document; the closing "---" must be alone on its own
# line, same shape most static-site generators use.
_FRONTMATTER_RE = re.compile(r"\A---\n.*?\n---\n?", re.DOTALL)


def _strip_frontmatter(text: str) -> str:
    return _FRONTMATTER_RE.sub("", text, count=1)


def _visible_text(text: str) -> str:
    """Extract visible document text for reading statistics.

    Strips frontmatter, link URLs (keeping visible anchor text), image definitions,
    HTML tags, reference-style links, and bare URLs so only readable words are counted.
    """
    clean = _strip_frontmatter(text)
    clean = re.sub(r"^\s*\[[^\]]+\]:\s*\S+.*$", "", clean, flags=re.MULTILINE)
    clean = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", clean)
    clean = re.sub(r"!\[([^\]]*)\]\[[^\]]*\]", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", clean)
    clean = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", clean)
    clean = re.sub(r"<[^>]+>", " ", clean)
    clean = re.sub(r"https?://\S+", "", clean)
    return clean


@dataclass(frozen=True)
class DocumentStats:
    words: int
    chars: int
    reading_time_minutes: int


def compute_document_stats(text: str) -> DocumentStats:
    """Compute word count, character count, and estimated reading time.

    Frontmatter, link destinations, images, and markup are stripped prior to counting.
    Words are counted via Unicode word tokens. Estimated reading time assumes
    standard 200 WPM silent reading speed.
    """
    visible = _visible_text(text)
    words = len(re.findall(r"\b\w+\b", visible))
    chars = len(visible)
    reading_time = max(1, math.ceil(words / 200)) if words > 0 else 0
    return DocumentStats(words=words, chars=chars, reading_time_minutes=reading_time)


# No script-src entry: enable-javascript-markup=False (set on the WebView
# below) already prevents any document <script> from running, and nh3 (see
# sanitize_html()) strips <script> tags outright regardless. This CSP layer
# exists for the non-script vector that needs no script at all -- an
# `<img src=http://tracker/pixel>` beacon -- which img-src 'self' kills.
# style-src allows inline <style> since we own all page styling ourselves
# and inject it as a literal <style> block below.
_CSP = (
    "default-src 'none'; img-src 'self' data:; font-src 'self' data:; "
    "style-src 'unsafe-inline'"
)

# nh3's own defaults strip `class`/`id` from most tags. Used as-is that
# silently breaks codehilite's <span class="k"> (colourless syntax
# highlighting), every heading id (kills TOC anchors), and footnote id/href
# pairs -- confirmed empirically before wiring this in. Mermaid diagrams are
# deliberately NOT special-cased here: they never reach the sanitizer as SVG
# markup at all (see markdown_ext.MermaidExtension's nonce mechanism), so
# this allowlist stays exactly as narrow as the plain-markdown features
# above actually need.
_ALLOWED_TAGS = nh3.ALLOWED_TAGS | {"input"}
_ALLOWED_ATTRIBUTES = {
    **nh3.ALLOWED_ATTRIBUTES,
    "abbr": {"title"},
    "h1": {"id"},
    "h2": {"id"},
    "h3": {"id"},
    "h4": {"id"},
    "h5": {"id"},
    "h6": {"id"},
    "span": {"class"},
    "code": {"class"},
    "pre": {"class"},
    "div": {"class"},
    "p": {"class"},
    "ul": {"class"},
    "li": {"id", "class"},
    "sup": {"id"},
    "a": {"id", "href", "class", "name"},
    # pymdownx.tasklist checkboxes -- read-only, `disabled` is load-bearing
    # (without it a click would try to toggle state nothing persists).
    "input": {"type", "disabled", "checked"},
}


def sanitize_html(body: str) -> str:
    """Strip everything nh3.clean() doesn't explicitly allow.

    Runs on markdown's converted output, which includes not just markdown
    syntax but any raw HTML a .md source embeds directly (the `extra`
    bundle's html passthrough) -- <script>, on* handlers, javascript:/data:
    URLs, <iframe>/<object>/<embed>, meta-refresh and <style> blocks are all
    removed here, verified empirically against nh3's actual default+override
    behaviour rather than assumed from its docs.
    """
    return nh3.clean(body, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRIBUTES)


# Code blocks are <pre>...</pre> (codehilite wraps some in a .codehilite
# div, plain/indented ones are bare). Non-greedy so each block maps to one
# match; a <pre> can never nest inside another in valid HTML.
_PRE_BLOCK_RE = re.compile(r"<pre\b[^>]*>.*?</pre>", re.S)

# Copy affordance for code blocks. The button is an <a> with a zeile-copy:
# URI, NOT a <button> with JS: document JavaScript is structurally disabled
# (enable_javascript-markup=False), so an in-page click handler could never
# run. Clicking the link fires decide-policy instead (a navigation attempt
# is pure HTML, no script involved), where the scheme is intercepted and
# the block's plain text -- captured here at render time -- is put on the
# GTK clipboard. The markup is injected *after* sanitize_html() (the same
# post-sanitizer pattern MermaidExtension.resolve uses) and contains only
# our own static strings plus an int index, so it widens the sanitizer's
# attack surface by nothing. A hostile .md embedding its own zeile-copy:
# link can at worst copy a block of its own content.
_COPY_ICONS = (
    '<svg class="ic ic-copy" viewBox="0 0 16 16" width="14" height="14"'
    ' aria-hidden="true"><rect x="5.5" y="5.5" width="8.5" height="8.5" rx="1.6"'
    ' fill="none" stroke="currentColor" stroke-width="1.4"/>'
    '<path d="M10.5 5.5V3.9A1.4 1.4 0 0 0 9.1 2.5H3.9A1.4 1.4 0 0 0 2.5 3.9'
    'v5.2a1.4 1.4 0 0 0 1.4 1.4h1.6" fill="none" stroke="currentColor"'
    ' stroke-width="1.4"/></svg>'
    '<svg class="ic ic-check" viewBox="0 0 16 16" width="14" height="14"'
    ' aria-hidden="true"><path d="M3 8.5 6.5 12 13 4.5" fill="none"'
    ' stroke="currentColor" stroke-width="1.8" stroke-linecap="round"'
    ' stroke-linejoin="round"/></svg>'
)


def _pre_plain_text(pre_html: str) -> str:
    """Plain text content of a rendered <pre> block (tags stripped,
    entities unescaped). The input came out of the sanitizer, so no raw
    unescaped '<' can hide in a text node."""
    return html.unescape(re.sub(r"<[^>]+>", "", pre_html))


def enhance_code_blocks(body: str) -> tuple[str, list[str]]:
    """Wrap every <pre> block with a copy affordance.

    Returns (new_body, plain_texts): plain_texts[i] is what clicking the
    i-th block's copy link puts on the clipboard, in document order.
    """
    texts: list[str] = []

    def _wrap(match: re.Match[str]) -> str:
        idx = len(texts)
        texts.append(_pre_plain_text(match.group(0)))
        return (
            '<div class="code-block">'
            f'<a class="code-copy" href="zeile-copy://{idx}"'
            f' title="{html.escape(_("Copy"))}"'
            f' aria-label="{html.escape(_("Copy code"))}">'
            f"{_COPY_ICONS}</a>{match.group(0)}</div>"
        )

    return _PRE_BLOCK_RE.sub(_wrap, body), texts


def read_asset(name: str) -> str:
    """Return the contents of an asset shipped next to this script."""
    return (Path(__file__).resolve().parent / "assets" / name).read_text(encoding="utf-8")


def render_body(
    text: str,
    *,
    enable_mermaid: bool,
    dark: bool,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
) -> tuple[str, list[dict], list[str]]:
    """Convert markdown text to sanitized HTML body content.

    Pure function -- no file I/O, no GTK -- so it's unit-testable directly.
    Returns (body, toc_tokens, code_texts): the `toc` extension already
    computes a heading tree for anchor generation, so the TOC overlay reuses
    it instead of re-deriving it from the rendered HTML; code_texts is the
    plain text of each code block in document order (see
    enhance_code_blocks), consumed by the copy-to-clipboard handler.

    body_font_id/code_font_id don't change the body HTML -- fonts are applied
    purely in CSS via data-font-* attributes on <html> (see build_document) --
    but they're accepted here so render() can forward the full setting set
    without the call sites needing to know which knobs affect which stage.
    """
    # Mermaid SVGs are pre-rendered with a light/dark palette baked in, so a
    # theme's darkness (not the system preference) decides the mmdc theme.
    theme_dark = is_theme_dark(theme_id, fallback=dark)
    text = _strip_frontmatter(text)
    mermaid_ext = MermaidExtension(enable_mermaid=enable_mermaid, dark=theme_dark)
    md = markdown.Markdown(
        extensions=[
            *EXTENSIONS,
            mermaid_ext,
            LanguageGuessExtension(),
            GfmAlertExtension(),
        ],
        extension_configs=EXTENSION_CONFIGS,
    )
    body = md.convert(text)
    body = sanitize_html(body)
    body = mermaid_ext.resolve(body)
    body, code_texts = enhance_code_blocks(body)
    return body, md.toc_tokens, code_texts  # type: ignore[attr-defined]


def build_document(
    body: str,
    title: str,
    *,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
    reading_width: str = "standard",
) -> str:
    """Wrap a sanitized HTML body in the full page shell (CSP, stylesheet)."""
    theme_id = _coerce_theme(theme_id)
    body_font_id = _coerce_font(body_font_id, kind="body")
    code_font_id = _coerce_font(code_font_id, kind="code")
    reading_width = _coerce_reading_width(reading_width)

    theme_attr = f' data-theme="{html.escape(theme_id)}"' if theme_id != "auto" else ""
    font_body_attr = f' data-font-body="{html.escape(body_font_id)}"'
    font_code_attr = f' data-font-code="{html.escape(code_font_id)}"'
    # Absent for the default so existing documents stay visually unchanged.
    width_attr = (
        f' data-width="{html.escape(reading_width)}"' if reading_width != "standard" else ""
    )
    stylesheet = read_asset("style.css") + "\n" + read_asset("themes.css")

    return (
        "<!DOCTYPE html><html"
        f"{theme_attr}{font_body_attr}{font_code_attr}{width_attr}>"
        "<head><meta charset='utf-8'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"{_CSP}\">"
        f"<title>{html.escape(title)}</title>"
        f"<style>{stylesheet}</style>"
        "</head><body><article class='markdown-body'>"
        f"{body}</article></body></html>"
    )


def render(
    path: Path,
    *,
    enable_mermaid: bool,
    dark: bool,
    theme_id: str = "auto",
    body_font_id: str = "system",
    code_font_id: str = "system",
    reading_width: str = "standard",
) -> tuple[str, list[dict], list[str]]:
    """Read `path`, render and sanitize markdown.

    Returns (html_doc, toc_tokens, code_texts) -- code_texts being the
    plain text of each code block in document order, for the clipboard.
    """
    code_texts: list[str] = []
    try:
        # Malformed bytes become U+FFFD instead of aborting the whole render.
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        body = f"<h1>{_('Cannot read file')}</h1><pre>{html.escape(str(exc))}</pre>"
        toc_tokens: list[dict] = []
    else:
        body, toc_tokens, code_texts = render_body(
            text,
            enable_mermaid=enable_mermaid,
            dark=dark,
            theme_id=theme_id,
            body_font_id=body_font_id,
            code_font_id=code_font_id,
        )

    return (
        build_document(
            body,
            path.name,
            theme_id=theme_id,
            body_font_id=body_font_id,
            code_font_id=code_font_id,
            reading_width=reading_width,
        ),
        toc_tokens,
        code_texts,
    )


def flatten_toc(tokens: list[dict], depth: int = 0) -> list[tuple[int, str, str]]:
    """Flatten the `toc` extension's nested heading tree to (depth, id, name)."""
    flat: list[tuple[int, str, str]] = []
    for token in tokens:
        flat.append((depth, token["id"], token["name"]))
        flat.extend(flatten_toc(token.get("children", []), depth + 1))
    return flat


_MARKDOWN_SUFFIXES = {".md", ".markdown"}
# Local files WebKit may load directly in the view. Anything else (.html, .svg,
# ...) would render without the generated document's CSP and sanitizer, so it
# goes to the system opener instead.
_DIRECT_LOAD_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif"}


def classify_local_target(target: Path, document: Path) -> str:
    """Decide what a link to a local file does: "navigate", "load" or "external"."""
    if not target.is_relative_to(document.parent):
        return "external"
    suffix = target.suffix.lower()
    if target == document:
        return "load"  # reload / same-document navigation stays in the view
    if suffix in _MARKDOWN_SUFFIXES:
        return "navigate"
    return "load" if suffix in _DIRECT_LOAD_SUFFIXES else "external"
