# Stage 4 release note

- **Commit released:** `44c3df81c8b9f008e07ba8f5a5c1574a5ad79178`. It contains:
  - the service at fbed83f;
  - the auditor's retirement of the holdout_s3 refunds-absent test (0347711);
  - evidence files (7ab1d5a, 248d58e);
  - the auditor's stage-4 holdouts in `tests/holdout_s4`.
- **Folder:** `stage-4/`. This is the last stage.
- **Date:** 2026-09-30 (UTC).
- **Released by:** gatekeeper.
- **Ledger:** `ledger/stage-4.json` at 77298a3. It has 18 items. Items 15, 17 and 18 are manual. There is no boundary item, because this is the last stage.
- **Upgrade sources:** the frozen `stage-1/` (0976b03), `stage-2/` (a43756c) and `stage-3/` (9bcc07b). By 44c3df8, each has changed only in its `RELEASE.md`.
- **Service code:** `git diff fbed83f 44c3df8 -- stage-4/pocketful stage-4/Dockerfile` is empty.
- **Result:** RELEASED.

## How the checks ran

Every check except the event harness ran in a fresh `git clone` in a temporary directory, checked
out at 44c3df8. The harness reads the shared repository. When it ran, HEAD was 44c3df8.

Machine paths are written as `<repo>` for this repository and `<kickoff>` for the event's kickoff
package, per decision D4.

## Checks

| # | Check | Command | Exit |
|---|---|---|---|
| 1 | Structure | `git clone <repo> rel && git checkout 44c3df8`; `find stage-4 -type l`; `git ls-files -s stage-4` (no mode 120000/160000); no nested `.git`, no `.gitmodules`; grep for references outside the folder | 0. There are no symlinks, submodules or nested repositories. The folder holds `Dockerfile`, `RUN.md`, `DESIGN.md`, `DECISIONS.md`, `pocketful/` and `tests/`. The `tests/` directory holds `unit`, `acceptance`, `holdout`, `stage2`, `holdout_s2`, `stage3`, `holdout_s3`, `stage4` and `holdout_s4`. The folder reaches nothing outside itself except the frozen stage-1, stage-2 and stage-3 images that the upgrade tests use, and RUN.md documents that. |
| 2 | Event harness, strict | `python -m harness run --track pocketful --repo <repo> --stage 4 --mode isolated`, run from `<kickoff>` through WSL | 0. Stage 1 passed 147/147, stage 2 35/35, stage 3 6/6 and stage 4 5/5. The run is `2059e33f570b4362bed3ae6c3dc298dd`, revision 44c3df8, mode isolated. |
| 3a | Build | `docker build` in `stage-4/`, `stage-3/`, `stage-2/` and `stage-1/` of the clone | 0 / 0 / 0 / 0 |
| 3b | Start, capped and offline | `docker network create --internal gk-s4-net`, then five containers, each started with `docker run -d --network gk-s4-net --cpus 2 --memory 2g --memory-swap 2g -e PORT=<p>`. They are stage-4 A (8080), stage-4 B (8081), stage-1 (8082), stage-2 (8083) and stage-3 (8084). | 0. The first `/health` 200 came after 1.38, 0.71, 0.76, 0.72 and 0.76 s, all within the 60 s limit. An outbound connection failed with `Errno 101 Network is unreachable`. |
| 4 | Whole suite in containers, 10 repeats | The runner image is the stage-4 image plus pytest, Playwright, Chromium and `tests/`, on the same offline network. `python -m pytest tests -q -rfE --tb=long` ran ×10, back to back on the same service containers with no restarts. All five URLs (`POCKETFUL_URL`, `_URL_B`, `_STAGE1_URL`, `_STAGE2_URL`, `_STAGE3_URL`) were set. | `0 0 0 0 0 0 0 0 0 0`. Every run had 1179 passed, no skips, and no FAILED or ERROR lines. The ten whole-suite runs cover every thread, timing, concurrency and screen test ten times. |
| 5 | Ledger gate | `python tools/ledger_check.py ledger/stage-4.json stage-4`, inside the runner on the offline network | 1: 14 PASS, 1 FAIL, 3 MANUAL. The only FAIL is item 14, `docker: not found`, because the runner has no Docker. |
| 5b | Ledger item 14 on the host | `python tools/ledger_check.py ledger/stage-4.json stage-4 --only 14` | 0: 1 PASS. |
| 6 | Secrets and private data | Three scans. `git grep -nIE` over the whole tree at 44c3df8, for tokens, private keys, credential literals, user-home and drive paths, WSL mounts, the kickoff package name and personal data. `git log --all -p` for token and key patterns. `git ls-files` for key, cert and env files. | 0 blocking hits. In `stage-4/`, the only matches are the fixture password `"correct horse"` in five test helpers. E-mail domains are test domains only. There are no machine paths in the tree. |
| 7 | Assets from other hosts | Static scan of `pocketful/web/` for off-host URLs, `@import`, `url(`, `<script src>` and `<link href>` | 0. Every asset is same-origin. The only absolute URL is the SVG namespace, which is never fetched. |

