#!/usr/bin/env python3
"""Export a BAND room through the jam CLI into one JSON file.

Stand-in for the organisers' `harness export-room` until that tool is published; the
output is a JSON object {"room": ..., "exported_at": ..., "messages": [...]} where each
message is the structured record jam prints with `room messages --json`, all types, all
pages, oldest first.

Usage: python tools/export_room.py <room-id> <out.json> [--jam <path-to-jam.exe>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys

TYPES = ["text", "thought", "tool_call", "tool_result", "error"]


def default_jam() -> str:
    cand = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "jam", "bin", "jam.exe"),
        "jam",
    ]
    for c in cand:
        if c == "jam" or os.path.exists(c):
            return c
    return "jam"


def fetch_page(jam: str, room: str, mtype: str, page: int) -> dict:
    out = subprocess.run(
        [jam, "room", "messages", room, "--type", mtype, "--page", str(page), "--json"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if out.returncode != 0:
        raise SystemExit(f"jam failed on {mtype} page {page}: {out.stderr.strip()[:300]}")
    return json.loads(out.stdout)


def extract(page: dict) -> tuple[list[dict], int | None]:
    msgs = None
    for key in ("messages", "items", "data"):
        if isinstance(page.get(key), list):
            msgs = page[key]
            break
    if msgs is None and isinstance(page, list):
        msgs = page
    total_pages = None
    for key in ("total_pages", "pages", "page_count"):
        if isinstance(page.get(key), int):
            total_pages = page[key]
            break
    return msgs or [], total_pages


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("room")
    ap.add_argument("out")
    ap.add_argument("--jam", default=default_jam())
    a = ap.parse_args()

    seen: dict[str, dict] = {}
    for mtype in TYPES:
        page = 1
        while True:
            data = fetch_page(a.jam, a.room, mtype, page)
            msgs, total_pages = extract(data)
            if not msgs:
                break
            new = 0
            for m in msgs:
                mid = str(m.get("id") or m.get("message_id") or f"{mtype}:{page}:{len(seen)}")
                if mid not in seen:
                    seen[mid] = m
                    new += 1
            if new == 0 or (total_pages is not None and page >= total_pages):
                break
            page += 1

    def ts(m: dict) -> str:
        return str(m.get("inserted_at") or m.get("created_at") or m.get("timestamp") or "")

    messages = sorted(seen.values(), key=ts)

    # scrub machine-specific data from every string value (never from the serialised
    # JSON: a regex over escaped text can eat an escaping backslash and corrupt the file)
    import getpass
    import platform
    import re
    home = pathlib.Path.home()
    repo = pathlib.Path(__file__).resolve().parents[1]
    user = re.escape(getpass.getuser())
    host = re.escape(platform.node())
    sep = r"[\\/]+"          # a character class, never an alternation of quantified groups

    def forms(path: pathlib.Path) -> list[str]:
        s = str(path)
        out = {s, s.replace("\\", "\\\\"), s.replace("\\", "/")}
        if path.drive:
            out.add("/" + path.drive.rstrip(":").lower() + s[2:].replace("\\", "/"))
        return sorted(out, key=len, reverse=True)

    names = sorted({m.get("sender_name") for m in messages if m.get("sender_type") == "User"} - {None, ""},
                   key=len, reverse=True)

    def scrub(s: str) -> str:
        for v in forms(repo):
            s = s.replace(v, "<repo>")
        for v in forms(home):
            s = s.replace(v, "~")
        s = re.sub(r"(?i)(?:[A-Za-z]:)?" + sep + "Users" + sep + user, "~", s)
        s = re.sub(r"(?i)(?:[A-Za-z]:)?" + sep + "Users" + sep + r"[A-Z0-9]{1,6}~\d", "~", s)
        s = re.sub(r"(?i)" + host + sep + user, "HOST/USER", s)
        s = re.sub(r"(?<![A-Za-z0-9<])[A-Za-z]:[\\/]+[^\s\"'`,;)\]]*", "<path>", s)  # other drive paths
        s = re.sub(r"\b[A-Z0-9]{1,6}~\d\b", "<home>", s)  # 8.3 short names
        # separator-stripped forms from shells that ate the backslashes (C:UsersNAME~1AppData...)
        s = re.sub(r"(?i)[A-Za-z]:Users(?:" + user + r"|[A-Z0-9]{1,6}~[0-9])", "~", s)
        s = re.sub(r"(?i)(?<![A-Za-z])Users(?:" + user + r"|[A-Z0-9]{1,6}~[0-9])(?=[A-Z])", "~", s)
        for n in names:
            s = s.replace(n, "human")
        return s

    def walk(x):
        if isinstance(x, str):
            return scrub(x)
        if isinstance(x, list):
            return [walk(i) for i in x]
        if isinstance(x, dict):
            return {k: walk(v) for k, v in x.items()}
        return x

    messages = walk(messages)

    payload = {
        "room": a.room,
        "exported_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "exporter": "tools/export_room.py via jam room messages --json",
        "message_count": len(messages),
        "messages": messages,
    }
    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    by_type: dict[str, int] = {}
    for m in messages:
        t = str(m.get("type") or m.get("message_type") or "?")
        by_type[t] = by_type.get(t, 0) + 1
    print(f"exported {len(messages)} messages to {out} {by_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
