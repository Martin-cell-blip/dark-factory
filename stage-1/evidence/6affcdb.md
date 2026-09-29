```
EVIDENCE PACKET (packet 5)
commit:      6affcdbf958c9737bac1136f1c8016bc947a49cb
folder:      stage-1
claims:      10, 34 (follow-up F1), with 1-43 carried at ledger 5fb6084
environment: image pocketful-stage-1 (python:3.12-slim, --cpus 2 --memory 2g), two instances on ports 18080 and 18081; host Windows 11, Docker 29.2.1, Python 3.13.2, pytest 9.1.1

commands (bash with pipefail, from stage-1/ of a clean detached worktree at the commit):
  1. cmd:    docker build -q -t pocketful-stage-1 . >/dev/null && echo built
     exit:   0
     digest: 586a866f990a
     tail:   built
  2. cmd:    docker run -d --rm --name builder-s1-a --cpus 2 --memory 2g -p 18080:18080 -e PORT=18080 pocketful-stage-1 >/dev/null && docker run -d --rm --name builder-s1-b --cpus 2 --memory 2g -p 18081:18081 -e PORT=18081 pocketful-stage-1 >/dev/null && sleep 3 && curl -s http://localhost:18080/health && curl -s http://localhost:18081/health
     exit:   0
     digest: 8c776a63809a
     tail:   {"status":"ok"}{"status":"ok"}
  3. cmd:    POCKETFUL_URL=http://localhost:18080 POCKETFUL_URL_B=http://localhost:18081 python -m pytest tests -q -p no:cacheprovider 2>&1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   0
     digest: 1f3f4d8d4735
     tail:   ........................................................................ [ 92%]
             ...........................................                              [100%]
             547 passed
  4. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/acceptance/test_i10.py tests/acceptance/test_i34.py -q -p no:cacheprovider 2>&1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   0
     digest: 376d15aea8c2
     tail:   ........                                                                 [100%]
             8 passed
  5. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/acceptance/test_i41.py -q -p no:cacheprovider 2>&1 | tail -1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   1
     digest: 882d2f91549d
     tail:   1 error   (item 41 fails, never skips, without POCKETFUL_URL_B)
  6. cmd:    (from the kickoff package) .venv/Scripts/python -m harness run --track pocketful --repo <worktree at the commit> --stage 1
     exit:   0
     digest: n/a (output names a temp path and a run id)
     tail:   highest contiguous stage: 1
             claimed stage: 1 on the shipped checks
             (stage 1: pass; stage 2: fail, as required; then the tool's fixed NOTE line)

tests: 547 run, 547 passed, 0 failed (437 builder tests + 1 new + 109 auditor holdouts from 9ec7306)
changed files since afd7f51: stage-1/pocketful/state.py, stage-1/DECISIONS.md (B11 wording, B12),
  stage-1/tests/acceptance/{test_i10,test_i34}.py
not claimed: none
```

- F1: `_hash_all` hashes every seeded password separately with its own random salt
  (in parallel); `test_i10.py::test_users_sharing_a_password_get_different_hashes`
  resets three users with one password and finds three different hashes in the export.
- 1000-user reset (distinct passwords): 2.89-3.36 s over 5 runs under the caps (D7: 5 s).
- `test_i34.py::test_thirty_mib_import_is_accepted` now builds its 30 MiB state from 1000
  users with 32000-character names, since 10000 per-user hashes would exceed the 10 s
  reset limit; the export is still over 30 MiB and imports unchanged.
- B11 wording now matches the parser (an oversized integer is not a number to the field
  rules); documentation only.
