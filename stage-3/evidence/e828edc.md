```
EVIDENCE PACKET (stage 3, packet 2)
commit:      e828edcd11a0c81b4bd6063e29043ebc8aec7adf
folder:      stage-3
claims:      1-25 (ledger/stage-3.md at 8954cdb, amendment 1); 21, 24 and 25 are for the auditor to judge
environment: images pocketful-stage-3, pocketful-stage-1 and pocketful-stage-2 (python:3.12-slim, --cpus 2 --memory 2g); stage 3 on 18080 and 18081, stage 1 on 18082, stage 2 on 18083; host Windows 11, Docker 29.2.1, Python 3.13.2, pytest 9.1.1, Playwright 1.61 with Chromium

commands (bash with pipefail, from stage-3/ of a clean detached worktree at the commit):
  1. cmd:    docker build -q -t pocketful-stage-3 . >/dev/null && (cd ../stage-1 && docker build -q -t pocketful-stage-1 . >/dev/null) && (cd ../stage-2 && docker build -q -t pocketful-stage-2 . >/dev/null) && echo built
     exit:   0
     digest: 586a866f990a
     tail:   built
  2. cmd:    docker run -d --rm --name builder-s3-a --cpus 2 --memory 2g -p 18080:18080 -e PORT=18080 pocketful-stage-3 >/dev/null && docker run -d --rm --name builder-s3-b --cpus 2 --memory 2g -p 18081:18081 -e PORT=18081 pocketful-stage-3 >/dev/null && docker run -d --rm --name builder-s1-up --cpus 2 --memory 2g -p 18082:18082 -e PORT=18082 pocketful-stage-1 >/dev/null && docker run -d --rm --name builder-s2-up --cpus 2 --memory 2g -p 18083:18083 -e PORT=18083 pocketful-stage-2 >/dev/null && sleep 3 && for p in 18080 18081 18082 18083; do curl -s http://localhost:$p/health; done
     exit:   0
     digest: 88320a170daf
     tail:   {"status":"ok"}{"status":"ok"}{"status":"ok"}{"status":"ok"}
  3. cmd:    POCKETFUL_URL=http://localhost:18080 POCKETFUL_URL_B=http://localhost:18081 POCKETFUL_STAGE1_URL=http://localhost:18082 POCKETFUL_STAGE2_URL=http://localhost:18083 python -m pytest tests -q -p no:cacheprovider 2>&1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   0
     digest: d8f91987cb12
     tail:   .........................................                                [100%]
             1049 passed
  4. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/stage3/test_i17.py -q -p no:cacheprovider 2>&1 | tail -1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   1
     digest: 2b7985bceaaf
     tail:   2 failed, 1 passed   (the stage-1 and stage-2 upgrade checks fail, never skip, without their URLs)
  5. cmd:    MSYS_NO_PATHCONV=1 docker exec builder-s3-a sh -c 'grep oom_kill /sys/fs/cgroup/memory.events; test $(cat /sys/fs/cgroup/memory.peak) -lt 1610612736 && echo peak-below-1.5GiB'
     exit:   0
     digest: 3d99d9564076
     tail:   oom_kill 0
             peak-below-1.5GiB
     (memory.peak after the whole suite: 228110336 bytes, about 218 MiB)
  6. cmd:    (from the kickoff package) .venv/Scripts/python -m harness run --track pocketful --repo <worktree at the commit> --stage 3
     exit:   0
     digest: n/a (temp path and run id)
     tail:   highest contiguous stage: 3
             claimed stage: 3 on the shipped checks
             (stages 1, 2 and 3 pass; stage 4 fails as required)

tests: 1049 run, 1049 passed, 0 failed (includes the auditor's holdout_s2 at 25d4da7)
changed files since 126b64f: stage-3/DECISIONS.md (B29), stage-3/pocketful/{history.py,holds.py,state.py},
  stage-3/tests/stage3/{sources.py,test_i11.py,test_i17.py,test_i18.py}
not claimed: none
```

## Amendment 1

- **S3-D8**: `State._settle_closed` gives every closed authorisation that arrives by seed or
  import a closed_at (latest capture payment, expires_at, or the recorded void time, else the
  reset or import time). Seeded closed ones, and imported ones whose close time the export
  did not keep (stage-2 voids), hold nothing historically (`holds.without_history`, exported
  as `authorizations_without_history`). Tests: `test_i18.py::test_closed_holds_that_arrive_by_seed`,
  `test_i17.py::test_a_stage_two_export` (an imported void).
- **Item 11**: `test_i11.py::test_each_revision_has_exactly_the_correction_fields`.
- **Item 1**: the retired boundary tests are gone (`tests/stage2/test_i36.py` by me in edc41e7,
  `holdout_s2::test_statement_absent` by the auditor in 25d4da7). The authorization shape in
  `tests/stage2/test_i04.py` gains closed_at; `tests/unit/test_holds.py` takes close times.
