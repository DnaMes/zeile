# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Tests for mermaid_render._strip_script_vectors and mmdc failure paths.

The SVG mmdc produces reaches the page un-sanitized (injected after nh3's
pass via markdown_ext's nonce mechanism), so mermaid_render strips script
vectors itself. These tests pin that behaviour without needing mmdc.

Failure-path tests install a fake `mmdc` on PATH via monkeypatch so they
never need the real mermaid-cli binary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

import mermaid_render
from mermaid_render import (
    MermaidRenderError,
    MermaidUnavailable,
    _strip_script_vectors,
    error_html,
    render_svg,
)


@pytest.fixture(autouse=True)
def _english_locale(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin mermaid_render's strings to English regardless of the test host's
    locale: the assertions below check English substrings of error_html().
    Error messages are translated lazily at error_html() call time, so
    monkeypatching the module-level `_` is enough."""
    monkeypatch.setattr(mermaid_render, "_", lambda s: s)


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


# The fake below is a POSIX shell script. Windows can only start a .cmd/.bat
# shim through cmd.exe, so with a list argv CreateProcess reports it as
# missing -- which is what these tests then see instead of the simulated
# failure. The code paths they pin (returncode, stderr decoding, output size)
# are plain Python and identical on every OS; the Windows-only case that does
# matter, mmdc being absent, is pinned by test_missing_mmdc above.
posix_shell_only = pytest.mark.skipif(
    sys.platform == "win32", reason="the fake mmdc is a POSIX shell script"
)


def _install_fake_mmdc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> None:
    mermaid_render._cache.clear()
    mmdc = tmp_path / "mmdc"
    mmdc.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    mmdc.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}{os.pathsep}{os.environ.get('PATH', '')}")


@posix_shell_only
def test_timeout_raises_render_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_mmdc(tmp_path, monkeypatch, "sleep 5\n")
    with pytest.raises(MermaidRenderError) as ei:
        render_svg("graph TD; A-->B;", dark=False, timeout=0.1)
    assert ei.value.kind == "timeout"
    out = error_html(ei.value.kind, detail=ei.value.detail, source="graph TD; A-->B;")
    assert "timed out" in out
    assert "mermaid-error" in out


@posix_shell_only
def test_nonzero_exit_escapes_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_mmdc(
        tmp_path,
        monkeypatch,
        'echo "<script>alert(1)</script>" >&2\nexit 1\n',
    )
    with pytest.raises(MermaidRenderError) as ei:
        render_svg("graph TD; A-->B;", dark=False)
    assert ei.value.kind == "failed"
    assert "<script>alert(1)</script>" in ei.value.detail
    out = error_html(ei.value.kind, detail=ei.value.detail, source="graph TD; A-->B;")
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in out


def test_missing_mmdc(monkeypatch: pytest.MonkeyPatch) -> None:
    mermaid_render._cache.clear()
    monkeypatch.setenv("PATH", "/nonexistent")
    with pytest.raises(MermaidUnavailable) as ei:
        render_svg("graph TD; A-->B;", dark=False)
    assert ei.value.kind == "missing"
    out = error_html(ei.value.kind)
    assert "mmdc" in out
    assert "not found on PATH" in out


@posix_shell_only
def test_empty_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Parse -o and write an empty SVG so exit 0 still triggers the empty path.
    _install_fake_mmdc(
        tmp_path,
        monkeypatch,
        """
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; shift 2; continue; fi
  shift
done
: > "$out"
exit 0
""",
    )
    with pytest.raises(MermaidRenderError) as ei:
        render_svg("graph TD; A-->B;", dark=False)
    assert ei.value.kind == "empty"
    out = error_html(ei.value.kind, source="graph TD; A-->B;")
    assert "empty output" in out


@posix_shell_only
def test_invalid_utf8_stderr_is_replaced_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_mmdc(tmp_path, monkeypatch, "printf '\\377\\376bad' >&2\nexit 1\n")
    with pytest.raises(MermaidRenderError) as ei:
        render_svg("graph TD; A-->B;", dark=False)
    assert ei.value.kind == "failed"
    assert "bad" in ei.value.detail
    assert "\ufffd" in ei.value.detail


@posix_shell_only
def test_invalid_utf8_svg_does_not_break_the_render(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fake_mmdc(
        tmp_path,
        monkeypatch,
        """
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; shift 2; continue; fi
  shift
done
printf '<svg><text>ok \\377</text></svg>' > "$out"
exit 0
""",
    )
    svg = render_svg("graph TD; A-->B;", dark=False)
    assert svg.startswith("<svg>") and "ok" in svg


@posix_shell_only
def test_oversized_svg_is_rejected_before_it_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mermaid_render, "MAX_SVG_CHARS", 100)
    _install_fake_mmdc(
        tmp_path,
        monkeypatch,
        """
out=""
while [ "$#" -gt 0 ]; do
  if [ "$1" = "-o" ]; then out="$2"; shift 2; continue; fi
  shift
done
head -c 5000 /dev/zero | tr '\\0' 'a' > "$out"
exit 0
""",
    )
    with pytest.raises(MermaidRenderError) as ei:
        render_svg("graph TD; A-->B;", dark=False)
    assert ei.value.kind == "oversized"
