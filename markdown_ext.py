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
import subprocess

from markdown.extensions import Extension
from markdown.preprocessors import Preprocessor

import mermaid_render

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
        except mermaid_render.MermaidUnavailable:
            return (
                "<div class='mermaid-error'>Mermaid diagram: --enable-mermaid "
                "is set but 'mmdc' (mermaid-cli) was not found on PATH.</div>"
            )
        except subprocess.CalledProcessError as exc:
            return (
                "<div class='mermaid-error'>Mermaid render failed:"
                f"<pre>{html.escape(exc.stderr or str(exc))}</pre></div>"
            )
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
