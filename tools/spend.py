#!/usr/bin/env python3
"""Measure model spend per seat for one room, from the runtimes' own logs.

BAND records, per seat and per room, the provider session the seat ran in. This tool
asks it for those ids, finds the matching logs, and sums the tokens used inside a time
window, so a tier or a whole run can be costed from what the models actually processed.

    python tools/spend.py --room <room-id>                          whole room
    python tools/spend.py --room <room-id> --since 2026-09-28T01:00Z --until 2026-09-28T04:30Z

Claude Code logs one line per streamed part of each assistant message; lines are
deduplicated by message and request id. Codex logs cumulative totals, so a window's spend
is the total at its end minus the total before its start. Token counts only: the seats
run on subscriptions, so there is no metered price to report.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOME = pathlib.Path.home()


def when(text: str | None) -> dt.datetime | None:
    if not text:
        return None
    try:
        return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def cli() -> str:
    for name in ("band", "jam"):
        if shutil.which(name):
            return shutil.which(name)
    win = HOME / "AppData" / "Local" / "Programs" / "jam" / "bin" / "jam.exe"
    if win.exists():
        return str(win)
    sys.exit("BAND CLI not found")


def seat_sessions(room: str) -> dict[str, tuple[str, str]]:
    """{seat: (provider, provider session id)} for the given room."""
    cfg = json.loads((ROOT / "factory" / "seats.json").read_text(encoding="utf-8"))
    who = subprocess.run([cli(), "whoami"], capture_output=True, text=True).stdout
    owner = re.search(r"@(\S+) ", who).group(1)
    out = {}
    for seat in cfg["seats"]:
        raw = subprocess.run([cli(), "sessions", "--as", f"{owner}/{seat['name']}", "--json"],
                             capture_output=True, text=True, encoding="utf-8").stdout
        for s in json.loads(raw or "[]"):
            sid = s.get("provider_session_id") or s.get("agent_session_id")
            if s.get("room") == room and sid:
                out[seat["name"]] = (s.get("provider", ""), sid)
    return out


def claude_usage(session_id: str, since, until) -> tuple[dict, str]:
    files = list((HOME / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
    files += list((HOME / ".claude" / "projects").glob(f"*/{session_id}/**/*.jsonl"))
    seen, tot, model = set(), dict(input=0, cached=0, output=0), ""
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message") or {}
            t = when(d.get("timestamp"))
            if d.get("type") != "assistant" or not t or msg.get("model") == "<synthetic>":
                continue
            if (since and t < since) or (until and t > until):
                continue
            key = (msg.get("id"), d.get("requestId"))
            if key in seen:
                continue
            seen.add(key)
            u = msg.get("usage") or {}
            tot["input"] += u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
            tot["cached"] += u.get("cache_read_input_tokens", 0)
            tot["output"] += u.get("output_tokens", 0)
            model = msg.get("model") or model
    return tot, model


def codex_usage(session_id: str, since, until) -> tuple[dict, str]:
    files = list((HOME / ".codex" / "sessions").glob(f"**/rollout-*{session_id}.jsonl"))
    before = after = None
    model = ""
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            p = d.get("payload") or {}
            if d.get("type") == "turn_context":
                model = p.get("model") or model
            info = p.get("info") if p.get("type") == "token_count" else None
            t = when(d.get("timestamp"))
            if not info or not t:
                continue
            total = info.get("total_token_usage") or {}
            if since and t < since:
                before = total
            elif not until or t <= until:
                after = total
    if not after:
        return dict(input=0, cached=0, output=0), model
    b = before or {}
    cached = after.get("cached_input_tokens", 0) - b.get("cached_input_tokens", 0)
    return dict(input=after.get("input_tokens", 0) - b.get("input_tokens", 0) - cached,
                cached=cached,
                output=after.get("output_tokens", 0) - b.get("output_tokens", 0)), model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--room", required=True)
    ap.add_argument("--since")
    ap.add_argument("--until")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    since, until = when(a.since), when(a.until)

    rows = []
    for seat, (provider, sid) in seat_sessions(a.room).items():
        use, model = (claude_usage if provider == "claudecode" else codex_usage)(sid, since, until)
        rows.append(dict(seat=seat, model=model, **use))
    if a.json:
        print(json.dumps(rows, indent=1))
        return 0
    print(f"{'seat':12} {'model':22} {'input':>12} {'cached input':>14} {'output':>10}")
    for r in rows:
        print(f"{r['seat']:12} {r['model']:22} {r['input']:>12,} {r['cached']:>14,} {r['output']:>10,}")
    print(f"{'total':35} {sum(r['input'] for r in rows):>12,} "
          f"{sum(r['cached'] for r in rows):>14,} {sum(r['output'] for r in rows):>10,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
