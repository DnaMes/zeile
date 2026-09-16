# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Tests for code_lang.guess_code_language.

The battery below is deliberately made of *realistic markdown-document
snippets* (config files, short functions, console transcripts), not full
source files -- that's the shape unlabeled fences actually have, and the
reason Pygments' own guess_lexer was rejected (see code_lang.py's module
docstring for the measured misfires).
"""

from pathlib import Path

import pytest
from pygments.lexers import get_lexer_by_name
from pygments.util import ClassNotFound

from code_lang import MAX_CODE_CHARS, guess_code_language

# (expected, code) -- expectations double as documentation of intent;
# when a case here flips, that's a regression to investigate, not to
# rubber-stamp.
BATTERY = [
    ("python", "def foo(x):\n    return x + 1\n\nclass Bar:\n    pass\n"),
    ("python", 'import os\nimport sys\n\nfor arg in sys.argv:\n    print(f"got {arg}")\n'),
    ("python", '#!/usr/bin/env python3\nprint("hi")\n'),
    (
        "javascript",
        'import x from "y";\nexport function foo(a, b) {\n  return a + b;\n}\nconst z = [1, 2].map(n => n * 2);\nconsole.log(z);\n',
    ),
    (
        "typescript",
        "interface Foo { name: string }\nexport const bar = (x: number): string => {\n  return x.toFixed(2);\n};\n",
    ),
    ("bash", 'set -euo pipefail\nfor f in *.md; do\n  echo "processing $f"\ndone\n'),
    (
        "bash",
        "sudo pacman -Syu --needed git\nnpm install -g something && npm cache clean\n",
    ),
    ("bash", "#!/bin/bash\nset -e\nexit 0\n"),
    ("json", '{\n  "name": "zeile",\n  "version": "1.0.0",\n  "deps": ["a", "b"]\n}\n'),
    (
        "yaml",
        "name: test\non:\n  push:\n    branches: [main]\njobs:\n  build:\n    runs-on: ubuntu-latest\n",
    ),
    ("yaml", "---\ntitle: My Post\ndate: 2026-01-01\ntags:\n  - a\n  - b\n---\n"),
    ("toml", '[package]\nname = "x"\nversion = "0.1.0"\n\n[dependencies]\nserde = "1.0"\n'),
    ("ini", "[core]\nrepositoryformatversion = 0\nfilemode = true\nbare = false\n"),
    ("sql", "SELECT u.id, u.name FROM users u WHERE u.active = 1 ORDER BY u.name;\n"),
    ("sql", "CREATE TABLE users (\n  id INTEGER PRIMARY KEY,\n  name TEXT NOT NULL\n);\n"),
    (
        "c",
        '#include <stdio.h>\nint main(int argc, char **argv) {\n    printf("hi\\n");\n    return 0;\n}\n',
    ),
    (
        "cpp",
        '#include <iostream>\nint main() {\n    std::string s = "hi";\n    std::cout << s << std::endl;\n    return 0;\n}\n',
    ),
    ("go", 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("hi")\n}\n'),
    (
        "rust",
        'use std::io;\n\nfn main() {\n    let mut s = String::new();\n    io::stdin().read_line(&mut s).unwrap();\n    println!("{}", s);\n}\n',
    ),
    (
        "java",
        'import java.util.List;\n\npublic class Main {\n    public static void main(String[] args) {\n        System.out.println("hi");\n    }\n}\n',
    ),
    (
        "csharp",
        'using System;\n\nnamespace Demo {\n    class Program {\n        static void Main(string[] args) {\n            Console.WriteLine("hi");\n        }\n    }\n}\n',
    ),
    ("ruby", "def greet(name)\n  puts \"hello #{name}\"\nend\n\ngreet('world')\n"),
    ("html", "<!DOCTYPE html>\n<html>\n<body>\n  <p>hi</p>\n</body>\n</html>\n"),
    (
        "xml",
        '<?xml version="1.0"?>\n<catalog>\n  <book id="1"><title>X</title></book>\n</catalog>\n',
    ),
    (
        "css",
        "body {\n  color: red;\n  margin: 0 auto;\n}\n\na:hover { text-decoration: underline; }\n",
    ),
    (
        "diff",
        "diff --git a/f.py b/f.py\nindex 123..456 100644\n--- a/f.py\n+++ b/f.py\n@@ -1,3 +1,4 @@\n x\n-y\n+z\n+w\n",
    ),
    (
        "docker",
        'FROM alpine:3.19\nRUN apk add --no-cache git\nCOPY . /app\nCMD ["/app/run"]\n',
    ),
    (
        "console",
        "$ ls -la\ntotal 8\ndrwxr-xr-x  2 user user 4096 Sep 16 10:00 .\n$ echo done\ndone\n",
    ),
    (
        None,
        "This is just a sentence.\nAnother line of plain text.\nNothing codey here at all.\n",
    ),
    (None, "Notes:\n- buy milk\n- walk dog\n"),
    (None, "\n   \n"),
]


@pytest.mark.parametrize(("expected", "code"), BATTERY)
def test_battery(expected, code):
    assert guess_code_language(code) == expected


def test_every_alias_is_a_valid_pygments_lexer():
    """Whatever the detector may return must be accepted by codehilite as
    a fence info string -- a bad alias would silently downgrade rendering."""
    seen = {expected for expected, _ in BATTERY if expected}
    seen |= {
        # languages reachable via shebangs
        "javascript",
        "bash",
        "ruby",
        "perl",
        "r",
        "python",
        "php",
    }
    for alias in sorted(seen):
        try:
            get_lexer_by_name(alias)
        except ClassNotFound:  # pragma: no cover
            pytest.fail(
                f"guess_code_language can return {alias!r}, which is not a Pygments alias"
            )


def test_empty_and_whitespace_only():
    assert guess_code_language("") is None
    assert guess_code_language("  \n\t \n") is None


def test_oversized_input_returns_none_not_error():
    huge = "x = 1\n" * (MAX_CODE_CHARS // 6 + 10)
    assert len(huge) > MAX_CODE_CHARS
    # must not raise; a capped answer (here: python, from the prefix) or
    # None are both acceptable -- the guard is about bounding runtime.
    assert guess_code_language(huge) in (None, "python")


def test_no_runtime_import_of_pygments():
    """The detector is rule-based on purpose: its own source must not
    import Pygments (keeps render-time cost and import surface minimal)."""
    import code_lang

    src = Path(code_lang.__file__).read_text(encoding="utf-8")
    assert "import pygments" not in src
    assert "from pygments" not in src
