# Pocketful stage 4 — how to run it

Payments, requests, splits, an activity feed, atomic net settlements, payment
authorisations (holds and captures), historical balances, statements, payment
corrections, refunds and correction batches over HTTP, plus the browser app at `/`. The service
uses only the Python standard library and serves every script, stylesheet and icon itself;
the image installs nothing else and needs no outbound network at run time. State lives in
memory and is replaced by `POST /_test/reset`.

## Build and start (one command)

From this folder (`stage-4/`), with Docker running:

```sh
docker build -t pocketful-stage-4 . && docker run -d --rm --name pocketful-stage-4 -p 8080:8080 -e PORT=8080 pocketful-stage-4
```

The service listens on `0.0.0.0:$PORT` (default `8080`). It is ready when
`curl http://localhost:8080/health` returns `{"status":"ok"}` (within a second or two).
Open http://localhost:8080/ in a browser to use the app. Stop it with
`docker stop pocketful-stage-4`.

Any other port works the same way, e.g. `-p 9000:9000 -e PORT=9000`.

## Run the tests

The tests are black-box checks against the running container: HTTP checks, and screen
checks that drive Chromium through Playwright. They need, on the host, Python 3.10+,
pytest and Playwright with Chromium:

```sh
pip install pytest playwright && python -m playwright install chromium
```

`tests/acceptance/test_i41.py` moves an export into a second, fresh container on a
different port. Start it next to the first one and point `POCKETFUL_URL_B` at it (that
test fails without it):

```sh
docker run -d --rm --name pocketful-stage-4-b -p 8081:8081 -e PORT=8081 pocketful-stage-4
export POCKETFUL_URL_B=http://localhost:8081
```

Upgrade checks import exports from this team's released earlier services: the carried
`tests/stage2/test_i14.py` and `test_i27.py` need a stage-1 service, `tests/stage3/test_i17.py`
a stage-1 and a stage-2 service, and `tests/stage4/test_i12.py` all three. Build them from
the repository's frozen `stage-1/`, `stage-2/` and `stage-3/` folders, run each on its own
port and point `POCKETFUL_STAGE1_URL`, `POCKETFUL_STAGE2_URL` and `POCKETFUL_STAGE3_URL` at
them (those tests fail without them):

```sh
(cd ../stage-1 && docker build -t pocketful-stage-1 .)
(cd ../stage-2 && docker build -t pocketful-stage-2 .)
(cd ../stage-3 && docker build -t pocketful-stage-3 .)
docker run -d --rm --name pocketful-stage-1 -p 8082:8082 -e PORT=8082 pocketful-stage-1
docker run -d --rm --name pocketful-stage-2 -p 8083:8083 -e PORT=8083 pocketful-stage-2
docker run -d --rm --name pocketful-stage-3 -p 8084:8084 -e PORT=8084 pocketful-stage-3
export POCKETFUL_STAGE1_URL=http://localhost:8082 POCKETFUL_STAGE2_URL=http://localhost:8083
export POCKETFUL_STAGE3_URL=http://localhost:8084
```

```sh
python -m pytest tests -q                              # everything
python -m pytest tests/stage4/test_i08.py -q           # one stage-4 ledger item
POCKETFUL_URL=http://localhost:9000 python -m pytest tests -q   # another address
```

| Folder | What it checks |
|---|---|
| `tests/stage4` | Stage-4 ledger items, one file per item (`test_iNN.py`) |
| `tests/stage3`, `tests/holdout_s3` | Stage 3, carried forward (stage-4 ledger item 1) |
| `tests/stage2`, `tests/holdout_s2` | Stage 2, carried forward (stage-4 ledger item 1) |
| `tests/acceptance`, `tests/holdout` | Stage 1, carried forward (stage-4 ledger item 1) |
| `tests/unit` | Shared rules and hold mechanics, in process (no service needed) |

Every test resets its own fixture through `POST /_test/reset` (on the earlier stages'
services too, for the upgrade checks).

## Without Docker

```sh
PORT=8080 python -m pocketful
```

## Layout

| Path | Responsibility |
|---|---|
| `pocketful/http_api.py` | HTTP transport: routing, bodies, headers, JSON envelope, HTML for browsers |
| `pocketful/service.py` | Stage-1 API operations, each one check-and-act under one lock |
| `pocketful/authorization_api.py` | Authorise, capture, void and list authorisations |
| `pocketful/holds.py` | Authorisation records, per-user held amounts, expiry by the clock, closed_at |
| `pocketful/history.py` | Payment revisions; balances, holds and statements at an instant; the historical overdraft sweep |
| `pocketful/history_api.py` | GET /me with as_of and known_at, GET /statement with snapshots, corrections and revisions |
| `pocketful/corrections.py` | The correction rules and combined funds checks shared by single corrections and batches |
| `pocketful/refund_api.py` | POST /payments/{payment_id}/refunds |
| `pocketful/batch_api.py` | POST /correction-batches |
| `pocketful/state.py` | The state model, the one money guard, fixture and export/import |
| `pocketful/fields.py` | Field and query rules (amount, note, visibility, handles, limits) |
| `pocketful/paging.py` | limit, offset and has_more for every list |
| `pocketful/money.py` | The equal-split rule |
| `pocketful/jsonio.py` | Strict JSON parsing, the canonical form and replay fingerprints |
| `pocketful/passwords.py` | scrypt password hashing |
| `pocketful/clock.py` | RFC 3339 timestamps, strictly increasing |
| `pocketful/web.py` | Serves the app shell and its static files |
| `pocketful/web/` | The browser app: `index.html`, `assets/app.css` and one ES module per concern (`api.js`, `money.js`, `words.js`, `dom.js`, `layout.js`, `wallet.js`, `money-form.js`, `screen-*.js`) |
| `DESIGN.md` | Colour tokens with contrast, type scale, spacing, layouts, every state |
| `DECISIONS.md` | Choices made where the requirements leave room |
