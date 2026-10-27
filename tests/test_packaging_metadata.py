# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Package metadata must ship English and German user-visible strings."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
METAINFO = REPO / "packaging" / "flatpak" / "com.erdlabs.zeile.metainfo.xml"
DESKTOP_SOURCES = (
    REPO / "install.sh",
    REPO / "packaging" / "stage.sh",
    REPO / "packaging" / "flatpak" / "com.erdlabs.zeile.desktop",
)
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"
LOCALIZABLE_DESKTOP_KEYS = ("GenericName", "Comment", "Keywords")


def _lang(elem: ET.Element) -> str | None:
    return elem.get(XML_LANG) or elem.get("lang")


def _siblings_by_tag(parent: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in parent if child.tag == tag]


def _assert_de_twin(parent: ET.Element, tag: str, context: str) -> None:
    elems = _siblings_by_tag(parent, tag)
    defaults = [e for e in elems if _lang(e) is None]
    german = [e for e in elems if _lang(e) == "de"]
    assert defaults, f"{context}: missing default (English) <{tag}>"
    assert german, f"{context}: missing <{tag} xml:lang='de'>"
    assert len(german) >= len(defaults), (
        f"{context}: expected a German twin for every default <{tag}> "
        f"(got {len(defaults)} default, {len(german)} de)"
    )


def _assert_description_de_twins(description: ET.Element, context: str) -> None:
    """AppStream forbids xml:lang on <description>; localize <p>/<li> instead."""
    assert _lang(description) is None, (
        f"{context}: <description> must not carry xml:lang (AppStream)"
    )
    blocks = [e for e in description.iter() if e.tag in {"p", "li"}]
    defaults = [e for e in blocks if _lang(e) is None]
    german = [e for e in blocks if _lang(e) == "de"]
    assert defaults, f"{context}: missing English description blocks"
    assert german, f"{context}: missing xml:lang='de' description blocks"
    assert len(german) >= len(defaults), (
        f"{context}: expected a German twin for every English <p>/<li> "
        f"(got {len(defaults)} default, {len(german)} de)"
    )


def test_metainfo_has_german_twins() -> None:
    root = ET.parse(METAINFO).getroot()
    _assert_de_twin(root, "summary", "metainfo root")

    descriptions = _siblings_by_tag(root, "description")
    assert len(descriptions) == 1, "metainfo: expected one unlocalized <description>"
    _assert_description_de_twins(descriptions[0], "metainfo description")

    screenshots = root.find("screenshots")
    assert screenshots is not None, "metainfo: missing <screenshots>"
    for index, shot in enumerate(screenshots.findall("screenshot"), start=1):
        _assert_de_twin(shot, "caption", f"screenshot[{index}]")

    releases = root.find("releases")
    assert releases is not None, "metainfo: missing <releases>"
    for release in releases.findall("release"):
        version = release.get("version", "?")
        rel_descs = _siblings_by_tag(release, "description")
        assert len(rel_descs) == 1, f"release {version}: expected one <description>"
        _assert_description_de_twins(rel_descs[0], f"release {version} description")


def test_desktop_sources_have_german_twins() -> None:
    key_line = re.compile(
        r"^(GenericName|Comment|Keywords)(?:\[([^\]]+)\])?=(.*)$",
        re.MULTILINE,
    )
    for path in DESKTOP_SOURCES:
        text = path.read_text(encoding="utf-8")
        by_key: dict[str, set[str | None]] = {k: set() for k in LOCALIZABLE_DESKTOP_KEYS}
        for match in key_line.finditer(text):
            key, lang, _value = match.group(1), match.group(2), match.group(3)
            by_key[key].add(lang)

        for key in LOCALIZABLE_DESKTOP_KEYS:
            langs = by_key[key]
            if not langs:
                # Keywords is only present in the Flatpak desktop entry.
                continue
            assert None in langs, f"{path}: missing unlocalized {key}="
            assert "de" in langs, f"{path}: missing {key}[de]="
