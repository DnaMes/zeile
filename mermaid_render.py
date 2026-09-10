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

import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

# Disables mermaid's foreignObject/htmlLabels rendering path for the diagram
# types that expose the option, so mmdc emits plain SVG <text>/<tspan> labels
# instead of <foreignObject><div xmlns="...">...</div></foreignObject>.
# Confirmed key shape via mermaid-cli issue #691 and independent reports
# (GNOME Inkscape #3268, Prince forum) -- not independently verified against
# a real mmdc run here, since mmdc is not installed on this machine (opt-in,
# default off). The sanitizer in zeile.py does not special-case SVG content
# at all (see its module docstring), so this setting is the only thing
# standing between a diagram and a foreignObject in the shipped output --
# treat it as load-bearing, not cosmetic.
_MERMAID_CONFIG = json.dumps(
    {
        "flowchart": {"htmlLabels": False},
        "class": {"htmlLabels": False},
        "state": {"htmlLabels": False},
    }
)

_cache: dict[str, str] = {}


class MermaidUnavailable(RuntimeError):
    """Raised when a diagram needs rendering but mmdc is not on PATH."""


def available() -> bool:
    return shutil.which("mmdc") is not None


def render_svg(source: str, *, dark: bool) -> str:
    """Render Mermaid diagram source to an SVG string.

    Cached by (source, theme) so an unchanged diagram isn't re-shelled-out to
    on every debounced reload. Raises MermaidUnavailable if mmdc is not
    installed, or subprocess.CalledProcessError if mmdc rejects the source.
    """
    key = hashlib.sha256(f"{dark}\0{source}".encode()).hexdigest()
    cached = _cache.get(key)
    if cached is not None:
        return cached

    if not available():
        raise MermaidUnavailable("mmdc (mermaid-cli) not found on PATH")

    with tempfile.TemporaryDirectory(prefix="zeile-mermaid-") as tmp_name:
        tmp = Path(tmp_name)
        in_path = tmp / "diagram.mmd"
        out_path = tmp / "diagram.svg"
        config_path = tmp / "config.json"
        in_path.write_text(source, encoding="utf-8")
        config_path.write_text(_MERMAID_CONFIG, encoding="utf-8")
        subprocess.run(
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
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        svg = out_path.read_text(encoding="utf-8")

    _cache[key] = svg
    return svg
