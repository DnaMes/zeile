#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Custom python-markdown preprocessor for ```mermaid fences.

Replaces the old approach: extracting fences from the raw source string
before markdown.convert() saw it, and re-inserting rendered output afterward
by string-replacing a fixed marker like "MDVIEW-MERMAID-0". That had two
confirmed bugs: a fence indented inside a list or blockquote never matched a
regex anchored to column 0, and a document that happened to contain that
literal marker text hijacked a real diagram's slot.

This preprocessor fixes both: it captures the fence's own indentation instead
of assuming column 0, and it never emits the rendered diagram into text that
untrusted markdown source or the HTML sanitizer ever sees. Each diagram gets
a random per-render nonce; the preprocessor stashes the nonce (not the
diagram) via md.htmlStash so the block parser doesn't wrap it in a stray
<p>, and the caller in zeile.py substitutes the real rendered HTML back in
*after* running the sanitizer over the nonce-bearing body. The sanitizer
therefore never has to reason about SVG content at all.
"""

from __future__ import annotations

import html
import re
import secrets
import xml.etree.ElementTree as etree

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor

import mermaid_render
from code_lang import guess_code_language

FENCE_RE = re.compile(
    r"^(?P<indent>[ \t]*)```mermaid[ \t]*\n"
    r"(?P<body>.*?)"
    r"^(?P=indent)```[ \t]*$",
    re.DOTALL | re.MULTILINE,
)


def _dedent(body: str, indent: str) -> str:
    """Strip a fence's own indentation from each line of its body.

    A line that is shorter than the fence's indent (e.g. a blank line) is
    left as-is rather than having leading whitespace stripped from it --
    that would silently reindent content nested inside the diagram source.
    """
    if not indent:
        return body
    return "\n".join(
        line[len(indent) :] if line.startswith(indent) else line
        for line in body.split("\n")
    )


class MermaidPreprocessor(Preprocessor):
    def __init__(self, md, enable_mermaid: bool, dark: bool) -> None:
        super().__init__(md)
        self.enable_mermaid = enable_mermaid
        self.dark = dark
        # nonce -> rendered HTML for this run, consumed by MermaidExtension.resolve()
        self.pending: dict[str, str] = {}

    def run(self, lines: list[str]) -> list[str]:
        self.pending.clear()
        text = "\n".join(lines)
        text = FENCE_RE.sub(self._replace, text)
        return text.split("\n")

    def _replace(self, match: re.Match[str]) -> str:
        source = _dedent(match.group("body"), match.group("indent"))
        nonce = secrets.token_hex(16)
        self.pending[nonce] = self._render(source)
        return self.md.htmlStash.store(nonce)

    def _render(self, source: str) -> str:
        if not self.enable_mermaid:
            return f"<pre class='mermaid-disabled'>{html.escape(source)}</pre>"
        try:
            svg = mermaid_render.render_svg(source, dark=self.dark)
        except mermaid_render.MermaidRenderError as exc:
            return mermaid_render.error_html(exc.kind, detail=exc.detail, source=source)
        return f"<div class='mermaid-diagram'>{svg}</div>"


class MermaidExtension(Extension):
    def __init__(self, **kwargs) -> None:
        self.config = {
            "enable_mermaid": [False, "Render mermaid fences via mmdc"],
            "dark": [False, "Use dark theme for mermaid diagrams"],
        }
        self.preprocessor: MermaidPreprocessor | None = None
        super().__init__(**kwargs)

    def extendMarkdown(self, md) -> None:
        self.preprocessor = MermaidPreprocessor(
            md, self.getConfig("enable_mermaid"), self.getConfig("dark")
        )
        # `extra`'s fenced_code_block preprocessor also registers at priority
        # 25 -- confirmed empirically that ties go to whichever registered
        # first, which is fenced_code_block since EXTENSIONS lists "extra"
        # before this extension. Must run strictly before it (26) or a
        # ```mermaid fence gets consumed as an ordinary code block first.
        md.preprocessors.register(self.preprocessor, "mermaid", 26)

    def resolve(self, body: str) -> str:
        """Substitute rendered diagrams into `body`, once it has been sanitized.

        Must be called after the sanitizer, not before -- the whole point of
        stashing a nonce instead of the diagram is that the sanitizer never
        sees SVG markup.

        The nonce itself (plain hex, no markup) doesn't look like block-level
        HTML to markdown's paragraph processor, so it usually ends up wrapped
        as `<p>{nonce}</p>` -- confirmed empirically. The fragments here are
        always block-level (<pre>/<div>), so leaving that wrapper in place
        would nest a <div> inside a <p>, which is invalid and gets silently
        "fixed" by the HTML parser at render time. Strip the wrapper when
        present; fall back to a bare substitution for any other context
        (e.g. a fence inside a list item may wrap differently).
        """
        assert self.preprocessor is not None, "extendMarkdown() was not called"
        for nonce, fragment in self.preprocessor.pending.items():
            wrapped = re.compile(rf"<p>{re.escape(nonce)}</p>")
            if wrapped.search(body):
                body = wrapped.sub(lambda _m: fragment, body, count=1)
            else:
                body = body.replace(nonce, fragment, 1)
        return body


class LanguageGuessPreprocessor(Preprocessor):
    """Add a detected language to *unlabeled* fenced code blocks.

    A fence with no info string renders as plain uncoloured code (codehilite
    runs with guess_lang deliberately off -- Pygments' guess_lexer misfires
    badly on short snippets, see code_lang.py). This preprocessor scans
    fences and, for blocks with an empty info string, runs code_lang's
    detector over the body and writes the detected alias into the fence line
    so codehilite highlights the block as if the author had tagged it.

    It mirrors python-markdown's own FENCED_BLOCK_RE acceptance exactly
    (verified against the installed source): opening fence at column 0,
    closing fence the *identical* string (` ```` vs ` ``` ` lengths matter)
    at column 0 with only trailing spaces. A fence shape fenced_code itself
    would not treat as a block (indented, longer/shorter closer, no closer)
    is left completely alone -- rewriting a line fenced_code ignores would
    leak the injected alias into the surrounding paragraph as visible text.
    Labeled fences and ```mermaid fences are never touched either, and the
    scanner jumps past each consumed block, so a code block *containing*
    example fence lines is walked correctly.
    """

    _FENCE_OPEN = re.compile(r"^(?P<fence>[`~]{3,})[ ]*(?P<info>.*?)[ ]*$")

    def run(self, lines: list[str]) -> list[str]:
        out = list(lines)
        n = len(out)
        i = 0
        while i < n:
            m = self._FENCE_OPEN.match(out[i])
            if not m:
                i += 1
                continue
            info = m.group("info").strip()
            fence = m.group("fence")
            # Exact same fence string at column 0, trailing spaces only --
            # precisely what fenced_code's (?P=fence)[ ]*$ requires.
            close_re = re.compile(r"^" + re.escape(fence) + r"[ ]*$")
            j = i + 1
            while j < n and not close_re.match(out[j]):
                j += 1
            if j < n and not info:
                # fenced_code-recognized block with no language: detect.
                lang = guess_code_language("\n".join(out[i + 1 : j]))
                if lang:
                    out[i] = fence + lang
            # Jump past the whole block either way: labeled blocks need no
            # rewrite, and inner lines must not be re-scanned as opens.
            i = j + 1 if j < n else n
        return out


