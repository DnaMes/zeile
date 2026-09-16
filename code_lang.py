#!/usr/bin/python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 erdlabs
"""Rule-based language detection for unlabeled fenced code blocks.

Pygments' own guess_lexer()/analyse_text() turned out to be unusable for the
short snippets that actually appear in markdown documents -- measured on a
battery of obvious samples (2026-09-16): a Python function was detected as
"Tera Term macro", JSON and SQL as "Text only", YAML as "Transact-SQL", and
PythonLexer.analyse_text() scored a *perfect 1.0 on JavaScript and Go code*
while scoring 0.0 on Python itself. So instead of forwarding to Pygments,
this module runs its own deterministic, weighted-regex heuristics:

1. definitive fast paths (shebangs, parseable JSON, XML declaration,
   ``<?php``, diff headers, Dockerfile instructions),
2. structured-format heuristics (YAML, TOML, INI, CSS, HTML/XML snippets,
   ``$``-prompt shell sessions, SQL),
3. weighted indicator patterns per programming language with an absolute
   threshold *and* a margin over the runner-up, so ambiguous or plain-text
   blocks stay unhighlighted instead of getting a confidently wrong colour.

Every returned string is a Pygments alias accepted by codehilite as a fence
info string (asserted by tests/test_code_lang.py). Detection never raises
and never takes quadratic time; input is capped at MAX_CODE_CHARS.

The function is conservative on purpose: ``None`` (render as plain,
uncoloured code) is always a safe answer, a wrong language is not.
"""

from __future__ import annotations

import json
import re

MAX_CODE_CHARS = 100_000

# Absolute score a language must reach to be considered at all, and the
# factor by which it must beat the runner-up (ties mean "don't know").
_MIN_SCORE = 2.0
_MARGIN = 1.3
# A score this high wins immediately, before structured-format heuristics
# get a chance to misfire on code that merely looks config-ish.
_STRONG_SCORE = 4.0


def _hits(pattern: str, text: str, flags: int = re.MULTILINE) -> int:
    return len(re.findall(pattern, text, flags))


def _score(patterns: list[tuple[str, float]], text: str) -> float:
    """Weighted pattern score; each pattern's hit count is capped so one
    noisy indicator (e.g. `$VAR` appearing five times) cannot dominate."""
    total = 0.0
    for pattern, weight in patterns:
        total += min(_hits(pattern, text), 4) * weight
    return total


# --- definitive single-signal fast paths -------------------------------------

_SHEBANG_MAP = (
    (r"python", "python"),
    (r"node|deno", "javascript"),
    (r"(^|/|env )(ba|z|a|k|fi)?sh", "bash"),
    (r"ruby", "ruby"),
    (r"perl", "perl"),
    (r"php", "php"),
    (r"Rscript", "r"),
)

_YAML_KV = re.compile(r"^[ \t]*[A-Za-z0-9_.\"'-]+:( |$)", re.MULTILINE)
_BULLET = re.compile(r"^[ \t]*- \S", re.MULTILINE)

