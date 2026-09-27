# dark-factory

Team **dark-factory** (solo), track **pocketful**, WeAreDevelopers × BAND: Dark Factory.
MIT licence.

An evidence-gated software factory for Band Desktop: four seats, one that writes product
code and three that plan, verify and release, and the wallet service it built stage by
stage.

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
