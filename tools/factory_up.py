#!/usr/bin/env python3
"""Stand the factory up from factory/seats.json, on macOS, Linux or Windows.

Creates one Jam-owned BAND agent per seat with its mandate live-linked, then one room that
holds every seat and the human owner. Idempotent: a seat that already exists is refreshed
(mandate link, runtime settings, launch flags), never recreated. The room id is kept in
private/room.txt (gitignored).

    python tools/factory_up.py --dry-run    probe every runtime, create nothing
    python tools/factory_up.py              create or refresh the seats, reuse or create the room
    python tools/factory_up.py --new-room   same, but always start a fresh room (one room per run)
    python tools/factory_up.py --stop       stop every seat's runtime, keep identities and room

Needs Band Desktop signed in (its CLI is `band`, formerly `jam`), and the coding CLIs the
seats use (Claude Code, Codex) signed in.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def find_cli(explicit: str | None) -> str:
    if explicit:
        return explicit
    for name in ("band", "jam"):
        path = shutil.which(name)
        if path:
            return path
    win = pathlib.Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "jam" / "bin" / "jam.exe"
    if win.exists():
        return str(win)
    sys.exit("BAND CLI not found: install Band Desktop, or pass --cli <path>")


def run(cli: str, *args: str) -> tuple[int, str]:
    p = subprocess.run([cli, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def launch_flags(seat: dict) -> list[str]:
    """Runtime-template flags: launch arguments and tool restrictions."""
    flags = [f"--spawn-arg={a}" for a in seat.get("spawn_args", [])]
    for tool in seat.get("claude_disallowed_tools", []):
        flags += ["--claude-disallowed-tool", tool]
    if seat.get("claude_strict_mcp_config"):
        flags.append("--claude-strict-mcp-config")
    return flags


def runtime_flags(seat: dict, prefix: str) -> list[str]:
    """Model, effort, approval and sandbox; `prefix` is '--runtime-' on create, '--' on settings."""
    out = []
    for key in ("model", "effort", "approval", "sandbox"):
        if seat.get(key):
            out += [f"{prefix}{key}", seat[key]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--config", default=str(ROOT / "factory" / "seats.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--new-room", action="store_true")
    ap.add_argument("--stop", action="store_true")
    ap.add_argument("--cli", default=None, help="path to the band/jam CLI")
    a = ap.parse_args()

    cli = find_cli(a.cli)
    cfg = json.loads(pathlib.Path(a.config).read_text(encoding="utf-8"))
    workspace = str((ROOT / cfg.get("workspace", ".")).resolve())

    code, who = run(cli, "whoami")
    m = re.search(r"@(\S+) .*\[user\] ([0-9a-f-]{36})", who)
    if code != 0 or not m:
        sys.exit(f"not signed in to BAND: {who.strip()}")
    owner, user_id = m.group(1), m.group(2)
    seats = cfg["seats"]
    handles = {s["name"]: f"{owner}/{s['name']}" for s in seats}
    print(f"owner @{owner}  workspace {workspace}")

    if a.stop:
        for h in handles.values():
            print(f"stop {h}: {run(cli, 'stop', '--as', h)[1].strip()}")
        return 0

    _, listing = run(cli, "list")
    for s in seats:
        handle = handles[s["name"]]
        mandate = ROOT / s["mandate"]
        if not mandate.exists():
            sys.exit(f"mandate missing: {mandate}")
        create = ["agent", "create", "--session", s["name"], "--name", s["name"],
                  "--description", s["description"], "--cwd", workspace,
                  "--transport", s["transport"], "--runtime-auth", s["auth"],
                  *runtime_flags(s, "--runtime-"), *launch_flags(s)]

        if a.dry_run:
            code, out = run(cli, *create, "--dry-run", "--json")
            try:
                probe = json.loads(out[out.index("{"):out.rindex("}") + 1])["probe"]
                print(f"probe {handle}: ok={probe['ok']}  {probe['message'][:110]}")
            except (ValueError, KeyError):
                print(f"probe {handle}: failed  {out.strip()[:300]}")
            continue

        if handle not in listing:
            print(f"create {handle}")
            code, out = run(cli, *create, "--instructions-file", str(mandate), "--json")
            if code != 0:
                sys.exit(f"create failed for {handle}:\n{out}")
        else:
            print(f"refresh {handle}")
            steps = [
                ["agent", "instructions", "set", "--as", handle, "--instructions-file", str(mandate)],
                ["runtime", "settings", "--as", handle, *runtime_flags(s, "--")] if runtime_flags(s, "--") else None,
                ["runtime", "template", "set", "--as", handle, *launch_flags(s), "--apply-and-restart"] if launch_flags(s) else None,
            ]
            for step in filter(None, steps):
                code, out = run(cli, *step)
                if code != 0:
                    print(f"  warning: {' '.join(step[:3])}: {out.strip()[:200]}")

    if a.dry_run:
        return 0

    owner_seat = next((s["name"] for s in seats if s.get("room_owner")), seats[0]["name"])
    owner_handle = handles[owner_seat]
    room_file = ROOT / "private" / "room.txt"
    if room_file.exists() and not a.new_room:
        room = room_file.read_text(encoding="utf-8").strip()
        print(f"room {room} (reused from private/room.txt)")
    else:
        others = [x for h in handles.values() if h != owner_handle for x in ("--with", h)]
        code, out = run(cli, "chat", "new", "--as", owner_handle, *others)
        ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", out)
        if code != 0 or not ids:
            sys.exit(f"room creation failed: {out}")
        room = ids[-1]
        room_file.parent.mkdir(parents=True, exist_ok=True)
        room_file.write_text(room + "\n", encoding="utf-8")
        print(f"room {room} (new)")

    for participant in [user_id] + [h for h in handles.values() if h != owner_handle]:
        code, out = run(cli, "chat", "add", "--as", owner_handle, room, participant)
        if code != 0 and "409" not in out:  # 409: already a member
            print(f"  warning: add {participant}: {out.strip()[:200]}")
    print(run(cli, "chat", "participants", "--as", owner_handle, room)[1].rstrip())
    print(f"\nPost the task in the room and mention @{owner_handle}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
