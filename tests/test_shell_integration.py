# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Man pages and shell completions: stage, syntax, sync, install/uninstall."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from zeile import BODY_FONT_OPTIONS, CODE_FONT_OPTIONS, THEME_OPTIONS  # noqa: E402

COMPLETION_FILES = (
    REPO / "completions" / "zeile.bash",
    REPO / "completions" / "zeile.zsh",
    REPO / "completions" / "zeile.fish",
)

STAGED_RELATIVE = (
    "usr/share/man/man1/zeile.1",
    "usr/share/man/de/man1/zeile.1",
    "usr/share/bash-completion/completions/zeile",
    "usr/share/zsh/site-functions/_zeile",
    "usr/share/fish/vendor_completions.d/zeile.fish",
)

MAN_PAGES = (
    REPO / "man" / "zeile.1",
    REPO / "man" / "de" / "zeile.1",
)


def _long_options_from_help() -> list[str]:
    result = subprocess.run(
        [sys.executable, str(REPO / "zeile.py"), "--help"],
        check=True,
        capture_output=True,
        text=True,
    )
    return sorted(set(re.findall(r"--[a-z0-9-]+", result.stdout)))


def test_stage_sh_installs_man_and_completions(tmp_path: Path) -> None:
    dest = tmp_path / "stage"
    subprocess.run(
        ["bash", str(REPO / "packaging" / "stage.sh"), str(dest), "/usr"],
        check=True,
        cwd=REPO,
    )
    for relative in STAGED_RELATIVE:
        path = dest / relative
        assert path.is_file(), f"missing staged file: {relative}"
        assert path.stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not installed")
def test_bash_completion_syntax() -> None:
    subprocess.run(
        ["bash", "-n", str(REPO / "completions" / "zeile.bash")],
        check=True,
    )


@pytest.mark.skipif(shutil.which("fish") is None, reason="fish not installed")
def test_fish_completion_syntax() -> None:
    subprocess.run(
        ["fish", "--no-execute", str(REPO / "completions" / "zeile.fish")],
        check=True,
    )


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh not installed")
def test_zsh_completion_syntax() -> None:
    subprocess.run(
        ["zsh", "-n", str(REPO / "completions" / "zeile.zsh")],
        check=True,
    )


def test_completions_list_help_options_and_theme_font_ids() -> None:
    ids = list(THEME_OPTIONS) + list(BODY_FONT_OPTIONS) + list(CODE_FONT_OPTIONS)
    long_opts = _long_options_from_help()
    assert long_opts, "expected long options from --help"
    for path in COMPLETION_FILES:
        text = path.read_text(encoding="utf-8")
        for opt in long_opts:
            assert opt in text, f"{path.name}: missing {opt}"
        for option_id in ids:
            assert option_id in text, f"{path.name}: missing id {option_id}"


def test_theme_and_font_ids_match_zeile_tuples() -> None:
    """Completion id lists stay in lockstep with zeile.py tuples."""
    assert THEME_OPTIONS  # the count may grow; the loop below checks every id
    for path in COMPLETION_FILES:
        text = path.read_text(encoding="utf-8")
        for theme in THEME_OPTIONS:
            assert theme in text
        for body in BODY_FONT_OPTIONS:
            assert body in text
        for code in CODE_FONT_OPTIONS:
            assert code in text


