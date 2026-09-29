# Pocketful stage 2 — how to run it

Payments, requests, splits, an activity feed, atomic net settlements and payment
authorisations (holds and captures) over HTTP, plus the browser app at `/`. The service
uses only the Python standard library and serves every script, stylesheet and icon itself;
the image installs nothing else and needs no outbound network at run time. State lives in
memory and is replaced by `POST /_test/reset`.

## Build and start (one command)

From this folder (`stage-2/`), with Docker running:

```sh
docker build -t pocketful-stage-2 . && docker run -d --rm --name pocketful-stage-2 -p 8080:8080 -e PORT=8080 pocketful-stage-2
```

The service listens on `0.0.0.0:$PORT` (default `8080`). It is ready when
`curl http://localhost:8080/health` returns `{"status":"ok"}` (within a second or two).
Open http://localhost:8080/ in a browser to use the app. Stop it with
`docker stop pocketful-stage-2`.

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
docker run -d --rm --name pocketful-stage-2-b -p 8081:8081 -e PORT=8081 pocketful-stage-2
export POCKETFUL_URL_B=http://localhost:8081
```

`tests/stage2/test_i14.py` and `test_i27.py` upgrade from this team's released stage-1
service: they build a state on it, export it and import it here. Build the stage-1 image
from the repository's `stage-1/` folder (release commit 0976b03), run it on its own port and
point `POCKETFUL_STAGE1_URL` at it (those tests fail without it):

```sh
(cd ../stage-1 && docker build -t pocketful-stage-1 .)
docker run -d --rm --name pocketful-stage-1 -p 8082:8082 -e PORT=8082 pocketful-stage-1
export POCKETFUL_STAGE1_URL=http://localhost:8082
```

```sh
python -m pytest tests -q                              # everything
python -m pytest tests/stage2/test_i18.py -q           # one stage-2 ledger item
POCKETFUL_URL=http://localhost:9000 python -m pytest tests -q   # another address
```

| Folder | What it checks |
|---|---|
| `tests/stage2` | Stage-2 ledger items, one file per item (`test_iNN.py`) |
| `tests/acceptance`, `tests/holdout` | Stage 1, carried forward (stage-2 ledger item 1) |
| `tests/unit` | Shared rules and hold mechanics, in process (no service needed) |

Every test resets its own fixture through `POST /_test/reset` (on the stage-1 service too,
for items 14 and 27).

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
| `pocketful/holds.py` | Authorisation records, per-user held amounts, expiry by the clock |
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
