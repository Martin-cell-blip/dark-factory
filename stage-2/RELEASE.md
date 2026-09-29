# Stage 2 release note

- **Commit released:** `a43756c4ff14db39a2ef6537be458f8012fcac0d` (the service at ca8c807, packet 5 evidence from 12d74f4, and the auditor's stage-2 holdouts in `tests/holdout_s2`)
- **Folder:** `stage-2/`
- **Date:** 2026-09-29 (UTC)
- **Released by:** gatekeeper
- **Ledger:** `ledger/stage-2.json` at 06bd560 (38 items; 32, 34, 37 and 38 are manual)
- **Upgrade source:** `stage-1/` as released at 0976b03. Between 0976b03 and a43756c, `stage-1/` changed only in its `RELEASE.md`.
- **Result:** RELEASED.

All checks except the event harness ran in a fresh `git clone` of the repository into a temporary
directory, checked out at a43756c. The harness reads the shared repository. When it ran, HEAD was
`f6f5c29`, and `git diff a43756c f6f5c29 -- stage-2` is empty. The commits in between are the
stage-3 ledger and a path redaction in `stage-1/RELEASE.md`.

Machine paths are written as `<repo>` (this repository) and `<kickoff>` (the event's kickoff
package), per decision D4.

## Checks

| # | Check | Command | Exit |
|---|---|---|---|
| 1 | Structure | `git clone <repo> rel && git checkout a43756c`; `find stage-2 -type l`; `git ls-files -s stage-2` (no mode 120000/160000); no nested `.git`, no `.gitmodules`; grep for references outside the folder | 0. Clean on every point. The folder holds `Dockerfile`, `RUN.md`, `DESIGN.md`, `DECISIONS.md`, `pocketful/` (including `web/`) and `tests/` (unit, acceptance, holdout, stage2, holdout_s2). The only thing it needs from outside itself is the frozen `stage-1/` image, and only for the upgrade tests, as RUN.md documents. |
| 2 | Event harness, strict | `python -m harness run --track pocketful --repo <repo> --stage 2 --mode isolated`, run from `<kickoff>` through WSL | 0. Stage 1 passed 147/147, stage 2 passed 35/35, and stage 3 failed, as required. The run is `35e115452cd2434f83df9b77ab9836a7`, revision f6f5c29, mode isolated. |
| 3a | Build | `docker build -t gk-pocketful-s2:a43756c .` in `stage-2/`; `docker build -t gk-pocketful-s1:0976b03 .` in `stage-1/` | 0 / 0 |
| 3b | Start, capped and offline | `docker network create --internal gk-s2-net`; three containers, each started with `docker run -d --network gk-s2-net --cpus 2 --memory 2g --memory-swap 2g -e PORT=<p>`: stage-2 A (8080), stage-2 B (8081) and stage-1 (8082) | 0. First `/health` 200 after 1.11 s (A), 0.69 s (B) and 0.67 s (stage-1), all within 60 s. An outbound connect from inside the container failed with `Errno 101 Network is unreachable`. |
| 4a | Full suite in containers | A runner image on the stage-2 image, adding pytest, Playwright, Chromium and `tests/`, on the same offline network: `python -m pytest tests -q`, with `POCKETFUL_URL`, `POCKETFUL_URL_B` and `POCKETFUL_STAGE1_URL` pointing at the three containers | 0. 924 passed in 204 s, with no skips. |
| 4b | Thread, timing and screen tests, 10 repeats | `pytest` on stage-1 `acceptance/test_i08, i16, i17, i34` and `holdout/`; `holdout_s2/` (authorizations, idempotency_upgrade, screens, shell_and_product); `stage2/test_i03, i04, i06, i08–i14, i28, i32`. Repeated ×10. | `0 0 0 0 0 0 0 0 0 0`. Each run had 343 passed. |
| 5 | Ledger gate | `python tools/ledger_check.py ledger/stage-2.json stage-2`, inside the runner on the offline network | 1: 33 PASS, 1 FAIL, 4 MANUAL. The single FAIL is item 33, `docker: not found`, because the runner has no Docker. |
| 5b | Ledger item 33 on the host | `python tools/ledger_check.py ledger/stage-2.json stage-2 --only 33` | 0. 1 PASS. |
| 6 | Secrets and private data | `git grep -nIE` over the whole tree at a43756c for tokens, private keys, credential literals, user-home and drive paths, WSL mounts and personal data; `git log --all -p` for token and key patterns; `git ls-files` for key, cert and env files | 0 blocking hits in `stage-2/`. See the note below. |
| 7 | Assets from other hosts | Static scan of `pocketful/web/` for off-host URLs, `@import`, `url(`, `<script src>` and `<link href>`; ledger item 31 in a browser | 0. Every asset is same-origin (`/assets/app.css`, `/assets/app.js`, `/assets/icon.svg`). The only absolute URL is the SVG namespace `http://www.w3.org/2000/svg`, which is never fetched. Item 31 passed. |

**Ledger gate verdict.** All 34 items with a check command pass: 33 ran against the offline, capped
containers, and item 33, a `docker build`, passed on the host. The four manual items:

- **32 (product quality):** accepted by the auditor in packet ca8c807. Not re-judged here.
- **34 (harness claims stage 2):** confirmed by check 2.
- **37 (fixed names and maintainable code):** accepted by the auditor in packet ca8c807. Not re-judged here.
- **38 (memory headroom):** confirmed. Peak was 156 MiB over the whole suite, against a 1.5 GiB limit (see Resources).

**Secrets note.** In `stage-2/`, the only credential-like matches are the fixture password
`"correct horse"` in three test helpers (`holdout_client.py:101`, `holdout2_client.py:107`,
`test_h2_screens.py:47`). E-mail domains are test domains only.

Elsewhere in the repository, the scan found machine paths in my own `stage-1/RELEASE.md`, which I
wrote into df3eecd. I replaced them with placeholders in f6f5c29 before this release. They remain in
the history of df3eecd. They are paths, not credentials.

### Event harness, exact output

The final lines of the run. The report path's machine prefix is written as `<kickoff>`; the lines
are quoted exactly, including that path, in the room post.

```
highest contiguous stage: 2
claimed stage: 2 on the shipped checks
report: <kickoff>/runs/35e115452cd2434f83df9b77ab9836a7/report.json
NOTE: this run only includes a portion of the full tests that are applied before judging; this is meant to provide directional feedback, and ultimately you may not pass the stage with the full set of tests.
```

The claim line is `claimed stage: 2 on the shipped checks`. The folder claims its own tier,
stage 2, and the stage 3 suite fails.

## Test count

- **This release:** 924, which is 816 builder tests + 108 holdouts. The count collected in the container matches.
- **Previous released folder:** 547 (stage-1, 0976b03).
- **Drop:** none. The count rose by 377. Two stage-1 boundary tests were retired under ledger item 1, where stage 2 changes the rule. The foreman stated this in the room.

## Resources

- **Start time:** 1.11 s to the first `/health` 200 under 2 vCPU / 2 GiB with no network.
- **Peak memory over the whole suite (item 38):** 163,467,264 bytes (156 MiB), from cgroup `memory.peak` on a fresh container after one full 924-test run. The limit is 1.5 GiB.
- **Peak memory after all runs:** 271,503,360 bytes (259 MiB). This covers the full suite, 20 repeat runs and the ledger gate. `oom_kill 0`.
- **Resident memory at the end:** 100 MiB. `MALLOC_ARENA_MAX=2` fixed the 1.3 GiB retention from stage 1.

## Known limitations carried into the next tier

1. **Test isolation (holdouts).** Keep `tests/holdout_s2` screen modules ahead of the `tests/stage2` screen tests. `tests/stage2/conftest.py` opens a session-scoped Playwright browser. When `tests/holdout_s2/test_h2_screens.py` or `test_h2_shell_and_product.py` run after a stage2 screen test in the same pytest session, their module-scoped `sync_playwright()` errors ("It looks like you are using Playwright Sync API inside the asyncio loop"). That was 49 errors per run, and every other test still passed. The canonical `pytest tests` order runs holdout_s2 first, so the full suite and every ledger command pass. A stage-3 harness or reordered run would hit it.
2. **The harness sample is partial.** The harness ran a portion of the judge's tests (147 + 35), as its NOTE line says.
3. **Where the tests run.** The tests, pytest and Playwright are not in the service image. Running them "in the container" meant a runner image layered on the service image, on the same offline network.
4. **Upgrade tests.** They need a running stage-1 container (`POCKETFUL_STAGE1_URL`) built from the frozen `stage-1/`.
5. **In-memory state.** State lives in memory and is lost when the container restarts, by design (see `RUN.md`).
