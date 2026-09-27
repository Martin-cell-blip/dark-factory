# FACTORY.md

An evidence-gated software factory for Band Desktop: four seats, one that writes product
code and three that plan, verify and release. This file is enough to stand it up, explains
why it is built this way, what it cost, what failed on the way, and how it catches bad
work.

## Seats

| Seat | Harness | Model | Owns | Writes |
|---|---|---|---|---|
| [foreman](mandates/foreman.md) | Claude Code | claude-opus-5-5 | acceptance ledger, handoffs, board, verdicts, final report | ledgers |
| [builder](mandates/builder.md) | Claude Code | claude-opus-5-5 | implementation, design note, evidence packets | product code |
| [auditor](mandates/auditor.md) | Claude Code | claude-opus-5-5 | ledger coverage check, reproduction, holdout tests, adversarial sweep, verdicts | tests |
| [gatekeeper](mandates/gatekeeper.md) | Claude Code | claude-opus-5-5 | fresh-clone release check, release notes | release notes |

Each seat commits under its own git identity (`foreman@band.local`, `builder@band.local`,
`auditor@band.local`, `gatekeeper@band.local`), so the history shows who did what.

## Stand it up

You need Band Desktop signed in with its readiness checks green, Claude Code signed in,
Docker running, and Python 3.12 or later.

```
python tools/factory_up.py --dry-run     # probe the four runtimes, create nothing
python tools/factory_up.py --new-room    # create or refresh the seats, open a room
```

`factory/seats.json` is the whole configuration: seat names, harnesses, models, effort,
approval and sandbox policy, launch flags, and which seat owns the room. The script is
idempotent. Each mandate is attached as a live-linked file, so the text in `mandates/` is
the instruction the seat runs under. Every seat loads Band's own MCP server and nothing
else, with web tools disabled.

Run it: the script ends by printing the command that posts the task and mentions the
foreman. Post it, then do nothing else until the foreman's final report.

## Design choices, and why

**Nothing crosses a handoff without evidence a second seat can reproduce.** A handoff is
an evidence packet: full commit hash, exact commands, exit codes, output digests, the
ledger items claimed with their wording (`factory/evidence-packet.md`). The receiving seat
re-runs it before believing it; a claim without a packet is returned unread. Reason: a
model's summary of its own work is the least reliable signal in the room.

**The seat that judges does not share the builder's information.** Before anyone builds,
the auditor checks the foreman's ledger against the requirements, sentence by sentence,
and writes its own holdout tests. It reproduces each packet in its own worktree and sees
the builder's commits and packets, never its reasoning. Reason: a reviewer that reads the
builder's explanation inherits its mistakes.

**One harness, sized to measured limits.** A seat that stops at a usage limit stops for
good, because nobody may restart it once the task is dispatched. In the first rehearsal
the two Codex seats used 83% of a ChatGPT Plus five-hour limit in two and a half hours,
while the Claude seats did the larger half of the work without reaching a limit. Every
seat now runs Claude Code on one Max subscription, where the factory also decides which
tools and MCP servers a seat loads.

**Deterministic checks before any opinion.** The foreman writes the acceptance ledger as
JSON with one targeted command per checkable item (`factory/ledger.example.json`);
`tools/ledger_check.py` executes it before the auditor or gatekeeper forms a view, and the
task's own check tool runs next. Only items no command can decide are judged by a model.

**Holdout tests the builder never sees.** The auditor writes acceptance tests from the
requirements, aimed first at what the supplied sample tests never ask, and keeps them in
`private/` until it accepts the tier. Then it commits them into the tier's folder, where
they guard every later tier. Reason: the sample tests are a fraction of what is graded, so
building to them is building to the wrong target.

**Fresh-clone release.** The gatekeeper builds and starts every folder from a clean clone,
with no outbound network at run time, under the published caps, repeats every timing test
ten times, runs the task's check tool in its strictest mode, and scans for secrets and
private paths. Reason: the judge clones; a working tree can hide uncommitted files.

**Each tier's folder is that tier's answer.** The next tier starts as a copy of the
released folder. The ledger carries a boundary item per tier, a check that one capability
of the next tier is absent, so no folder answers a later tier.

**No human input after the task.** Nobody asks the human anything. Seats decide from the
requirements, record decisions in the room, and the foreman reports blockers as outcomes.
Every handoff carries the whole task, because a seat only receives the messages that
mention it.

## How it catches and recovers from bad work

