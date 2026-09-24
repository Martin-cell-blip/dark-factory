#!/usr/bin/env python3
"""Structural check of the repository before pushing.

Local stand-in for the organisers' `harness check` (which is published at kickoff):
  * every stage-N folder is complete and self-contained
  * stage folders are numbered contiguously from 1
  * no secrets, tokens, private keys or machine-specific paths anywhere tracked
  * required factory files exist

Usage: python tools/stage_check.py [repo_root]
Exit code 0 = ok, 1 = findings.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REQUIRED_ROOT = [
    "README.md",
    "LICENSE",
    "mandates",
    "factory/FACTORY.md",
    "factory/evidence-packet.md",
]
REQUIRED_IN_STAGE = ["Dockerfile", "README.md"]
TEST_HINTS = ("tests", "test", "test_", "_test.")

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{16,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"(?i)(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"[A-Z]:\\Users\\[^\\\s]+"),          # windows home paths
    re.compile(r"(?i)[\\/]Users[\\/][A-Z0-9]{1,6}~\d"),  # windows 8.3 short-name home paths
    re.compile(r"\b[A-Z]:\\\\?[A-Za-z0-9_.-]+\\\\?[A-Za-z0-9_.-]+"),  # any absolute drive path
    re.compile(r"/home/[a-z][\w-]*/"),               # linux home paths
    re.compile(r"/Users/[A-Za-z][\w-]*/"),           # mac home paths
]
SKIP_DIRS = {".git", ".venv", "__pycache__", "node_modules", "vendor", "wheels"}


def tracked_files(root: pathlib.Path) -> list[pathlib.Path]:
    try:
        out = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True).stdout
        return [root / p for p in out.decode("utf-8").split("\0") if p]
    except Exception:
        return [p for p in root.rglob("*") if p.is_file() and not any(s in p.parts for s in SKIP_DIRS)]


def main() -> int:
    root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    findings: list[str] = []

    for rel in REQUIRED_ROOT:
        if not (root / rel).exists():
            findings.append(f"missing required: {rel}")

    stages = sorted(p for p in root.glob("stage-*") if p.is_dir())
    nums = []
    for s in stages:
        m = re.fullmatch(r"stage-(\d+)", s.name)
        if not m:
            findings.append(f"bad stage folder name: {s.name}")
            continue
        nums.append(int(m.group(1)))
        for req in REQUIRED_IN_STAGE:
            if not (s / req).exists():
                findings.append(f"{s.name}: missing {req}")
        if not any(h in str(p.relative_to(s)).lower() for p in s.rglob("*") for h in TEST_HINTS):
            findings.append(f"{s.name}: no tests found")
        for p in s.rglob("*"):
            if p.is_symlink():
                findings.append(f"{s.name}: symlink not allowed: {p.relative_to(root)}")
    if nums and nums != list(range(1, len(nums) + 1)):
        findings.append(f"stage folders not contiguous from 1: {nums}")
    if not nums:
        print("note: no stage folders yet (expected before the build window)")

    for f in tracked_files(root):
        if any(s in f.parts for s in SKIP_DIRS):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in SECRET_PATTERNS:
            for m in pat.finditer(text):
                hit = m.group(0)
                if "..." in hit or "<" in hit or "0000-0000" in hit:
                    continue  # documented placeholder, not a value
                findings.append(f"possible secret/private path in {f.relative_to(root)}: {hit[:40]!r}")

    if findings:
        print("STAGE CHECK: findings")
        print("\n".join(findings))
        return 1
    print(f"STAGE CHECK: ok ({len(nums)} stage folders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
