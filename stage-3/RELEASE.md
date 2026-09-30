# Stage 3 release note

- **Commit released:** `9bcc07b26e76f2d203e0d4d3aa167fe670f9ae1e`. It contains the service accepted at 3ec50fb, the builder's test-only packet 4 (8987854), and the auditor's stage-3 holdouts in `tests/holdout_s3`.
- **Folder:** `stage-3/`
- **Date:** 2026-09-29 (UTC)
- **Released by:** gatekeeper
- **Ledger:** `ledger/stage-3.json` at 8954cdb. It has 25 items; 21, 24 and 25 are judged by hand.
- **Upgrade sources:** the frozen `stage-1/` (0976b03) and `stage-2/` (a43756c). Up to 9bcc07b, each folder changed only in its `RELEASE.md`.
- **Service code:** `git diff 3ec50fb 9bcc07b -- stage-3/pocketful stage-3/Dockerfile` is empty.
- **Result:** RELEASED.

All checks except the event harness ran in a fresh `git clone` of the repository, in a temporary
directory, checked out at 9bcc07b. The harness reads the shared repository. When it ran, HEAD was
77298a3, which adds only the stage-4 ledger; `git diff 9bcc07b 77298a3 -- stage-3` is empty. Machine
paths are written as `<repo>` (this repository) and `<kickoff>` (the event's kickoff package), per
decision D4.

## Checks

| # | Check | Command | Exit |
|---|---|---|---|
| 1 | Structure | `git clone <repo> rel && git checkout 9bcc07b`; `find stage-3 -type l`; `git ls-files -s stage-3` (no mode 120000/160000); no nested `.git`, no `.gitmodules`; grep for references outside the folder | 0. No symlinks, submodules or nested repositories. The folder holds `Dockerfile`, `RUN.md`, `DESIGN.md`, `DECISIONS.md`, `pocketful/` and `tests/` (unit, acceptance, holdout, stage2, holdout_s2, stage3, holdout_s3). Only the upgrade tests reach outside the folder, to the frozen stage-1 and stage-2 images, and RUN.md documents that. |
| 2 | Event harness, strict | `python -m harness run --track pocketful --repo <repo> --stage 3 --mode isolated`, run from `<kickoff>` through WSL | 0. Stage 1 passed 147/147, stage 2 passed 35/35 and stage 3 passed 6/6. Stage 4 failed, which is the required result. Run `aa99e4ae7c964898899bfa0abcbe4627`, revision 77298a3, mode isolated. |
| 3a | Build | `docker build` in `stage-3/`, `stage-2/` and `stage-1/` of the clone | 0 / 0 / 0 |
| 3b | Start, capped and offline | `docker network create --internal gk-s3-net`, then four containers, each `docker run -d --network gk-s3-net --cpus 2 --memory 2g --memory-swap 2g -e PORT=<p>`: stage-3 A (8080), stage-3 B (8081), stage-1 (8082), stage-2 (8083) | 0. First `/health` 200 after 1.17 s, 0.67 s, 0.69 s and 0.71 s, all within 60 s. An outbound connection failed with `Errno 101 Network is unreachable`. |
| 4a | Full suite in containers | Runner image = the stage-3 image plus pytest, Playwright and Chromium, plus `tests/`, on the same offline network. Command: `python -m pytest tests -q` with `POCKETFUL_URL`, `POCKETFUL_URL_B`, `POCKETFUL_STAGE1_URL` and `POCKETFUL_STAGE2_URL` set | 0. 1096 passed in 214 s, with no skips. |
| 4b | Thread, timing and screen tests, 10 repeats | Run in this order: `stage2/test_i03, i04, i06, i08–i14, i28, i32`, then `holdout_s2/` (authorizations, idempotency_upgrade, screens, shell_and_product), then stage-1 `acceptance/test_i08, i16, i17, i34` and `holdout/`, then `stage3/test_i04, i12, i15, i17, i18` and `holdout_s3/test_h3_history, test_h3_holds_upgrade`. Repeated 10 times. | `0 0 0 0 0 0 0 0 0 0`, with 427 passed each time. This covers the foreman's request to repeat packet 4's `stage3/test_i15` and `test_i17`. |
| 4c | holdout_s2 order isolation (the stage-2 limitation) | Row 4b runs `holdout_s2` screen modules after `stage2` screen tests in one pytest session. At stage 2 this order gave 49 errors per run. | 0 on all 10 runs. The auditor's fix holds. |
| 5 | Ledger gate | `python tools/ledger_check.py ledger/stage-3.json stage-3`, inside the runner on the offline network | 1: 21 PASS, 1 FAIL, 3 MANUAL. The only FAIL is item 20, `docker: not found`, because the runner has no Docker. |
| 5b | Ledger item 20 on the host | `python tools/ledger_check.py ledger/stage-3.json stage-3 --only 20` | 0. 1 PASS. |
| 6 | Secrets and private data | `git grep -nIE` over the whole tree at 9bcc07b for tokens, private keys, credential literals, user-home and drive paths, WSL mounts, the kickoff package name and personal data. `git log --all -p` for token and key patterns. `git ls-files` for key, cert and env files. | 0 blocking hits. In `stage-3/`, the only matches are the fixture password `"correct horse"` in test helpers (`holdout/holdout_client.py`, `holdout_s2/holdout2_client.py`, `holdout_s2/test_h2_screens.py`, `holdout_s3/holdout3_client.py`). E-mail addresses use test domains only. The tree has no machine paths. |
| 7 | Assets from other hosts | Static scan of `pocketful/web/` for off-host URLs, `@import`, `url(`, `<script src>` and `<link href>` | 0. Every asset is same-origin. The only absolute URL is the SVG namespace, which is never fetched. |

**Ledger gate verdict.** All 22 items that have a check command pass. Twenty-one ran against the
offline, capped containers. Item 20 is a `docker build`, so it ran on the host.

The manual items:

- **21 (harness claims stage 3):** confirmed by check 2.
- **24 (fixed names):** accepted by the auditor in packet 3ec50fb. I did not re-judge it.
- **25 (memory headroom):** confirmed. Peak memory was 198 MiB over the whole suite, against the 1.5 GiB limit (see Resources).

### Event harness, exact output

These are the final lines of the run, quoted exactly except that the report path's machine prefix
is written as `<kickoff>`. The room post quotes it verbatim.

```
highest contiguous stage: 3
claimed stage: 3 on the shipped checks
report: <kickoff>/runs/aa99e4ae7c964898899bfa0abcbe4627/report.json
NOTE: this run only includes a portion of the full tests that are applied before judging; this is meant to provide directional feedback, and ultimately you may not pass the stage with the full set of tests.
```

The folder claims its own tier, stage 3, and the stage 4 suite fails.

## Test count

- **This release:** 1096. The count collected in the container matches the auditor's.
- **Previous released folder:** 924 (stage-2, a43756c).
- **Drop:** none; the count rose by 172. Two tests were retired under ledger item 1, where stage 3 changes the rule, as the foreman stated in the room: `stage2/test_i36` and `holdout_s2::test_statement_absent`.

## Resources

- **Start time:** 1.17 s to the first `/health` 200 under 2 vCPU and 2 GiB with no network.
- **Peak memory over the whole suite (item 25):** 208,097,280 bytes (198 MiB). This is cgroup `memory.peak` on a fresh container after one full 1096-test run, against the 1.5 GiB limit.
- **Peak memory across all runs:** 262,709,248 bytes (251 MiB), over the full suite, 10 repeat runs and the ledger gate. `oom_kill 0`. Resident memory at the end was 152 MiB.

## Known limitations carried into the next tier

1. **Partial harness sample.** The harness ran only a portion of the judge's tests (147 + 35 + 6), as its NOTE line says.
2. **Clock skew allowance.** Packet 4 makes `stage3/test_i15` and `test_i17` read 5 s and 60 s ahead of host time to absorb clock skew between host and container. Here the runner and the service share one Docker kernel clock, so this release does not exercise that margin. A judge host with more skew than that could still fail them.
3. **Tests run beside the service, not in its image.** The service image contains no tests, pytest or Playwright. "Tests in the container" means a runner image layered on the service image, on the same offline network.
4. **Upgrade tests need running services.** They need live stage-1 and stage-2 containers (`POCKETFUL_STAGE1_URL`, `POCKETFUL_STAGE2_URL`) built from the frozen folders.
5. **In-memory state.** State lives in memory and is lost on restart, by design (see `RUN.md`).

## Addendum (2026-09-30): the whole suite, 10 repeats

The auditor saw one unidentified failure in 10 full-suite runs at 9bcc07b: 1095 passed, 1 failed,
with no test name captured. The release checks above ran the full suite only once. To cover that
gap, I rebuilt all four images from the same clone at 9bcc07b and started them offline under the same
caps. I then ran the whole suite 10 times back to back on one service container, with no restart
between runs:

- Command: `python -m pytest tests -q -rfE --tb=long` ×10, in the runner container.
- Exit codes: `0 0 0 0 0 0 0 0 0 0`. Every run had 1096 passed, with no FAILED or ERROR lines.
- Peak memory after all 10 runs: 295,190,528 bytes (282 MiB), `oom_kill 0`.

The failure did not reproduce in 10 runs. Across the gatekeeper's and the auditor's runs together, 1
of 20 full runs failed, and its test is still unknown. This is carried as a known limitation: a
possible intermittent failure somewhere under `tests/`, at about 1 in 20 or less.