def test_install_sh_man_completions_roundtrip(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    env = {**os.environ, "HOME": str(home)}

    man_en = home / ".local" / "share" / "man" / "man1" / "zeile.1"
    man_de = home / ".local" / "share" / "man" / "de" / "man1" / "zeile.1"
    bash_comp = home / ".local" / "share" / "bash-completion" / "completions" / "zeile"
    fish_comp = home / ".config" / "fish" / "completions" / "zeile.fish"
    installed = (man_en, man_de, bash_comp, fish_comp)

    # Unrelated neighbours that --uninstall must leave alone.
    keep_man = home / ".local" / "share" / "man" / "man1" / "other.1"
    keep_bash = home / ".local" / "share" / "bash-completion" / "completions" / "other"
    keep_fish = home / ".config" / "fish" / "completions" / "other.fish"
    for keep in (keep_man, keep_bash, keep_fish):
        keep.parent.mkdir(parents=True, exist_ok=True)
        keep.write_text("keep\n", encoding="utf-8")

    subprocess.run(
        ["bash", str(REPO / "install.sh")],
        check=True,
        cwd=REPO,
        env=env,
    )
    for path in installed:
        assert path.is_file(), f"install.sh did not create {path}"

    subprocess.run(
        ["bash", str(REPO / "install.sh"), "--uninstall"],
        check=True,
        cwd=REPO,
        env=env,
    )
    for path in installed:
        assert not path.exists(), f"uninstall left behind {path}"
    for keep in (keep_man, keep_bash, keep_fish):
        assert keep.is_file() and keep.read_text(encoding="utf-8") == "keep\n"


@pytest.mark.skipif(
    shutil.which("groff") is None and shutil.which("mandoc") is None,
    reason="neither groff nor mandoc installed",
)
@pytest.mark.parametrize("man_path", MAN_PAGES, ids=("en", "de"))
def test_man_pages_lint_clean(man_path: Path) -> None:
    if shutil.which("groff"):
        result = subprocess.run(
            ["groff", "-ww", "-z", "-man", str(man_path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert result.stderr.strip() == "", result.stderr
        return

    result = subprocess.run(
        ["mandoc", "-T", "lint", str(man_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stderr.strip() == "", result.stderr


def test_install_never_clobbers_or_removes_a_foreign_file(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {**os.environ, "HOME": str(home)}
    man_en = home / ".local" / "share" / "man" / "man1" / "zeile.1"
    man_en.parent.mkdir(parents=True)
    man_en.write_text("the user's own page\n", encoding="utf-8")

    subprocess.run(["bash", str(REPO / "install.sh")], check=True, cwd=REPO, env=env)
    assert man_en.read_text(encoding="utf-8") == "the user's own page\n"

    subprocess.run(
        ["bash", str(REPO / "install.sh"), "--uninstall"], check=True, cwd=REPO, env=env
    )
    assert man_en.read_text(encoding="utf-8") == "the user's own page\n"


def test_install_upgrades_its_own_files(tmp_path: Path) -> None:
    home = tmp_path / "home"
    env = {**os.environ, "HOME": str(home)}
    bash_comp = home / ".local" / "share" / "bash-completion" / "completions" / "zeile"
    subprocess.run(["bash", str(REPO / "install.sh")], check=True, cwd=REPO, env=env)
    bash_comp.write_text("# zeile-installer-owned\n# an older version\n", encoding="utf-8")

    subprocess.run(["bash", str(REPO / "install.sh")], check=True, cwd=REPO, env=env)
    assert bash_comp.read_text(encoding="utf-8") == (
        REPO / "completions" / "zeile.bash"
    ).read_text(encoding="utf-8")


def test_bash_completion_is_literal_and_covers_dirs_and_both_extensions(
    tmp_path: Path,
) -> None:
    (tmp_path / "a b.md").write_text("x", encoding="utf-8")
    (tmp_path / "a[1].markdown").write_text("x", encoding="utf-8")
    (tmp_path / "a*.MD").write_text("x", encoding="utf-8")
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "adir").mkdir()
    script = (
        f'source "{REPO / "completions" / "zeile.bash"}"\n'
        'COMP_WORDS=(zeile "a"); COMP_CWORD=1; _zeile\n'
        'printf "%s\\n" "${COMPREPLY[@]}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert sorted(result.stdout.splitlines()) == [
        "a b.md",
        "a*.MD",
        "a[1].markdown",
        "adir",
    ]
