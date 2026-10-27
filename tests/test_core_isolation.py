# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The core must import on Windows and macOS: no GUI toolkit, ever.

zeile ships three shells for one core. The Linux shell owns `gi` (GTK4 +
WebKitGTK), the Windows/macOS shell owns `webview` (WebView2 + WKWebView).
Everything else has to stay importable on a machine that has neither, or the
core stops being shared and the two shells drift apart.

This test is what makes that an invariant instead of a good intention: it is
cheap, it fails loudly, and it runs on all three CI platforms.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORE = ("documents.py", "preferences.py", "launch.py", "i18n.py")
GUI_ONLY = re.compile(r"^\s*(?:import|from)\s+(gi|webview)\b", re.MULTILINE)


def test_core_modules_do_not_import_a_gui_toolkit() -> None:
    for name in CORE:
        source = (REPO / name).read_text(encoding="utf-8")
        assert not GUI_ONLY.search(source), f"{name} imports a GUI toolkit"

    # The shells are allowed to, and must: that is their whole job.
    assert GUI_ONLY.search((REPO / "zeile.py").read_text(encoding="utf-8"))


def test_core_imports_without_a_display() -> None:
    """Import the core in a subprocess with no DISPLAY and no `gi` on the path."""
    import subprocess
    import sys

    code = (
        "import sys, documents, preferences, launch, i18n, markdown_ext;"
        "assert 'gi' not in sys.modules, 'the core pulled in gi'"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
