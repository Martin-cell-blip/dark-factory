```
EVIDENCE PACKET (stage 3, packet 3)
commit:      3ec50fb5303c4462ea4b6cf56a32b34f1dffbc94
folder:      stage-3
claims:      1-25 (ledger/stage-3.md at 8954cdb); closes audit R1 (item 18, and so 22); 21, 24, 25 carried from the audit of e828edc
environment: images pocketful-stage-3, pocketful-stage-1 and pocketful-stage-2 (python:3.12-slim, --cpus 2 --memory 2g); stage 3 on 18080 and 18081, stage 1 on 18082, stage 2 on 18083; host Windows 11, Docker 29.2.1, Python 3.13.2, pytest 9.1.1

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
  4. cmd:    for i in 1 2 3 4 5 6 7 8 9 10; do POCKETFUL_URL=http://localhost:18080 python -m pytest tests/stage3/test_i18.py -q -p no:cacheprovider >/dev/null 2>&1; printf '%s ' $?; done; echo
     exit:   0
     digest: 7f38f6393e2d
     tail:   0 0 0 0 0 0 0 0 0 0
  5. cmd:    MSYS_NO_PATHCONV=1 docker exec builder-s3-a sh -c 'grep oom_kill /sys/fs/cgroup/memory.events; test $(cat /sys/fs/cgroup/memory.peak) -lt 1610612736 && echo peak-below-1.5GiB'
     exit:   0
     digest: 3d99d9564076
     tail:   oom_kill 0
             peak-below-1.5GiB
  6. harness (item 21): the service is byte-identical to e828edc (only tests/stage3/test_i18.py
     changed); the auditor's run on e828edc stands: "claimed stage: 3 on the shipped checks".

tests: 1049 run, 1049 passed, 0 failed
changed files since e828edc: stage-3/tests/stage3/test_i18.py
not claimed: none
```

R1: `test_closed_holds_that_arrive_by_seed` bounded a container timestamp (the seeded void's
closed_at, the reset time) with host-clock readings, so it failed whenever the container ran
ahead of the host. The bounds are now the created_at of payments made on the service just
before and just after the reset. The other tests only compare server timestamps with each
other, or host times with at least a second of margin.
