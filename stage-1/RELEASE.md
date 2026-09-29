# Stage 1 release note

- **Commit released:** `0976b0304d57945fbe47ba8ca971826faa8d0e7b` (service at 6affcdb, evidence packet 5, auditor holdouts from 9ec7306)
- **Folder:** `stage-1/`
- **Date:** 2026-09-29 (UTC)
- **Released by:** gatekeeper
- **Ledger:** `ledger/stage-1.json` at 5fb6084 (43 items; 36, 37 and 40 are manual)
- **Result:** RELEASED. Every check below exited as required.

All checks except the event harness ran in a fresh `git clone` of the repository into a temporary
directory, checked out at the release commit. The harness reads the shared repository. When it
ran, HEAD was `f8f1680`, which only adds `ledger/stage-2.json`:
`git diff 0976b03 f8f1680 -- stage-1` is empty.

Machine paths are written as `<repo>` (this repository) and `<kickoff>` (the event's kickoff
package), which keeps them out of the repository as decision D4 intends.

## Checks

| # | Check | Command | Exit |
|---|---|---|---|
| 1 | Structure | `git clone <repo> rel && git checkout 0976b03`; `find stage-1 -type l`; `git ls-files -s stage-1` (no mode 120000/160000); no `stage-1/.git`, no `.gitmodules`; grep for references outside the folder | 0 / 0. There are no symlinks, submodules or nested repositories. The folder holds `Dockerfile`, `RUN.md`, `DECISIONS.md`, `pocketful/` and `tests/` (unit, acceptance, holdout). Its only external needs are Python and pytest on the host for the tests. |
| 2 | Event harness, strict | `python -m harness run --track pocketful --repo <repo> --stage 1 --mode isolated`, run from the kickoff package (`<kickoff>`) through WSL | 0. Stage 1 passed 147/147 collected tests. Stage 2 failed, as required. The run is `a38f3f12ce3c41309d50098c94950aa5`, revision f8f1680, mode isolated. |
| 3a | Build | `docker build -t gk-pocketful-s1:0976b03 .` (in `stage-1/`) | 0 |
| 3b | Start, capped and offline | `docker network create --internal gk-s1-net`; `docker run -d --network gk-s1-net --cpus 2 --memory 2g --memory-swap 2g -e PORT=8080 gk-pocketful-s1:0976b03` (plus a second container on PORT=8081 for item 41) | 0. `/health` returned `{"status":"ok"}` 0.72 s after `docker run`. Docker's healthcheck reported healthy at 5.8 s because of its 5 s interval. Both are within the 60 s limit. An outbound connect from inside the container failed with `Errno 101 Network is unreachable`. |
| 4a | Full test suite in containers | A runner image built on the service image, with pytest and `tests/` added and no source changes, ran on the same internal network with the same caps: `python -m pytest tests -q` (`POCKETFUL_URL=http://gk-s1-a:8080`, `POCKETFUL_URL_B=http://gk-s1-b:8081`) | 0. 547 passed in 32.1 s. Four later full runs each exited 0 with 547 passed. |
| 4b | Thread and timing tests, 10 repeats | `pytest tests/acceptance/test_i08.py test_i16.py test_i17.py test_i34.py tests/holdout` ×10 | `0 0 0 0 0 0 0 0 0 0`. Every run had 127 passed. |
| 5 | Ledger gate | `python tools/ledger_check.py ledger/stage-1.json stage-1`, inside the runner container on the internal network | 1 (see the note below). 39 PASS, 1 FAIL, 3 MANUAL. The single FAIL is item 35, `docker: not found`, because the runner container has no Docker. |
| 5b | Ledger item 35 on the host | `python tools/ledger_check.py ledger/stage-1.json stage-1 --only 35` | 0. 1 PASS. |
| 6 | Secrets and private data | `git grep -nIE` for cloud and API tokens, private-key headers, `api_key=`/`secret=`/`password=` literals, user-home and drive paths, WSL mounts, personal e-mail and handles, and SSN-like numbers, over the whole tree at 0976b03; `git log --all -p` for token and key patterns; `git ls-files` for key, cert and env files | 0 blocking hits. The single match is the test password literal `"correct horse"` in `tests/holdout/holdout_client.py:101`, a fixture value for the test service. E-mail domains are limited to test domains (`example.com`, `pocket.test`, `elsewhere.test`, `other.org`, `x.io`, `band.local`). |

**Ledger gate verdict.** Items 1–34, 38, 39 and 41–43 passed against the offline, capped
containers. Item 35 is a `docker build`, so it cannot run inside a container and was run on the
host, where it passed. Taken together, all 40 checked items pass. The manual items:

- **36:** a single `docker build … && docker run …` command is in `RUN.md`, and there is no nested `.git`. Confirmed in check 1.
- **37:** confirmed by check 2.
- **40:** accepted by the auditor in packets afd7f51 and 6affcdb. Not re-judged here.

### Event harness, exact output

The final lines of the run, quoted exactly:

```
highest contiguous stage: 1
claimed stage: 1 on the shipped checks
report: <kickoff>/runs/a38f3f12ce3c41309d50098c94950aa5/report.json
NOTE: this run only includes a portion of the full tests that are applied before judging; this is meant to provide directional feedback, and ultimately you may not pass the stage with the full set of tests.
```

The last two lines are the `report:` line and the `NOTE:` line. The claim line is
`claimed stage: 1 on the shipped checks`. The folder claims its own tier, stage 1.

## Test count

- **This release:** 547, which is 437 builder tests + 1 + 109 auditor holdouts. The count collected in the container matches.
- **Previous released folder:** none. This is the first tier, so there is no drop to explain.

## Resources

- **Start time:** 0.72 s to the first `/health` 200 under 2 vCPU / 2 GiB with no network.
- **Peak memory:** 1,492,205,568 bytes (≈1.39 GiB), read from cgroup `memory.peak`. This is the service container after 1 + 20 focused + 1 ledger + 4 full suite runs. `oom_kill 0`.
- **Resident memory:** 1.26–1.31 GiB after the first run. It stayed flat over four more full runs (1.26 → 1.29 → 1.29 → 1.31 → 1.29 GiB).
- **Idle memory:** a fresh container at idle used 23 MiB.

## Known limitations carried into the next tier

1. **Retained memory.** After the 64 MiB-body and 50-concurrent-request tests (item 34, holdout contract), the Python process keeps about 1.3 GiB resident. The level is stable, not growing, but only about 0.6 GiB of the 2 GiB cap remains. Stage 2 adds load on the same process, so it should bound or release large-body buffers.
2. **The harness sample is partial.** It ran a portion of the judge's tests (147), as its NOTE line says. The full judged set may differ.
3. **Where the tests run.** The folder's tests run from a host or a runner container against the service over HTTP. The service image does not contain pytest or the tests. Running them "in the container" meant an image layered on the service image, on the same offline network.
4. **In-memory state.** State lives in memory and is lost when the container restarts, by design for stage 1 (see `RUN.md`).
