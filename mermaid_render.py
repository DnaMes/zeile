#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Render Mermaid diagram source to static SVG via the mmdc CLI.

Pre-rendering to SVG at markdown-render time means the document WebView never
runs mermaid.js itself, so there is no live JS renderer to keep working once
enable-javascript-markup=False blocks document script. mmdc (mermaid-cli)
pulls a headless Chromium via Puppeteer at install time (~300 MB), so this
stays opt-in behind --enable-mermaid rather than a base dependency.
"""

from __future__ import annotations

import gettext
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Same domain as zeile.py; local fallback avoids importing zeile (circular).
_translation = gettext.translation(
    "zeile", localedir=Path(__file__).resolve().parent / "locale", fallback=True
)
_ = _translation.gettext

# Disables mermaid's foreignObject/htmlLabels rendering path for the diagram
# types that expose the option, so mmdc emits plain SVG <text>/<tspan> labels
# instead of <foreignObject><div xmlns="...">...</div></foreignObject>.
#
# 2026-09-11, empirically verified for the first time (mmdc 11.17.0 /
# mermaid 11.17.2): this config is IGNORED for flowchart node labels —
# neither the config file nor a %%{init}%% directive nor
# defaultRenderer:"native" keeps labels out of foreignObject. It likely
# worked on older mermaid and may work again, so it stays. The actual walls
# are document-level anyway (enable-javascript-markup=False blocks <script>
# and on*= handlers document-wide, CSP default-src 'none', decide-policy);
# _strip_script_vectors() below adds a belt-and-suspenders pass over the
# SVG mmdc hands back, because that output reaches the page un-sanitized
# (injected after nh3's pass, see markdown_ext's nonce mechanism).
_MERMAID_CONFIG = json.dumps(
    {
        "flowchart": {"htmlLabels": False},
        "class": {"htmlLabels": False},
        "state": {"htmlLabels": False},
    }
)

# A <script> element (with any content up to its closing tag) or an on*=
# event-handler attribute anywhere in mmdc's SVG output is a mermaid-level
# sanitizer regression and gets stripped here. Bounded by design: this runs
# over the diagram SVG mmdc produced for us, not over arbitrary user input.
_SCRIPT_RE = re.compile(r"<script\b[^>]*>.*?</script\s*>", re.DOTALL | re.IGNORECASE)
_ON_ATTR_RE = re.compile(r'\s+on[a-zA-Z]+\s*=\s*("[^"]*"|\'[^\']*\'|[^\s>]+)')

RENDER_TIMEOUT_SEC = 30.0
MAX_SVG_CHARS = 1_000_000


def _strip_script_vectors(svg: str) -> str:
    svg = _SCRIPT_RE.sub("", svg)
    return _ON_ATTR_RE.sub("", svg)


_cache: dict[str, str] = {}


class MermaidRenderError(RuntimeError):
    """User-visible mmdc failure; ``kind`` selects the translated title."""

    def __init__(self, kind: str, detail: str = "") -> None:
        self.kind = kind
        self.detail = detail
        super().__init__(kind)


class MermaidUnavailable(MermaidRenderError):
    """Raised when a diagram needs rendering but mmdc is not on PATH."""

    def __init__(self) -> None:
        super().__init__("missing")


def available() -> bool:
    return shutil.which("mmdc") is not None


def error_html(kind: str, *, detail: str = "", source: str = "") -> str:
    """Build a mermaid-error div; title is translated, detail/source escaped."""
    titles = {
        "missing": _(
            "Mermaid diagram: --enable-mermaid is set but 'mmdc' "
            "(mermaid-cli) was not found on PATH."
        ),
        "timeout": _("Mermaid render timed out."),
        "empty": _("Mermaid render produced empty output."),
        "oversized": _("Mermaid render produced oversized output."),
        "failed": _("Mermaid render failed:"),
        "oserror": _("Mermaid render failed:"),
    }
    title = titles.get(kind, _("Mermaid render failed:"))
    parts = [f"<div class='mermaid-error'>{html.escape(title)}"]
    if detail:
        parts.append(f"<pre>{html.escape(detail)}</pre>")
    if source:
        parts.append(f"<pre>{html.escape(source)}</pre>")
    parts.append("</div>")
    return "".join(parts)


def _decode(data: bytes | str | None) -> str:
    """mmdc output as text; invalid UTF-8 becomes U+FFFD instead of raising."""
    if isinstance(data, bytes):
        return data.decode("utf-8", errors="replace")
    return data or ""


def render_svg(source: str, *, dark: bool, timeout: float = RENDER_TIMEOUT_SEC) -> str:
    """Render Mermaid diagram source to an SVG string.

    Cached by (source, theme) so an unchanged diagram isn't re-shelled-out to
    on every debounced reload. Raises MermaidRenderError (or MermaidUnavailable)
    on any mmdc failure; never leaves an uncaught subprocess/OS error.
    """
    key = hashlib.sha256(f"{dark}\0{source}".encode()).hexdigest()
    cached = _cache.get(key)
    if cached is not None:
        return cached

    if not available():
        raise MermaidUnavailable()

    try:
        with tempfile.TemporaryDirectory(prefix="zeile-mermaid-") as tmp_name:
            tmp = Path(tmp_name)
            in_path = tmp / "diagram.mmd"
            out_path = tmp / "diagram.svg"
            config_path = tmp / "config.json"
            in_path.write_text(source, encoding="utf-8")
            config_path.write_text(_MERMAID_CONFIG, encoding="utf-8")
            try:
                result = subprocess.run(
                    [
                        "mmdc",
                        "-i",
                        str(in_path),
                        "-o",
                        str(out_path),
                        "-c",
                        str(config_path),
                        "-b",
                        "transparent",
                        "-t",
                        "dark" if dark else "default",
                    ],
                    check=False,
                    capture_output=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise MermaidRenderError("timeout", _decode(exc.stderr)) from None
            except FileNotFoundError:
                raise MermaidUnavailable() from None

            if result.returncode != 0:
                detail = (
                    _decode(result.stderr)
                    or _decode(result.stdout)
                    or f"exit {result.returncode}"
                )
                raise MermaidRenderError("failed", detail)

            if not out_path.is_file():
                raise MermaidRenderError("empty")
            if (
                out_path.stat().st_size > MAX_SVG_CHARS
            ):  # bytes >= chars: judge before reading
                raise MermaidRenderError("oversized")
            svg = out_path.read_text(encoding="utf-8", errors="replace")
            if not svg.strip():
                raise MermaidRenderError("empty")
            if len(svg) > MAX_SVG_CHARS:
                raise MermaidRenderError("oversized")
            svg = _strip_script_vectors(svg)
    except MermaidRenderError:
        raise
    except OSError as exc:
        raise MermaidRenderError("oserror", str(exc)) from None

    _cache[key] = svg
    return svg