_LANG_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "python": [
        (r"^\s*def \w+\s*\(", 2.5),
        (r"^\s*class \w+(\([^\)]*\))?:\s*$", 2.5),
        (r"^\s*(from [\w.]+ import |import \w+)", 2.0),
        (r"\bself\.", 1.5),
        (r"\belif\b", 2.5),
        (r"^\s*@\w+", 1.5),
        (r"\bprint\(", 1.0),
        (r"\blambda \w+.*:", 1.5),
        (r"__name__", 2.0),
        (r"\braise \w+", 1.5),
        (r"\bf\"[^\"]*\"", 1.0),
    ],
    "javascript": [
        (r"\bfunction\b", 1.5),
        (r"=>", 1.5),
        (r"\b(const|let)\s+\w+\s*=", 1.5),
        (r"\bvar\s+\w+\s*=", 1.0),
        (r"console\.log", 2.5),
        (r"require\(['\"]", 2.0),
        (r"module\.exports", 2.5),
        (r"^\s*export (default|function|const|class)", 2.0),
        (r"document\.\w+", 1.5),
        (r"\.then\(", 1.5),
        (r"\basync function\b|\bawait\b", 1.5),
    ],
    "typescript": [
        # JS-shared indicators first: TS is a superset, so a TS sample also
        # lights these up. The TS-only ones below decide the race.
        (r"\bfunction\b", 1.0),
        (r"=>", 1.0),
        (r"\b(const|let)\s+\w+\s*=", 1.0),
        (r"^\s*export (default|function|const|class)", 1.5),
        (r":\s*(string|number|boolean|void|any|unknown)\b", 2.5),
        (r"^\s*interface \w+", 2.5),
        (r"^\s*import \w+ .* from ['\"]", 1.0),
        (r"\benum \w+", 2.0),
        (r"\bas \w+\b", 1.0),
        (r":\s*\w+\[\]", 1.5),
    ],
    "c": [
        (r"#include\s*<", 2.5),
        (r"\bint\s+main\s*\(", 2.5),
        (r"\bprintf\s*\(", 2.0),
        (r"\bmalloc\(|\bfree\(", 1.5),
        (r"^\s*struct \w+", 2.0),
        (r"\btypedef\b", 2.0),
        (r"\buint\d+_t\b", 2.0),
    ],
    "cpp": [
        (r"std::", 2.5),
        (r"#include\s*<(iostream|vector|string|map|memory)>", 2.5),
        (r"\bnamespace \w+", 2.0),
        (r"\btemplate\s*<", 2.5),
        (r"\b(cout|cin|cerr)\b", 2.5),
        (r"^\s*class \w+\s*(final\s*)?\{", 2.0),
    ],
    "csharp": [
        (r"^using\s+[\w.]+;", 2.5),
        (r"Console\.(Write|Read)", 2.5),
        (r"^\s*namespace \w+", 1.5),
        (
            r"\b(public|private|internal)\s+(static\s+)?(async\s+)?\w+[\w<>\[\]]*\s+\w+\s*\(",
            1.5,
        ),
        (r"^\s*\[(\w+\.)?\w+([^(]*\([^)]*\))?\]\s*$", 1.0),
    ],
    "java": [
        (r"\bpublic\s+class\s+\w+", 2.5),
        (r"System\.out\.print", 2.5),
        (r"^import\s+java\.", 2.5),
        (r"^\s*package\s+[\w.]+;", 2.0),
        (r"\bnew\s+\w+\s*\(", 1.0),
    ],
    "go": [
        (r"^package \w+", 3.0),
        (r":=", 2.0),
        (r"\bfunc\s+\w*\s*\(", 2.5),
        (r"\bfmt\.\w+", 2.5),
        (r"^\s*import \(", 2.0),
        (r"\bnil\b", 1.0),
    ],
    "rust": [
        (r"\bfn\s+\w+\s*\(", 2.5),
        (r"\blet\s+mut\b", 2.5),
        (r"^use\s+[\w:]+::", 2.0),
        (r"\bimpl\b", 2.0),
        (r"\b(println|print|format|vec)!", 2.5),
        (r"\bpub\s+fn\b", 2.5),
        (r"&str\b|&mut\b", 1.5),
    ],
    "ruby": [
        (r"^\s*def \w+[^(]*$", 2.5),
        (r"^\s*end\s*$", 2.0),
        (r"\bputs\b", 2.5),
        (r"require ['\"]", 2.5),
        (r"\bdo \|[^\|]*\|", 2.5),
        (r"\bgem ['\"]", 2.5),
        (r"@\w+", 1.0),
        (r"\belsif\b", 2.5),
        (r"attr_(accessor|reader|writer)", 2.5),
    ],
    "bash": [
        (r"\$\{?\w+\}?", 0.5),
        (r"\becho\s", 1.0),
        (r"^\s*(if|for|while)\b.*;\s*(then|do)\b", 2.5),
        (r"^\s*(fi|done|esac)\s*$", 2.5),
        (
            r"\b(sudo|pacman|apt|apt-get|npm|yarn|pip3?|docker|git|curl|wget|systemctl)\b",
            0.5,
        ),
        (r"^\s*export\s+\w+=", 1.5),
        (r"&&|\|\|", 0.5),
        (r"2>&1|/dev/null", 2.0),
        (r"^\s*#\s*\w", 0.2),
        (r"\b--\w[\w-]*", 0.3),
    ],
}

_SQL_KEYWORDS = (
    "SELECT",
    "INSERT INTO",
    "UPDATE",
    "DELETE FROM",
    "CREATE TABLE",
    "ALTER TABLE",
    "DROP TABLE",
    "PRIMARY KEY",
    "FOREIGN KEY",
    "NOT NULL",
    "REFERENCES",
    " FROM ",
    " WHERE",
    " JOIN ",
    "GROUP BY",
    "ORDER BY",
    " VALUES",
    "LIMIT",
)

_HTML_TAG = (
    r"</?(div|span|p\b|a\b|ul|ol|li|h[1-6]|table|thead|tbody|tr\b|td|th|script"
    r"|style|link|meta|br\b|img|input|form|nav|header|footer|section|article"
    r"|button|label|select|textarea)\b"
)