class LanguageGuessExtension(Extension):
    """Wire LanguageGuessPreprocessor into the markdown pipeline."""

    def extendMarkdown(self, md) -> None:
        pre = LanguageGuessPreprocessor(md)
        # 27: strictly before extra's fenced_code (25) and the mermaid
        # preprocessor (26) -- same ordering constraint MermaidExtension
        # documents; ties go to whichever registered first, so be explicit.
        md.preprocessors.register(pre, "zeile-lang-guess", 27)


GFM_ALERT_RE = re.compile(
    r"^\[!(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*"
    r"(?P<title>[^\n]*)(?:\n(?P<rest>.*))?$",
    re.DOTALL | re.IGNORECASE,
)


class GfmAlertTreeprocessor(Treeprocessor):
    """Transform GitHub-Flavored Markdown alert blockquotes into admonitions.

    Matches blockquotes whose paragraphs begin with `[!NOTE]`, `[!TIP]`,
    `[!IMPORTANT]`, `[!WARNING]`, or `[!CAUTION]`. Converts each alert section
    into `<div class="admonition {kind}">` and prepends an admonition title
    (`<p class="admonition-title">Title</p>`).

    Handles adjacent alerts and mixed blockquote/alert sections by splitting
    them into distinct sibling blocks in their parent container.

    Runs at priority 25 (before `inline` at 20), so inline markup in the body
    and title is parsed naturally afterwards and the first paragraph's text has
    not yet been partitioned into child elements.
    """

    def run(self, root: etree.Element) -> None:
        self._process_element(root)

    def _process_element(self, parent: etree.Element) -> None:
        new_children: list[etree.Element] = []
        for child in parent:
            if child.tag == "blockquote":
                sub_blocks = self._split_blockquote(child)
                for sb in sub_blocks:
                    self._process_element(sb)
                new_children.extend(sub_blocks)
            else:
                self._process_element(child)
                new_children.append(child)
        parent[:] = new_children

    def _split_blockquote(self, bq: etree.Element) -> list[etree.Element]:
        has_alert = any(c.tag == "p" and c.text and GFM_ALERT_RE.match(c.text) for c in bq)
        if not has_alert:
            return [bq]

        blocks: list[etree.Element] = []
        current_block: etree.Element | None = None

        for c in bq:
            m = GFM_ALERT_RE.match(c.text) if (c.tag == "p" and c.text) else None
            if m:
                kind = m.group("kind").lower()
                custom_title = m.group("title").strip()
                rest = m.group("rest")
                title = custom_title if custom_title else kind.capitalize()

                current_block = etree.Element("div", {"class": f"admonition {kind}"})
                title_el = etree.Element("p", {"class": "admonition-title"})
                title_el.text = title
                current_block.append(title_el)

                if rest is not None and rest.strip():
                    c.text = rest.lstrip("\n")
                    current_block.append(c)
                blocks.append(current_block)
            else:
                if current_block is not None:
                    current_block.append(c)
                else:
                    if not blocks or blocks[-1].tag != "blockquote":
                        current_block = etree.Element("blockquote")
                        blocks.append(current_block)
                    else:
                        current_block = blocks[-1]
                    current_block.append(c)

        return blocks


class GfmAlertExtension(Extension):
    """Wire GfmAlertTreeprocessor into the markdown pipeline."""

    def extendMarkdown(self, md) -> None:
        md.treeprocessors.register(GfmAlertTreeprocessor(md), "zeile-gfm-alerts", 25)
