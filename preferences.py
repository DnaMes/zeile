# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Settings and option tables: what zeile remembers between runs.

Platform-neutral on purpose -- the settings file is the one piece of state a
Windows or macOS shell needs exactly as the Linux shell does. Every value is
coerced on read, because the file is a plain JSON document a user may have
edited by hand, and a bad value must never stop the viewer from opening.
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

from i18n import _

THEME_OPTIONS = (
    "auto",
    "github-light",
    "github-dark",
    "catppuccin-latte",
    "catppuccin-frappe",
    "catppuccin-macchiato",
    "catppuccin-mocha",
    "solarized-light",
    "solarized-dark",
    "gruvbox-light",
    "gruvbox-dark",
    "nord",
    "dracula",
    "rose-pine",
    "rose-pine-dawn",
    "tokyo-night",
    "tokyo-night-day",
    "cyberpunk",
    "vscode-dark",
    "one-dark",
    "monokai",
)

THEME_DARKNESS: dict[str, bool | None] = {
    "auto": None,
    "github-light": False,
    "github-dark": True,
    "catppuccin-latte": False,
    "catppuccin-frappe": True,
    "catppuccin-macchiato": True,
    "catppuccin-mocha": True,
    "solarized-light": False,
    "solarized-dark": True,
    "gruvbox-light": False,
    "gruvbox-dark": True,
    "nord": True,
    "dracula": True,
    "rose-pine": True,
    "rose-pine-dawn": False,
    "tokyo-night": True,
    "tokyo-night-day": False,
    "cyberpunk": True,
    "vscode-dark": True,
    "one-dark": True,
    "monokai": True,
}


BODY_FONT_OPTIONS = (
    "system",
    "inter",
    "atkinson",
    "ia-writer",
    "noto-serif",
    "ibmplex-sans",
)

CODE_FONT_OPTIONS = (
    "system",
    "jetbrains-mono",
    "ia-writer",
    "fira-code",
    "cascadia-code",
)

READING_WIDTH_OPTIONS = (
    "narrow",
    "standard",
    "wide",
)

_DEFAULT_SETTINGS = {
    "theme": "auto",
    "body_font": "system",
    "code_font": "system",
    "reading_width": "standard",
    "zoom": "1.0",
    "window_w": "900",
    "window_h": "1000",
    "window_maximized": "false",
    "intro_seen": "false",  # the erdlabs intro plays once per install (#5)
}
_ZOOM_MIN, _ZOOM_MAX = 0.4, 3.0
_WINDOW_MIN, _WINDOW_MAX = 200, 10000


def _default_settings_path() -> Path:
    return (
        Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
        / "zeile"
        / "settings.json"
    )


def _coerce_theme(theme: str) -> str:
    return theme if theme in THEME_OPTIONS else _DEFAULT_SETTINGS["theme"]


def _coerce_font(font: str, kind: str) -> str:
    allowed = BODY_FONT_OPTIONS if kind == "body" else CODE_FONT_OPTIONS
    return (
        font
        if font in allowed
        else _DEFAULT_SETTINGS["body_font" if kind == "body" else "code_font"]
    )


def _coerce_reading_width(width: object) -> str:
    return (
        width
        if isinstance(width, str) and width in READING_WIDTH_OPTIONS
        else _DEFAULT_SETTINGS["reading_width"]
    )


def _as_finite_float(value: object) -> float | None:
    """Return `value` as a finite float, or None if it is not one.

    JSON can smuggle in values float() accepts but no UI can use: 1e309
    (inf), "nan", and integers beyond float range (OverflowError). Bools
    are rejected explicitly because JSON `true` would otherwise read as 1.
    """
    if isinstance(value, bool):
        return None
    try:
        n = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    return n if math.isfinite(n) else None


def _coerce_number(
    value: object,
    lo: float,
    hi: float,
    *,
    integer: bool = False,
    default: str | None = None,
) -> str:
    """Clamp-to-range number coercion for free-form settings values.

    Unparseable or non-finite input falls back to `default` (the documented
    default), not to the range minimum -- "garbage" should restore the
    shipped default, not produce a 200px window.
    """
    n = _as_finite_float(value)
    if n is None:
        if default is not None:
            return default
        n = 0.0
    n = min(hi, max(lo, n))
    return str(int(n)) if integer else str(n)


def is_theme_dark(theme_id: str, *, fallback: bool) -> bool:
    value = THEME_DARKNESS.get(theme_id)
    if value is None:
        return fallback
    return value


