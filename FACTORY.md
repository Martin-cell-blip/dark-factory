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
sums the tokens in the runtimes' own logs, and with `tools/room_metrics.py` on
`room.json`. The seats run on one Claude Max subscription, so there is no metered price;
tokens are the cost.

The submitted run, track pocketful: one dispatched message, four stages, 14 h 38 min in
the room, 64 commits by the seats (builder 38, foreman 13, auditor 7, gatekeeper 6), no
question to the human.

| Stage | Wall clock | Packets | Rejections | Tests | Shipped checks, strictest mode |
|---|---|---:|---:|---:|---|
| 1 payments and settlements | 2 h 43 min | 5 | 3 | 547 | 147/147; the stage 2 suite fails |
| 2 wallet screens and holds | 3 h 40 min | 5 | 4 | 924 | and 35/35; the stage 3 suite fails |
| 3 statements and corrections | 3 h 10 min | 4 | 2 | 1,096 | and 6/6; the stage 4 suite fails |
| 4 refunds and batch corrections | 4 h 50 min | 2 | 0 | 1,179 | and 5/5 |

| Seat | Model | Input | Cached input | Output |
|---|---|---:|---:|---:|
| foreman | claude-opus-5-5 | 537,873 | 31,938,363 | 117,765 |
| builder | claude-opus-5-5 | 1,121,139 | 197,643,069 | 556,268 |
| auditor | claude-opus-5-5 | 1,396,711 | 174,808,626 | 300,896 |
| gatekeeper | claude-opus-5-5 | 748,916 | 28,808,249 | 82,057 |
| total | | 3,804,639 | 433,198,307 | 1,056,986 |

On the plan's own meter the account used about 14 points of its weekly limit during the
run and never reached the five-hour limit. The builder wrote about half of the output tokens; the seats that
verify did about half of the reading.

What the verification caught, before any release:

- Before the first packet of each stage, the auditor's coverage check found 19
  requirements the ledgers had missed (8, 8, 3 and 0 by stage), each quoted from the
  specification.
- Stage 1: an amount of 5,000 digits answered 400 where the specification requires 422;
  resetting 1,000 users took 10.3 s; fifty 8 MiB bodies broke the 2 GiB memory cap; a build
  step's output could not be reproduced.
- Stage 2: the loading and error screens rendered without the app shell; hold times mixed
  UTC and local time; closed holds still showed an expiry line.
- Stage 3: a test compared the host clock with the container clock, which ran 34-47 ms
  ahead.
- Stages 3 and 4: about one full run in twenty timed out while connecting, only through
  the auditor's host port mapping; twenty full runs on internal networks passed. It is
  recorded as a limitation, not hidden.

A practice run on the event's practice track, with the same seats, took 2 h 51 min of work
and 80 million cached input tokens; its lessons are items 10-12 below.

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

The submitted run left three more. The mandates stay as they ran, so these are the next
changes, not yet made:

13. Evidence packets crossed ledger amendments: about one round per stage went to a packet
    built against a ledger the auditor had just changed. Next: the builder names the ledger
    commit it built against and the auditor rejects a stale one unread.
14. A builder commit swept up the auditor's uncommitted edits to its holdout tests in the
    shared working tree; the builder took them back out one commit later. Next: the
    auditor edits tests only in its own worktree.
15. One full run in twenty failed to connect, and only through a host port mapping; runs
    on an internal container network never failed. Next: every suite runs on an internal
    network.

The rehearsal transcripts are not published: a runtime brought unrelated personal data into
that room (item 3).

## Limitations

- The shipped checks are a sample of the graded tests: about 21%, 65%, 91% and 84% of
  stages 1-4 were covered only by the ledgers and the auditor's holdout tests.
- State is held in memory only, which the specification allows.
- After release, frozen folders changed only in their `RELEASE.md`: a path scrub in stage
  1 and a test-run addendum in stage 3.
- A seat cannot approve another seat's permission request, so every seat runs in a
  permission mode that needs no approval.
- All four seats share one model family. The auditor's independence rests on what it
  sees and when it writes its tests, not on a different model.
- A seat whose runtime fails a turn, at a usage limit or an outage, posts an error that
  mentions nobody, so the band waits. The factory stays inside measured limits rather than
  recovering from that.
- An evidence packet proves what ran and what it printed, not that it was the right thing
  to run; that judgement is the auditor's, and the auditor is a model.
