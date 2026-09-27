#!/usr/bin/env python3
"""Compute case-study metrics from a BAND room export.

Input: the JSON written by tools/export_room.py (or any JSON list/object with messages
that carry `content`, `message_type` and `sender_name`), or a plain-text transcript.

Only room prose counts (`text` and `error` messages); tool payloads echo verdict words and
are ignored. Each metric is attributed by the sender's role, so a foreman relaying a packet
is not counted as a packet:

  packet        builder message containing an EVIDENCE PACKET block with a commit line
  verdict       auditor message whose last line, or whose first line after "verdict ...:",
                is ACCEPT, REJECT or HELD (HELD counts as a rejection)
  held          foreman message that starts with HELD (a pre-audit rejection)
  release note  gatekeeper message starting RELEASE / RELEASED / HELD; released only when
                the first line says RELEASED and not HELD, FAIL or NOT RELEASED
  human answer  human message containing "Answer <id>:"
  human question foreman message containing "I need input to continue"

Role detection: the sender name contains the role word (foreman, builder, auditor,
gatekeeper); anything else is treated as human. Override with --roles
"foreman=<name>,builder=<name>,auditor=<name>,gatekeeper=<name>".

Usage: python tools/room_metrics.py <export.json> [--json] [--roles ...]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import re
import sys

ROLES = ("foreman", "builder", "auditor", "gatekeeper")
ITEM_RE = re.compile(r"\bitems?\s*#?\s*(\d+)", re.I)
CLAIMS_RE = re.compile(r"claims:\s*([0-9,\s-]+)", re.I)
COMMIT_RE = re.compile(r"^commit:\s*([0-9a-f]{7,40})", re.I | re.M)
GATE_RE = re.compile(r"(RELEASE|RELEASED|HELD)(?![A-Z])")
VERDICT_RE = re.compile(r"verdict[^:\n]*:\s*(ACCEPT|REJECT|HELD)\b", re.I)


def expand(nums: str) -> list[int]:
    out: list[int] = []
    for part in re.split(r"[,\s]+", nums.strip()):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a.isdigit() and b.isdigit():
                out.extend(range(int(a), int(b) + 1))
        elif part.isdigit():
            out.append(int(part))
    return out


def load_messages(path: pathlib.Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
        return [{"text": b, "sender": "", "ts": ""} for b in blocks]
    if isinstance(data, dict):
        for key in ("messages", "items", "data", "events"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return []
    out = []
    for m in data:
        if not isinstance(m, dict):
            continue
        # accepts Band's room download (camelCase) and the jam CLI's JSON (snake_case)
        mtype = str(m.get("messageType") or m.get("message_type") or m.get("type") or "text")
        if mtype not in ("text", "error"):
            continue
        text = m.get("content") or m.get("text") or m.get("body") or ""
        if isinstance(text, dict):
            text = json.dumps(text)
        sender = (m.get("senderName") or m.get("sender_name") or m.get("sender")
                  or m.get("author") or "")
        if isinstance(sender, dict):
            sender = sender.get("handle") or sender.get("name") or ""
        ts = str(m.get("insertedAt") or m.get("inserted_at") or m.get("createdAt")
                 or m.get("created_at") or m.get("timestamp") or "")
        out.append({"text": str(text), "sender": str(sender), "ts": ts, "type": mtype})
    out.sort(key=lambda x: x["ts"])
    return out


def role_of(sender: str, roles: dict[str, str]) -> str:
    s = sender.lower()
    for role, name in roles.items():
        if name and name.lower() in s:
            return role
    for role in ROLES:
        if role in s:
            return role
    return "human"


def parse_ts(ts: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def compute(msgs: list[dict], roles: dict[str, str]) -> dict:
    packets: list[dict] = []
    verdicts: list[dict] = []
    helds: list[dict] = []
    releases: list[dict] = []
    human_questions = 0
    human_answers = 0
    errors = 0
    rejections_per_item: collections.Counter[int] = collections.Counter()
    items_rejected: set[int] = set()
    items_accepted: set[int] = set()
    last_claims: list[int] = []
    first_ts: dt.datetime | None = None
    last_ts: dt.datetime | None = None

    for m in msgs:
        role = role_of(m["sender"], roles)
        t = m["text"]
        u = t.upper()
        when = parse_ts(m["ts"])
        if when:
            first_ts = first_ts or when
            last_ts = when
        if m["type"] == "error":
            errors += 1
            continue
        body = re.sub(r"^(\s*@\[\[[^\]]+\]\]\s*)+", "", t)  # drop leading mention tokens
        u = body.upper()
        lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
        last_line = lines[-1].upper() if lines else ""

        if role == "builder" and "EVIDENCE PACKET" in u and COMMIT_RE.search(t):
            c = CLAIMS_RE.search(t)
            last_claims = expand(c.group(1)) if c else []
            packets.append({"commit": COMMIT_RE.search(t).group(1)[:7], "claims": last_claims, "ts": m["ts"]})
        elif role == "auditor" and (last_line in ("ACCEPT", "REJECT", "HELD")
                                    or VERDICT_RE.search(lines[0] if lines else "")):
            mv = VERDICT_RE.search(lines[0] if lines else "")
            word = (mv.group(1).upper() if mv else last_line)
            word = "REJECT" if word == "HELD" else word     # an auditor hold is a rejection
            verdicts.append({"verdict": word, "ts": m["ts"]})
            if word == "REJECT":
                for it in {int(x) for x in ITEM_RE.findall(t)}:
                    rejections_per_item[it] += 1
                    items_rejected.add(it)
            else:
                for it in last_claims:
                    items_accepted.add(it)
        elif role == "foreman" and u.startswith("HELD"):
            helds.append({"ts": m["ts"], "reason": lines[1][:120] if len(lines) > 1 else ""})
            for it in {int(x) for x in ITEM_RE.findall(t)}:
                rejections_per_item[it] += 1
                items_rejected.add(it)
        elif role == "gatekeeper" and GATE_RE.match(u):
            head = lines[0].upper() if lines else ""
            released = ("RELEASED" in head and "NOT RELEASED" not in head
                        and "HELD" not in head and "FAIL" not in head)
            releases.append({"released": released, "ts": m["ts"], "head": lines[0][:100] if lines else ""})
        elif role == "foreman" and "I NEED INPUT TO CONTINUE" in u:
            human_questions += 1
        elif role == "human" and re.search(r"\bAnswer\s+[0-9A-F]{6,}:", t):
            human_answers += 1

    first_pass = items_accepted - items_rejected
    wall = (last_ts - first_ts) if (first_ts and last_ts) else None
    # false accept: an auditor ACCEPT followed (before the next ACCEPT) by a gatekeeper hold
    false_accepts = 0
    events = sorted(
        [("A", v["ts"]) for v in verdicts if v["verdict"] == "ACCEPT"]
        + [("H", r["ts"]) for r in releases if not r["released"]],
        key=lambda e: e[1],
    )
    prev = None
    for kind, _ in events:
        if kind == "H" and prev == "A":
            false_accepts += 1
        prev = kind
    accepts = sum(1 for v in verdicts if v["verdict"] == "ACCEPT")
    return {
        "messages_prose": len(msgs),
        "errors": errors,
        "packets": len(packets),
        "packet_commits": [p["commit"] for p in packets],
        "verdicts_accept": sum(1 for v in verdicts if v["verdict"] == "ACCEPT"),
        "verdicts_reject": sum(1 for v in verdicts if v["verdict"] == "REJECT"),
        "foreman_held_before_audit": len(helds),
        "held_reasons": [h["reason"] for h in helds],
        "releases_pass": sum(1 for r in releases if r["released"]),
        "releases_fail": sum(1 for r in releases if not r["released"]),
        "false_accepts": false_accepts,
        "false_accept_rate": round(false_accepts / accepts, 3) if accepts else None,
        "rework_cap_hits": sum(1 for n in rejections_per_item.values() if n >= 3),
        "human_questions": human_questions,
        "human_answers": human_answers,
        "items_accepted": len(items_accepted),
        "items_rejected_ever": sorted(items_rejected),
        "first_pass_rate": round(len(first_pass) / len(items_accepted), 3) if items_accepted else None,
        "max_rework_loops_on_one_item": max(rejections_per_item.values()) if rejections_per_item else 0,
        "wall_clock": str(wall) if wall else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("export")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--roles", default="", help="foreman=<name>,builder=<name>,...")
    ap.add_argument("--since", default="", help="ISO timestamp; ignore messages before it (e.g. the smoke tests)")
    a = ap.parse_args()
    roles = {}
    for pair in a.roles.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            roles[k.strip()] = v.strip()
    msgs = load_messages(pathlib.Path(a.export))
    if a.since:
        msgs = [m for m in msgs if m["ts"] >= a.since]
    if not msgs:
        print("no messages parsed", file=sys.stderr)
        return 1
    res = compute(msgs, roles)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        for k, v in res.items():
            print(f"{k:30} {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
