#!/usr/bin/env python3
"""Scan seat mandates for track-specific detail.

The hackathon disqualifies any mandate that names something specific to the track or the
challenge: endpoint paths, field names, error codes, element ids. This linter is a local
stand-in for the organisers' harness scan. It is deliberately strict: a false positive
costs a minute, a false negative costs the entry.

Usage:
    python tools/mandate_lint.py [mandates_dir] [--extra-terms terms.txt]

Exit code 0 = clean, 1 = findings.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

# Patterns that almost always mean "this mandate is a transcript of one problem".
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("url path", re.compile(r"(?<![\w`])/(?:api|v\d)[\w/{}:-]*")),
    ("route-like path", re.compile(r"(?<![\w:/`])/[a-z][\w-]*(?:/[\w{}:-]+)+")),
    ("http status code", re.compile(r"\b(?:HTTP\s*)?(?:[1-5]\d{2})\b(?=\s*(?:status|error|code|response|Bad|Not|Conflict|Unprocessable|Created|OK))")),
    ("http status code (bare)", re.compile(r"\b(?:200|201|204|400|401|403|404|409|422|429|500|502|503)\b")),
    ("data-testid", re.compile(r"data-testid", re.I)),
    ("json field literal", re.compile(r"\"[a-z_]+\"\s*:")),
    ("snake_case identifier in backticks", re.compile(r"`[a-z]+_[a-z_]+`")),
    ("camelCase identifier in backticks", re.compile(r"`[a-z]+[A-Z][A-Za-z]+`")),
    ("currency/money words", re.compile(r"\b(?:wallet|balance|transfer|payment|pocketful|venmo|cents|rounding of money)\b", re.I)),
    ("reservation words", re.compile(r"\b(?:reservation|restaurant|table|booking|tablekeeper|opentable|time ?zone)\b", re.I)),
    ("challenge words", re.compile(r"\b(?:stage[- ]?[1-4]|track|hackathon|lablab|spec\.md|SPEC)\b", re.I)),
]

# Words the mandates legitimately use that would otherwise trip a pattern.
ALLOW = {
    "table",  # only allowed when it is 'work table'? keep strict: not allowed. (left for clarity)
}


def lint_file(path: pathlib.Path, extra: list[re.Pattern[str]]) -> list[str]:
    findings: list[str] = []
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        for name, pat in PATTERNS + [("extra term", p) for p in extra]:
            for m in pat.finditer(line):
                token = m.group(0)
                if token.lower() in ALLOW:
                    continue
                findings.append(f"{path.name}:{lineno}: [{name}] {token!r}  <- {line.strip()[:90]}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mandates_dir", nargs="?", default="mandates")
    ap.add_argument("--extra-terms", help="file with one forbidden term per line (e.g. names lifted from the published spec)")
    args = ap.parse_args()

    extra: list[re.Pattern[str]] = []
    if args.extra_terms:
        for term in pathlib.Path(args.extra_terms).read_text(encoding="utf-8").splitlines():
            term = term.strip()
            if term and not term.startswith("#"):
                extra.append(re.compile(re.escape(term), re.I))

    root = pathlib.Path(args.mandates_dir)
    files = sorted(root.glob("*.md"))
    if not files:
        print(f"no mandates found under {root}", file=sys.stderr)
        return 2
    all_findings: list[str] = []
    for f in files:
        all_findings.extend(lint_file(f, extra))
    if all_findings:
        print("MANDATE LINT: findings (fix every one before submitting)")
        print("\n".join(all_findings))
        return 1
    print(f"MANDATE LINT: clean ({len(files)} files, {len(PATTERNS) + len(extra)} patterns)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
