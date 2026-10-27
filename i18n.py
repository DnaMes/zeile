# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The one gettext lookup shared by the core modules and the shells.

fallback=True: on a system with no compiled translation for the current
locale (or none at all), _() returns the original English string instead of
raising -- translation is additive, never a hard requirement to run.
ngettext is exposed as _n for plural forms such as the search-bar match count.
"""

from __future__ import annotations

import gettext
from pathlib import Path

_translation = gettext.translation(
    "zeile", localedir=Path(__file__).resolve().parent / "locale", fallback=True
)
_ = _translation.gettext
_n = _translation.ngettext