def _is_jsonish(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped[0] not in "[{":
        return False
    try:
        json.loads(stripped)
    except ValueError:
        # Lenient fallback: quoted-key density for JSON with trailing
        # commas or comments -- but only when it doesn't look like Python.
        kv = _hits(r"^\s*\"[^\"]+\"\s*:", stripped)
        return kv >= 2 and ";" not in stripped
    return True


def _looks_like_yaml(text: str) -> bool:
    if _hits(r";\s*$", text) > 0:
        return False
    kv_lines = len(_YAML_KV.findall(text))
    if kv_lines == 0:
        return False
    bullets = len(_BULLET.findall(text))
    doc_sep = text.startswith("---\n") or "\n---\n" in text
    return (kv_lines >= 2 and (bullets >= 1 or doc_sep)) or kv_lines >= 4


def _detect_structured(text: str) -> str | None:
    """Structured formats that regex/heuristics can decide with high
    precision. Runs only when no programming language scored strongly."""
    if _is_jsonish(text):
        return "json"
    if _looks_like_yaml(text):
        return "yaml"

    section = _hits(r"^\s*\[+[\w.$\" -]+\]+\s*$", text)
    assign = _hits(r"^\s*[A-Za-z0-9_.\"-]+\s*=\s*\S", text)
    if section or assign >= 2:
        if section:
            # With section headers, TOML needs a distinctly TOML-ish value
            # (a quoted string, or an [[array-of-tables]] header); bare
            # `key = true` pairs are far more likely INI / git-config.
            tomlish = re.search(r"=\s*(\"[^\"]*\"|'[^']*')", text) or re.search(
                r"^\s*\[\[", text, re.M
            )
            return "toml" if tomlish else "ini"
        tomlish = re.search(
            r"=\s*(\"[^\"]*\"|'[^']*'|true|false|\[[^\]]*\]|-?\d+\.\d+)", text
        )
        if tomlish and assign >= 2 and ";" not in text:
            return "toml"

    css_blocks = _hits(r"[\w.#-]+(\s*,\s*[\w.#-]+)*\s*\{[^{}]*:[^{}]*;[^{}]*\}", text)
    if css_blocks or re.search(r"@(media|import|keyframes)\b", text):
        return "css"

    html_tags = _hits(_HTML_TAG, text)
    if html_tags >= 2:
        return "html"
    closes = _hits(r"</[A-Za-z][\w.:-]*>", text)
    if closes >= 2:
        return "xml"

    prompts = _hits(r"^\s*[$>] ", text)
    if prompts >= 1 and len(text.strip().splitlines()) >= 2:
        return "console"

    sql = sum(1 for kw in _SQL_KEYWORDS if kw in text)
    sql_ci = sum(
        1 for kw in _SQL_KEYWORDS if re.search(kw.replace(" ", r"\s+"), text, re.I)
    )
    if (
        sql >= 2
        or (sql >= 1 and sql_ci >= 3)
        or (sql_ci >= 3 and text.rstrip().endswith(";"))
    ):
        return "sql"

    return None


def guess_code_language(code: str) -> str | None:
    """Best-effort language id (a Pygments alias) for an unlabeled code
    block, or None when nothing scored confidently. Never raises."""
    if not code or not code.strip():
        return None
    text = code if len(code) <= MAX_CODE_CHARS else code[:MAX_CODE_CHARS]

    # 1. shebangs are definitive
    first_line = text.split("\n", 1)[0].strip()
    if first_line.startswith("#!"):
        for pattern, lang in _SHEBANG_MAP:
            if re.search(pattern, first_line):
                return lang
        return "bash"

    # 2. other definitive single signals
    if text.lstrip().startswith("<?xml"):
        return "xml"
    if re.search(r"<!DOCTYPE html", text, re.I) or re.search(r"<html\b", text, re.I):
        return "html"
    if "<?php" in text:
        return "php"
    if re.match(r"^diff --git ", text) or (
        _hits(r"^--- (a/|\S)", text) >= 1 and _hits(r"^\+\+\+ (b/|\S)", text) >= 1
    ):
        return "diff"
    if re.search(r"^@@ -\d+[^\n]*@@ ", text, re.M):
        return "diff"
    if (
        _hits(r"^FROM \S+", text) >= 1
        and _hits(r"^(RUN|COPY|CMD|ENTRYPOINT|WORKDIR|ARG|ENV|LABEL|EXPOSE|VOLUME) ", text)
        >= 1
    ):
        return "docker"

    # 3. programming-language scoring
    scores = {lang: _score(patterns, text) for lang, patterns in _LANG_PATTERNS.items()}
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_lang, best = ranked[0]
    second = ranked[1][1]
    if best >= _STRONG_SCORE and best >= _MARGIN * max(second, 1.0):
        return best_lang

    # 4. structured formats, then weak language winners
    structured = _detect_structured(text)
    if structured is not None:
        return structured
    if best >= _MIN_SCORE and best >= _MARGIN * max(second, 1.0):
        return best_lang
    return None
