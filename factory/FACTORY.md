# The factory

## Pattern

An assembly line with a customs post and a release gate. Work moves forward on evidence and
backward on rejection. The human sits outside the line and is consulted only for product
decisions.

```
human ─task─▶ foreman ─ledger─▶ builder ─packet─▶ auditor ─verdict─▶ foreman ─release request─▶ gatekeeper ─release note─▶ foreman ─▶ human
                                   ▲                  │                                              │
                                   └──── reject: item number, expected vs actual ◀───────────────────┘
```

## Seats

| Seat | Mandate | Runtime | Writes product code |
|---|---|---|---|
| foreman | `mandates/foreman.md` | Codex, gpt-5.5, high effort | no |
| builder | `mandates/builder.md` | Claude Code | yes |
| auditor | `mandates/auditor.md` | Codex, gpt-5.5, high effort | tests only |
| gatekeeper | `mandates/gatekeeper.md` | Claude Code | no |

Each seat is a persistent BAND agent whose runtime BAND Desktop starts on demand. Its
mandate is attached as a live-linked file, so the standing instruction a reader sees here is
the one the seat runs under. The builder and the auditor use different model providers so
the seat that judges does not share the blind spots of the seat that built.
`factory/seats.json` holds the configuration, including launch flags: Codex memories off,
web tools and outside MCP servers off for the Claude seats.

## The mention graph

Each mandate names the next *role*, never a handle; a seat looks up the room participants at
handoff time to find who holds it. A seat can therefore be replaced mid-run, and a seat that
finds a role missing asks the foreman instead of skipping the step. A handoff ends the
sender's turn; nobody waits on a reply.

| From | To | When | Carries |
|---|---|---|---|
| human | foreman | task posted in the room | the task text |
| foreman | builder | ledger published | ledger item numbers |
| builder | auditor | commit ready | evidence packet |
| auditor | builder | an item fails, or the packet does not reproduce | item number, expected vs actual |
| auditor | foreman | every claimed item passes | verdict and sweep findings |
| foreman | gatekeeper | tier has no held items | commit to release |
| gatekeeper | builder or auditor | a release check fails | failing step and its output |
| gatekeeper | foreman | release passes | release note |
| foreman | human | a product decision, or a tier released | one question with a recommended option, or the release note |

## Verification, deterministic first

1. **Ledger gate.** The foreman writes the ledger as JSON (`factory/ledger.example.json`)
   with one targeted command per checkable item, boundary items included.
   `tools/ledger_check.py` executes it and reports `PASS`, `FAIL` or `MANUAL` per item.
2. **Holdouts.** The auditor's own acceptance tests live in `private/holdout/<folder>/`,
   written before the first packet and never readable by the builder.
3. **Judgement.** Only then does the auditor judge the `MANUAL` items and run its
   adversarial sweep: many callers on one resource, replays, torn sequences, malformed
   input, boundary arithmetic, restart. Timing-sensitive tests run ten times under the caps.
4. **Release.** The gatekeeper repeats the gate and the holdouts from a fresh clone, builds
   and starts the folder with no network under the caps, and scans the repository for
   secrets and private data.

## What the room holds at the end

The ledger (room plan and JSON artifact) with every item's final verdict; every evidence
packet and verdict, in order; one release note per tier. `tools/room_metrics.py` reads them
from the room export:

| Metric | Definition |
|---|---|
| packets | evidence packets posted by the builder |
| verdicts | auditor ACCEPT and REJECT (an auditor hold counts as a rejection) |
| holds before audit | foreman holds, such as a fixed name copied wrong |
| gate holds | release checks that failed at the gatekeeper |
| false-accept rate | auditor ACCEPTs later held at the gate, over all ACCEPTs |
| first-pass rate | items accepted on their first packet, over items accepted |
| rework | rejections per ledger item; three on one item are escalated to the human |
| human questions | product questions the foreman asked, and answers received |
| wall clock | first message to last release note |

## Operating

Prerequisites: Band Desktop signed in with its readiness checks green, Claude Code and
Codex (0.146 or later) signed in, Docker, Python 3.10 or later.

```
python tools/factory_up.py --new-room   # seats created or refreshed, one fresh room
python tools/factory_up.py --stop       # stop every runtime, keep identities and room
```

Run one room per task, so the room export holds that run and nothing else. Post the task in
the room as the human and mention the foreman; watch the board; answer only product
questions. After the last release note, export the room and commit the export with
`tools/room_metrics.py` output.

On Windows, commands inside Codex's `workspace-write` sandbox run as a separate user that
cannot reach the local BAND daemon, so the Codex seats run with `danger-full-access`, the
same host-native trust the Claude Code seats have. On macOS and Linux `workspace-write` can
be restored in `factory/seats.json`.

## Declared limitations

- A seat cannot approve another seat's permission request; a human must.
- The evidence packet proves what ran and what it printed, not that the right thing ran.
- Seats run with host-native access to the workspace machine.
