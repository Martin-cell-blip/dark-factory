# dark-factory

An evidence-gated software factory for BAND Desktop: four coding-agent seats, one that
writes code and three that only verify. Entry for WeAreDevelopers × BAND: Dark Factory,
track pocketful. MIT licence.

## The rule the factory is built on

Nothing crosses a handoff without evidence a second seat can reproduce. Every handoff is an
evidence packet: the commit, the exact commands, their exit codes and output digests. The
receiving seat re-runs it before believing it, and a claim without a packet is returned
unread. The auditor, which judges the builder's work, runs a different model provider from
the builder.

## The band

| Seat | Runtime | Owns | Writes product code |
|---|---|---|---|
| [foreman](mandates/foreman.md) | Codex | acceptance ledger, board, verdicts, questions to the human | no |
| [builder](mandates/builder.md) | Claude Code | implementation, evidence packets | yes, the only one |
| [auditor](mandates/auditor.md) | Codex | reproduction, holdout tests, adversarial sweep | tests only |
| [gatekeeper](mandates/gatekeeper.md) | Claude Code | fresh-clone offline release, caps, secret scan, release note | no |

The mandates are generic: they name no route, field, status code or element id, and
`tools/mandate_lint.py` checks that before every commit. On competition day it runs again
with every fixed name from the spec as an extra forbidden term.

## How work moves

```
human ─task─▶ foreman ─ledger─▶ builder ─packet─▶ auditor ─verdict─▶ foreman ─release request─▶ gatekeeper ─release note─▶ foreman ─▶ human
                                   ▲                  │                                              │
                                   └──── reject: item number, expected vs actual ◀───────────────────┘
```

- Only product questions reach the human, and no seat answers on the human's behalf.
- No handle is hardcoded: each seat looks up who holds the next role at handoff time.
- Delete test: without BAND there is no shared ledger, no packets, no verdicts, no release
  notes and nothing to measure; one agent grades its own work.

## Four checks that make it a factory rather than a transcript

1. **Deterministic gate before any opinion.** The foreman publishes the ledger as JSON with
   one targeted command per checkable item, and `tools/ledger_check.py` runs it before the
   auditor or the gatekeeper judge anything.
2. **Holdout tests.** The auditor writes acceptance tests under `private/` that the builder
   is forbidden to read, and the gatekeeper runs them again at release.
3. **Fresh-clone release.** The gatekeeper builds and starts every folder from a clean clone
   with no network, under the published caps, and repeats every timing-sensitive test ten
   times.
4. **Tier boundaries.** Each tier's ledger carries a check that one capability of the next
   tier is absent, so every folder is its own tier's answer and not a later one.

## Stand it up

Needs Band Desktop signed in (macOS, Windows or Linux), Claude Code and Codex signed in,
Docker, and Python 3.10 or later.

```
python tools/factory_up.py --dry-run    # probe the four runtimes
python tools/factory_up.py --new-room   # create or refresh the seats, open a room
```

`factory/seats.json` is the whole configuration. Post the task in the room, mention the
foreman, and answer only what it asks you. `factory/seats.codex-only.json` runs every seat
on Codex when Claude is unavailable, at the price of a weaker audit.

## Repository

| Path | What |
|---|---|
| `mandates/` | one standing instruction per seat |
| `factory/` | design and mention graph, evidence-packet format, ledger shape, seat configuration, rehearsals |
| `tools/` | bring-up, mandate lint, ledger gate, offline smoke test, secret scan, room export, metrics |
| `AGENTS.md` | seat rules every runtime loads in this repository (`CLAUDE.md` imports it) |
| `stage-1/` … `stage-4/` | the product, one folder per released stage, written by the factory during the build |

The factory was rehearsed twice before the build window on an unrelated domain; what the
runs caught and the rules they left behind are in [`factory/REHEARSAL.md`](factory/REHEARSAL.md).

## Limitations

- A seat cannot approve another seat's permission request; a genuine exception reaches the
  human.
- The seats run host-native with full access to the workspace machine. On Windows, Codex's
  own sandbox cannot reach the local BAND daemon, so it is switched off for the Codex seats.
- An evidence packet proves what ran and what it printed, not that it was the right thing
  to run; that judgement is the auditor's, and the auditor is a model.
- The runtimes do not attribute tokens per seat; wall clock is reported instead.