| Layer | Catches | What happens next |
|---|---|---|
| Ledger with fixed names copied verbatim | a name graded literally, drifted | foreman holds before audit |
| Ledger coverage check by the auditor | a requirement with no item, a misworded name | foreman amends the ledger before the first packet |
| Packet reproduction | a claim that does not match what the commit does | `REJECT: packet does not reproduce` |
| Deterministic gate and the task's check tool | a failing item, a folder that overshoots its tier | reject with item number, expected, actual |
| Holdout tests | requirements the sample tests never ask | reject with expected versus actual |
| Adversarial sweep | races, replays, torn sequences, malformed input, arithmetic edges, restarts, screen states | new ledger items or a rejection |
| Timing repeats under caps | a test that passes once and fails one run in five | defect, reject |
| Fresh-clone release | uncommitted files, a service that does not start, secrets | release held, routed to the seat that can fix it |
| Foreman recovery | an item rejected three times, a silent seat, a folder held twice | item restated from the requirements, one retry, then recorded as a blocker |

## Measured cost and time

Measured with `tools/spend.py`, which reads each seat's provider session from Band and
sums the tokens in the runtimes' own logs, and with `tools/room_metrics.py` on the room
log. The seats run on subscriptions, so there is no metered price;
tokens are the cost.

Practice run on the event's unscored practice track, four stages, every seat on Claude
Code: 5 h 20 min wall clock, of which the host slept 2 h 29 min, so 2 h 51 min of work and
568 model calls.

| Seat | Model | Input | Cached input | Output |
|---|---|---:|---:|---:|
| foreman | claude-opus-5-5 | 338,685 | 15,325,606 | 74,968 |
| builder | claude-opus-5-5 | 418,971 | 21,812,813 | 116,484 |
| auditor | claude-opus-5-5 | 518,969 | 27,994,993 | 127,984 |
| gatekeeper | claude-opus-5-5 | 297,127 | 15,253,433 | 58,898 |
| total | | 1,573,752 | 80,386,845 | 378,334 |

The builder produced under a third of the output tokens; the seats that verify did most of
the reading. 7 evidence packets, 3 rejections, 1 release held, 5 ledger amendments, 2 of
them from the auditor's coverage check. Every stage claimed 100% of its own suite in the
strictest mode, and every next-stage suite the harness runs failed against the earlier
folder, as it must; an independent re-run after the report agreed.

## What we tried that failed

Two rehearsals on an unrelated domain, a small HTTP service for a community tool library,
and a practice run on the event's practice track each left a rule in the factory.

1. The auditor checked out a commit in the shared working tree, and the gatekeeper then
   committed onto that detached HEAD. Now the auditor reproduces in a temporary worktree,
   nobody but the owner of a path commits it, and every commit names only its own paths.
2. A seat answered a product question put to the human. Now nobody asks the human anything
   after the task is dispatched.
3. The Codex runtime's memory consolidation handed the foreman an unrelated task, which it
   relayed. Now work enters only as the human's task in the room; anything else a runtime
   injects is ignored, not relayed.
4. A queue test passed for the builder and the auditor, then failed one run in five at the
   gate under 1 CPU. Now timing and concurrency tests run ten times under the caps.
5. A ledger ran the full suite for 13 of its 14 items, and the gate took an hour. Now each
   item carries one targeted command and the full suite is one item.
6. A malformed-input test passed only after a 30-second socket timeout. Now a suite whose
   wall clock is out of proportion to its test count is a finding; after the fix the test
   took 0.6 s.
7. One release was held three times on privacy and never on the product: an absolute path
   in a packet, a home directory in captured shell output, an example path in a comment.
   Now committed files carry repository-relative paths only.
8. The first bring-up script ran only on Windows. It is now `tools/factory_up.py`, which
   runs wherever Band Desktop does.
9. The foreman and the auditor ran Codex on a ChatGPT Plus plan. They used 83% of its
   five-hour limit in two and a half hours, and they inherited the operator's own Codex
   setup: personal MCP servers, plugins with browser and desktop control, and environment
   variables that the operator's configuration injects into every shell. Launch flags can
   add Codex settings but not remove them. Every seat now runs Claude Code, whose MCP
   servers and tools the factory sets.
10. In the practice run the host went to sleep for 2 h 29 min in the middle of a release
    check. The band carried on when it woke, but a sleeping host is indistinguishable from
    a stalled band, so the machine is kept awake for the length of a run.
11. A boundary item for a tier whose successor adds no observable capability could not be
    checked; the builder refused to plant a defect to make it checkable, and the foreman
    withdrew the item. Now the ledger records that no boundary item applies.
12. A Windows path in a handoff lost its backslashes to escape processing on the way into
    the room. Paths in messages are written with forward slashes.

The rehearsal transcripts are not published: a runtime brought unrelated personal data into
that room (item 3).

## Limitations

- A seat cannot approve another seat's permission request, so every seat runs in a
  permission mode that needs no approval.
- All four seats share one model family. The auditor's independence rests on what it
  sees and when it writes its tests, not on a different model.
- A seat whose runtime fails a turn, at a usage limit or an outage, posts an error that
  mentions nobody, so the band waits. The factory stays inside measured limits rather than
  recovering from that.
- An evidence packet proves what ran and what it printed, not that it was the right thing
  to run; that judgement is the auditor's, and the auditor is a model.
