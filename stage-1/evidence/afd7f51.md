```
EVIDENCE PACKET (packet 4)
commit:      afd7f51920e1015858f733198622f83a08cca06e
folder:      stage-1
claims:      1-43 (ledger/stage-1.md at 5fb6084, amendment 4); closes audit R4b on item 34
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
     digest: bf4cf7f46ab3
     tail:   ........................................................................ [ 98%]
             .....                                                                    [100%]
             437 passed
  4. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/acceptance/test_i05.py tests/acceptance/test_i34.py -q -p no:cacheprovider 2>&1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   0
     digest: ee5af023f583
     tail:   ...........................                                              [100%]
             27 passed
  5. cmd:    POCKETFUL_URL=http://localhost:18080 python -m pytest tests/acceptance/test_i41.py -q -p no:cacheprovider 2>&1 | tail -1 | sed -E 's/ in [0-9.]+s.*//'
     exit:   1
     digest: 882d2f91549d
     tail:   1 error   (item 41 fails, never skips, without POCKETFUL_URL_B)
  6. cmd:    (from the kickoff package) .venv/Scripts/python -m harness run --track pocketful --repo <worktree at the commit> --stage 1
     exit:   0
     digest: n/a (output names a temp path and a run id)
     tail:   highest contiguous stage: 1
             claimed stage: 1 on the shipped checks
             (stage 1: pass, 147 passed; stage 2: fail, as required; then the tool's fixed NOTE line)

tests: 437 run, 437 passed, 0 failed
changed files since bf911c3: stage-1/DECISIONS.md (B13), stage-1/pocketful/{http_api,jsonio,service}.py,
  stage-1/tests/acceptance/test_i34.py
not claimed: none
```

Item 34 tests added (test_i34.py), run under --cpus 2 --memory 2g:
- `test_api_bodies_above_one_mib_are_refused_with_the_envelope`: a 1 MiB + 1 byte payment is 413 `payload_too_large`, nothing moves.
- `test_fifty_concurrent_maximal_api_bodies_within_five_seconds`: 50 concurrent POST /payments, each exactly 1048576 bytes with an ignored array field of about 524k zeros; all 201, each answered within 5 s (the whole burst takes about 2 s; peak memory seen about 250 MiB).
- `test_thirty_mib_import_is_accepted`: a 10000-user fixture exports to more than 30 MiB and imports unchanged with 204.
