```
EVIDENCE PACKET (stage 2, packet 4)
commit:      d0ae2d1d7f6c73a5ca14efe1c81b929cbc4974b1
folder:      stage-2
claims:      1-38 (ledger/stage-2.md at 06bd560); closes audit R1 (item 32); 32, 34, 37 and 38 are for the auditor to judge
environment: images pocketful-stage-2 and pocketful-stage-1 (python:3.12-slim, --cpus 2 --memory 2g), stage 2 on 18080 and 18081, stage 1 on 18082; host Windows 11, Docker 29.2.1, Python 3.13.2, pytest 9.1.1, Playwright 1.61 with Chromium

commands (bash with pipefail, from stage-2/ of a clean detached worktree at the commit):
  1. cmd:    docker build -q -t pocketful-stage-2 . >/dev/null && (cd ../stage-1 && docker build -q -t pocketful-stage-1 . >/dev/null) && echo built
     exit:   0
     digest: 586a866f990a
     tail:   built
  2. cmd:    docker run -d --rm --name builder-s2-a --cpus 2 --memory 2g -p 18080:18080 -e PORT=18080 pocketful-stage-2 >/dev/null && docker run -d --rm --name builder-s2-b --cpus 2 --memory 2g -p 18081:18081 -e PORT=18081 pocketful-stage-2 >/dev/null && docker run -d --rm --name builder-s1-up --cpus 2 --memory 2g -p 18082:18082 -e PORT=18082 pocketful-stage-1 >/dev/null && sleep 3 && curl -s http://localhost:18080/health && curl -s http://localhost:18081/health && curl -s http://localhost:18082/health
     exit:   0
     digest: 3a48edb7cdc4
     tail:   {"status":"ok"}{"status":"ok"}{"status":"ok"}
  3. cmd:    POCKETFUL_URL=http://localhost:18080 POCKETFUL_URL_B=http://localhost:18081 POCKETFUL_STAGE1_URL=http://localhost:18082 python -m pytest tests -q -p no:cacheprovider 2>&1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   0
     digest: 8d90a58ab444
     tail:   ........................................................................ [ 97%]
             .......................                                                  [100%]
             815 passed
  4. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/stage2/test_i14.py tests/stage2/test_i27.py -q -p no:cacheprovider 2>&1 | tail -1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   1
     digest: 52a22065cf74
     tail:   2 passed, 4 errors   (upgrade tests fail, never skip, without POCKETFUL_STAGE1_URL)
  5. cmd:    MSYS_NO_PATHCONV=1 docker exec builder-s2-a sh -c 'grep oom_kill /sys/fs/cgroup/memory.events; test $(cat /sys/fs/cgroup/memory.peak) -lt 1610612736 && echo peak-below-1.5GiB'
     exit:   0
     digest: 3d99d9564076
     tail:   oom_kill 0
             peak-below-1.5GiB
     (memory.peak after the whole suite: 178360320 bytes, about 170 MiB)
  6. cmd:    (from the kickoff package) .venv/Scripts/python -m harness run --track pocketful --repo <worktree at the commit> --stage 2
     exit:   0
     digest: n/a (temp path and run id)
     tail:   highest contiguous stage: 2
             claimed stage: 2 on the shipped checks
             (stage 1 pass; stage 2 pass; stage 3 fail, as required; then report and NOTE lines)

tests: 815 run, 815 passed, 0 failed
changed files since f19be05: stage-2/DESIGN.md, stage-2/pocketful/web/assets/{app.js,layout.js,app.css,words.js,screen-home.js,screen-authorizations.js},
  new stage-2/tests/stage2/test_i32.py
not claimed: none
```

## R1 (item 32)

- `app.js` renders the top bar (brand, navigation, Log out) and card-shaped skeletons before
  GET /me answers; `current-user` fills in when it lands (`layout.js` `topbar(..., {pending})`,
  `loadingScreen()`).
- When GET /me cannot be reached, the error card with Try again sits inside that shell.
- `tests/stage2/test_i32.py` holds GET /me back on every signed-in route and checks the nav,
  Log out and skeleton cards, then aborts it and checks the error inside the shell.

## Audit notes also addressed

- (a)/(b) Holds show one wording in local time, "Expires 30 Sept 2026, 03:18 (in 2 h)" or
  "Expired …", beside the exact RFC 3339 `authorization-expires-{id}` text.
- (c) Home on phones has a "Jump to your activity" link under the wallet (hidden on desktop).
