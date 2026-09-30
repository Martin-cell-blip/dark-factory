# dark-factory

Team **dark-factory** (solo), track **pocketful**, WeAreDevelopers × BAND: Dark Factory.
MIT licence.

An evidence-gated software factory for Band Desktop: four seats, one that writes product
code and three that plan, verify and release, and the wallet service it built stage by
stage.

## Result of the submitted run

One human message dispatched all four stages, and the band released every one. Each folder
claims its stage in the harness's strictest mode, and the next stage's suite fails against
it, as it must:

| Folder | Released commit | Shipped checks | Tests in the folder |
|---|---|---|---:|
| `stage-1/` payments and settlements | `0976b03` | 147/147 | 547 |
| `stage-2/` wallet screens and holds | `a43756c` | 147/147, 35/35 | 924 |
| `stage-3/` statements and corrections | `9bcc07b` | 147/147, 35/35, 6/6 | 1,096 |
| `stage-4/` refunds and batch corrections | `44c3df8` | 147/147, 35/35, 6/6, 5/5 | 1,179 |

14 h 38 min, 16 evidence packets, 9 rejections before release, 19 requirements added to the
ledgers by the auditor before the first packet of each stage, no question to the human. Cost per seat, what the
verification caught and what failed are in [`FACTORY.md`](FACTORY.md); the whole
collaboration is in `room.json`.

## How to read this repository

| Path | What it is | Written by |
|---|---|---|
| [`FACTORY.md`](FACTORY.md) | the factory: seats, setup, design choices, measured cost, what failed, how it catches bad work | the human |
| [`mandates/`](mandates/) | one standing instruction per seat, each naming its harness and model | the human |
| `room.json` | the Band room the submitted run happened in, downloaded unchanged | Band |
| `stage-1/` … `stage-4/` | the service, one complete buildable folder per stage, each with a `Dockerfile` and a `RUN.md` | the band |
| [`tools/`](tools/) | bring-up, the ledger gate, spend measurement, room metrics | the human |
| [`factory/`](factory/) | seat configuration, evidence-packet format, ledger shape | the human |
| [`AGENTS.md`](AGENTS.md) | rules every seat loads in this repository (`CLAUDE.md` imports it) | the human |

Everything under `stage-N/` was written by the seats in the room; the git history shows
which seat made each commit (`builder`, `auditor`, `gatekeeper`).

## Stand it up

```
python tools/factory_up.py --new-room
```

Prerequisites and the rest are in [`FACTORY.md`](FACTORY.md).
