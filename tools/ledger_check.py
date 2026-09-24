#!/usr/bin/env python3
"""Deterministic gate: execute every machine-checkable item of an acceptance ledger.

The foreman writes the ledger as JSON (see factory/ledger.example.json). Each item has an
id, a description, and optionally a `check` command that must exit with `expect_exit`
(default 0) when run from `cwd` (default the stage folder). Items without a check are
listed as MANUAL so the auditor knows what still needs judgement.

The auditor and the gatekeeper run this before any model-based judgement; a FAIL here
is a rejection with no further discussion.

Usage: python tools/ledger_check.py <ledger.json> <folder> [--only 8,9,10] [--json]
Exit code 0 = every checked item passed, 1 = at least one FAIL, 2 = ledger error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time


def run(cmd: str, cwd: pathlib.Path, timeout: int) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired as e:
        return 124, f"timeout after {timeout}s: {e}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger")
    ap.add_argument("folder")
    ap.add_argument("--only", default="", help="comma-separated item ids to run")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    try:
        ledger = json.loads(pathlib.Path(a.ledger).read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"ledger error: {e}", file=sys.stderr)
        return 2
    items = ledger.get("items") if isinstance(ledger, dict) else ledger
    if not isinstance(items, list):
        print("ledger error: no items list", file=sys.stderr)
        return 2
    only = {int(x) for x in a.only.split(",") if x.strip().isdigit()} if a.only else None
    folder = pathlib.Path(a.folder).resolve()

    results = []
    for it in items:
        iid = it.get("id")
        if only is not None and iid not in only:
            continue
        check = it.get("check")
        if not check:
            results.append({"id": iid, "status": "MANUAL", "desc": it.get("desc", "")})
            continue
        cwd = folder / it["cwd"] if it.get("cwd") else folder
        t0 = time.time()
        code, out = run(check, cwd, it.get("timeout", a.timeout))
        expect = it.get("expect_exit", 0)
        digest = hashlib.sha256(out.encode("utf-8", "replace")).hexdigest()[:12]
        results.append({
            "id": iid, "status": "PASS" if code == expect else "FAIL",
            "desc": it.get("desc", ""), "cmd": check, "exit": code, "expect": expect,
            "digest": digest, "seconds": round(time.time() - t0, 1),
            "tail": "\n".join(out.strip().splitlines()[-3:]),
        })

    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = [r for r in results if r["status"] == "FAIL"]
    manual = sum(1 for r in results if r["status"] == "MANUAL")
    if a.json:
        print(json.dumps({"folder": str(folder), "pass": passed, "fail": len(failed),
                          "manual": manual, "results": results}, indent=1))
    else:
        for r in results:
            line = f"{r['status']:6} #{r['id']:<3} {r['desc'][:70]}"
            if r["status"] != "MANUAL":
                line += f"  [exit {r['exit']} expected {r['expect']}, digest {r['digest']}, {r['seconds']}s]"
            print(line)
            if r["status"] == "FAIL" and r.get("tail"):
                print("       " + r["tail"].replace("\n", "\n       "))
        print(f"LEDGER CHECK: {passed} PASS, {len(failed)} FAIL, {manual} MANUAL")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