def load_settings(*, path: Path | None = None) -> dict[str, str]:
    """Load viewer settings from JSON with robust fallback."""
    settings_path = path or _default_settings_path()
    settings = dict(_DEFAULT_SETTINGS)
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    # UnicodeDecodeError is a ValueError; RecursionError covers pathological
    # nesting. Any of them means "unreadable settings", i.e. the defaults.
    except (OSError, ValueError, RecursionError):
        return settings

    if not isinstance(data, dict):
        return settings

    theme = data.get("theme")
    if isinstance(theme, str):
        settings["theme"] = _coerce_theme(theme)

    body_font = data.get("body_font")
    if isinstance(body_font, str):
        settings["body_font"] = _coerce_font(body_font, kind="body")

    code_font = data.get("code_font")
    if isinstance(code_font, str):
        settings["code_font"] = _coerce_font(code_font, kind="code")

    reading_width = data.get("reading_width")
    if isinstance(reading_width, str):
        settings["reading_width"] = _coerce_reading_width(reading_width)

    # Free-form numeric/bool keys: non-finite or unparseable values keep the
    # default, finite out-of-range values are clamped; nothing raises.
    zoom = _as_finite_float(data.get("zoom"))
    if zoom is not None:
        settings["zoom"] = _coerce_number(zoom, _ZOOM_MIN, _ZOOM_MAX)
    for key in ("window_w", "window_h"):
        width = _as_finite_float(data.get(key))
        if width is not None:
            settings[key] = _coerce_number(width, _WINDOW_MIN, _WINDOW_MAX, integer=True)
    maximized = data.get("window_maximized")
    if isinstance(maximized, bool):
        settings["window_maximized"] = "true" if maximized else "false"
    elif maximized in ("true", "false"):
        settings["window_maximized"] = maximized

    intro_seen = data.get("intro_seen")
    if isinstance(intro_seen, bool):
        settings["intro_seen"] = "true" if intro_seen else "false"
    elif intro_seen in ("true", "false"):
        settings["intro_seen"] = intro_seen

    return settings


def save_settings(settings: dict[str, str], *, path: Path | None = None) -> None:
    """Persist settings if possible; silently ignore environment write failures."""
    settings_path = path or _default_settings_path()
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "theme": _coerce_theme(settings.get("theme", _DEFAULT_SETTINGS["theme"])),
            "body_font": _coerce_font(
                settings.get("body_font", _DEFAULT_SETTINGS["body_font"]), kind="body"
            ),
            "code_font": _coerce_font(
                settings.get("code_font", _DEFAULT_SETTINGS["code_font"]), kind="code"
            ),
            "reading_width": _coerce_reading_width(
                settings.get("reading_width", _DEFAULT_SETTINGS["reading_width"])
            ),
            "zoom": _coerce_number(
                settings.get("zoom", _DEFAULT_SETTINGS["zoom"]),
                _ZOOM_MIN,
                _ZOOM_MAX,
                default=_DEFAULT_SETTINGS["zoom"],
            ),
            "window_w": _coerce_number(
                settings.get("window_w", _DEFAULT_SETTINGS["window_w"]),
                _WINDOW_MIN,
                _WINDOW_MAX,
                integer=True,
                default=_DEFAULT_SETTINGS["window_w"],
            ),
            "window_h": _coerce_number(
                settings.get("window_h", _DEFAULT_SETTINGS["window_h"]),
                _WINDOW_MIN,
                _WINDOW_MAX,
                integer=True,
                default=_DEFAULT_SETTINGS["window_h"],
            ),
            "window_maximized": (
                "true"
                if settings.get("window_maximized", _DEFAULT_SETTINGS["window_maximized"])
                in (True, "true")
                else "false"
            ),
            "intro_seen": (
                "true"
                if settings.get("intro_seen", _DEFAULT_SETTINGS["intro_seen"])
                in (True, "true")
                else "false"
            ),
        }
        settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        return


def _theme_label(theme_id: str) -> str:
    mapping = {
        "auto": _("Auto (system)"),
        "github-light": _("GitHub Light"),
        "github-dark": _("GitHub Dark"),
        "catppuccin-latte": _("Catppuccin Latte"),
        "catppuccin-frappe": _("Catppuccin Frappé"),
        "catppuccin-macchiato": _("Catppuccin Macchiato"),
        "catppuccin-mocha": _("Catppuccin Mocha"),
        "solarized-light": _("Solarized Light"),
        "solarized-dark": _("Solarized Dark"),
        "gruvbox-light": _("Gruvbox Light"),
        "gruvbox-dark": _("Gruvbox Dark"),
        "nord": _("Nord"),
        "dracula": _("Dracula"),
        "rose-pine": _("Rosé Pine"),
        "rose-pine-dawn": _("Rosé Pine Dawn"),
        "tokyo-night": _("Tokyo Night"),
        "tokyo-night-day": _("Tokyo Night Day"),
        "cyberpunk": _("Cyberpunk"),
        "vscode-dark": _("VS Code Dark"),
        "one-dark": _("One Dark"),
        "monokai": _("Monokai"),
    }
    return mapping.get(theme_id, theme_id)


def _font_label(font_id: str, *, is_code: bool) -> str:
    if is_code:
        mapping = {
            "system": _("System monospace"),
            "jetbrains-mono": _("JetBrains Mono"),
            "ia-writer": _("iA Writer Mono"),
            "fira-code": _("Fira Code"),
            "cascadia-code": _("Cascadia Code"),
        }
        return mapping.get(font_id, font_id)

    mapping = {
        "system": _("System"),
        "inter": _("Inter"),
        "atkinson": _("Atkinson Hyperlegible"),
        "ia-writer": _("iA Writer Quattro"),
        "noto-serif": _("Noto Serif"),
        "ibmplex-sans": _("IBM Plex Sans"),
    }
    return mapping.get(font_id, font_id)
