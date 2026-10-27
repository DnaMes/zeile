# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Unit checks for packaging/smoke_render.py (no display, no GUI).

The real render check runs inside packaging/smoke.sh under cage; here we
only verify the script's shape (executable, SPDX header, compiles) and that
smoke.sh actually wires it into the smoke run.
"""

import py_compile
import stat
from pathlib import Path

PACKAGING = Path(__file__).resolve().parent.parent / "packaging"


def test_smoke_render_is_executable() -> None:
    script = PACKAGING / "smoke_render.py"
    mode = script.stat().st_mode
    assert mode & stat.S_IXUSR, "smoke_render.py must be executable"


def test_smoke_render_has_spdx_header() -> None:
    text = (PACKAGING / "smoke_render.py").read_text(encoding="utf-8")
    assert "SPDX-License-Identifier: GPL-3.0-or-later" in text


def test_smoke_render_compiles() -> None:
    py_compile.compile(str(PACKAGING / "smoke_render.py"), doraise=True)


def test_smoke_sh_runs_the_render_check() -> None:
    text = (PACKAGING / "smoke.sh").read_text(encoding="utf-8")
    assert "smoke_render.py" in text
    assert "render OK" in text