**Ledger gate verdict.** All 15 items with a check command pass. Fourteen ran against the offline,
capped containers. Item 14 is a `docker build`, so it ran on the host. The manual items:

- **Item 15 (harness claims stage 4):** confirmed by check 2.
- **Item 17 (fixed names):** accepted by the auditor in packet 0347711. Not re-judged here.
- **Item 18 (memory headroom):** confirmed. Peak memory over the whole suite was 182 MiB, against a 1.5 GiB limit.

**The open intermittent.** The unnamed intermittent from stages 3 and 4 is a 15 s localhost TCP
connect timeout that never reaches the service. It did not occur in these 10 runs, which produced
no FAILED or ERROR lines. The runs used an internal Docker network with no host port proxy.

### Event harness, exact output

These are the final lines of the run. The machine prefix of the report path is written as
`<kickoff>`, and the room post quotes that line verbatim.

```
highest contiguous stage: 4
claimed stage: 4 on the shipped checks
report: <kickoff>/runs/2059e33f570b4362bed3ae6c3dc298dd/report.json
NOTE: this run only includes a portion of the full tests that are applied before judging; this is meant to provide directional feedback, and ultimately you may not pass the stage with the full set of tests.
```

The folder claims its own tier, stage 4. That is the final stage, so there is no later suite to
fail.

## Test count

- **This release:** 1179. The count collected in the container matches the auditor's.
- **Previous released folder:** 1096 (stage-3, 9bcc07b).
- **Change:** up 83, no drop. Two tests were retired under ledger item 1, where stage 4 changes the rule, as the foreman stated in the room: `stage3/test_i23` and `holdout_s3::test_refunds_absent`.

## Resources

- **Start time:** 1.38 s to the first `/health` 200 under 2 vCPU / 2 GiB with no network.
- **Peak memory over the whole suite (item 18):** 190,959,616 bytes (182 MiB). This is cgroup `memory.peak` on a fresh container after one full 1179-test run.
- **Peak memory across all runs:** 295,194,624 bytes (282 MiB). This covers 10 full suites and the ledger gate. `oom_kill 0`. Resident memory at the end was 122 MiB.

## Known limitations of the final tier

1. **Partial harness sample.** The harness ran only a portion of the judge's tests: 147 + 35 + 6 + 5, as its NOTE line says.
2. **Intermittent localhost connect stall.** The auditor saw about 1 failure in 20 full runs at stage 3 and 1 in 22 at stage 4. Both were 15 s TCP connect timeouts through the host port proxy, not service errors. My 30 full runs on internal networks, 10 at stage 3 and 10 at stage 4, saw none. A judge that goes through host port mapping may still hit it.
3. **Host clock skew.** Stage-3 clock tests keep margins of at least 1 s against clock skew between host and container. Here the runner and the service share one Docker kernel clock, so this release did not exercise those margins.
4. **Where the tests run.** The service image carries no tests, pytest or Playwright. "Tests in the container" means a runner image layered on the service image, on the same offline network.
5. **Upgrade tests need live containers.** The upgrade tests need running stage-1, stage-2 and stage-3 containers built from the frozen folders.
6. **In-memory state.** State lives in memory and is lost on restart, by design (see `RUN.md`).
