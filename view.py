# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""The boundary between zeile and the toolkit's web view.

A shell (zeile.py today; a pywebview shell for Windows and macOS later) owns the
window and the menus and talks to the page only through `DocumentView`. A backend
(`webkitgtk_view.py`: WebKitGTK on Linux) implements it. What a link click may do
is decided here, once, by `decide()`, so every backend enforces the same policy.

This module must stay importable without a GUI toolkit (tests/test_core_isolation.py).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from documents import classify_local_target

COPY_SCHEME = "zeile-copy"
_COPY_URI_RE = re.compile(rf"{COPY_SCHEME}://(\d+)")


class Action(Enum):
    LOAD = "load"  # let the view load it (the document itself, a local image)
    NAVIGATE = "navigate"  # another .md file: re-render it in the same window
    COPY = "copy"  # a code-block copy button
    EXTERNAL = "external"  # hand it to the system opener; the view loads nothing


@dataclass(frozen=True)
class Decision:
    action: Action
    target: Path | None = None  # NAVIGATE: the file to open
    copy_index: int | None = None  # COPY: the code block


def decide(uri: str, document: Path) -> Decision:
    """Decide what a navigation request to `uri` does while `document` is open.

    Only file:// URIs under the document's directory ever load in the view; a
    local markdown link re-enters our renderer (loading it directly would show the
    raw source with no way back); everything else is external.
    """
    parsed = urlparse(uri)
    scheme = parsed.scheme.lower()
    if scheme == COPY_SCHEME:
        match = _COPY_URI_RE.fullmatch(uri)
        return Decision(Action.COPY, copy_index=int(match.group(1)) if match else None)
    if scheme == "file" and parsed.netloc in ("", "localhost"):
        target = Path(url2pathname(unquote(parsed.path))).resolve()
        action = classify_local_target(target, document)
        if action == "navigate":
            return Decision(Action.NAVIGATE, target=target)
        if action == "load":
            return Decision(Action.LOAD)
    return Decision(Action.EXTERNAL)


class DocumentView(Protocol):
    """The calls a shell may make on the web view (document JavaScript is always off)."""

    widget: object  # the toolkit widget the shell embeds
    zoom: float

    # Set by the shell. `on_navigation` returns the decision the backend enforces.
    on_navigation: Callable[[str], Decision]
    on_load_finished: Callable[[], None]
    on_hover_link: Callable[[str | None], None]
    on_find_result: Callable[[int], None]  # match count, 0 = none

    def load_html(self, html: str, base_uri: str) -> None: ...

    def run_js(self, js: str) -> None:
        """Run app-authored script (never document-sourced) in the page."""

    def get_scroll_y(self, callback: Callable[[int], None]) -> None:
        """Deliver the vertical scroll offset in pixels (0 if it cannot be read)."""

    def find(self, text: str) -> None: ...

    def find_next(self) -> None: ...

    def find_previous(self) -> None: ...

    def find_finish(self) -> None: ...

    def print_dialog(self, parent: object) -> None: ...

    def export_pdf(self, uri: str) -> None: ...

    def grab_focus(self) -> None: ...
