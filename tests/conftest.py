# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Make the repo root importable so tests can `import zeile`/`markdown_ext`.

These aren't a packaged module (they're scripts shipped next to each other,
same as install.sh's launcher assumes), so pytest needs a nudge to find them.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
