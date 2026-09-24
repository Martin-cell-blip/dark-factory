# Rehearsals

The factory ran twice before the build window, on a domain unrelated to either track: a
small HTTP service for a community tool library, with create, list, borrow and return, one
HTML page, no double borrow under concurrency with idempotent replays, and a waiting list.
None of that code is part of this repository.

| Run | Scope | Result | Wall clock | Packets | Holds | First-pass rate |
|---|---|---|---|---|---|---|
| 2026-09-23 | four tiers | four folders released from a fresh clone, offline, under 512 MiB and 1 CPU | 2 h 48 min | 6 | 1 foreman, 1 gate | 0.95 |
| 2026-09-24 | tier 1 again from an empty folder, second-version mandates | released | 8 h 38 min, 5.5 h of it waiting for the human | 2 | 1 auditor, 3 gate | 0.79 |

The figures come from `tools/room_metrics.py` on the room exports. The exports themselves
stay private, because a runtime brought unrelated personal data into the rehearsal room
(item 3 below).

## What the runs caught, and the rule each left in the mandates

1. The auditor checked out a commit in the shared working tree, and the gatekeeper then
   committed its release note onto that detached HEAD. **Rule:** the shared tree belongs to
   the builder; the auditor reproduces in a temporary worktree; the gatekeeper checks in a
   fresh clone and runs no git in the shared tree.
2. The foreman mentioned every seat on a product question, and the auditor answered it.
   **Rule:** product questions mention only the human, and a seat mentioned on one replies
   nothing.
3. The Codex runtime's memory consolidation handed the foreman an unrelated task, which the
   foreman relayed and put on the board. The builder refused it and the human stopped the
   rest. **Rule:** work enters only as the human's task in the room; runtime housekeeping is
   never work. The Codex seats now start with memories off.
4. A queue test passed for the builder and the auditor, then failed about one run in five at
   the gate under 1 CPU. **Rule:** timing and concurrency tests run ten times under the
   published caps, and one failure is a defect.
5. A ledger ran the full suite for 13 of its 14 items; with rule 4 the gate took an hour.
   **Rule:** one targeted command per item, and "the whole suite passes" is one item.
6. A malformed-input test passed only after a 30-second socket timeout: 34 tests took 47 s.
   **Rule:** a suite whose wall clock is out of proportion to its test count is a finding.
   After the fix the suite took 18 s and that test 0.6 s.
7. The gate held one release three times on privacy and never on the product: an absolute
   path in a packet, a home directory inside captured shell output, an example path in a
   comment. **Rule:** committed files carry repository-relative paths only, and the room
   exporter scrubs every string.
8. The builder named a folder `toolshed-tier2` where the human had fixed `toolshed-t2`, and
   the foreman held it before audit. No new rule: this was the literal-names rule working.

One more rule came from the competition's grading text rather than from a run: tier
boundaries, which keep each folder its own tier's answer.
