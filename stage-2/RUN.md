# Pocketful stage 1 — how to run it

Payments, requests, splits, an activity feed and atomic net settlements over HTTP.
The service uses only the Python standard library; the image installs nothing else and
needs no outbound network at run time. State lives in memory and is replaced by
`POST /_test/reset`.

## Build and start (one command)

From this folder (`stage-1/`), with Docker running:

```sh
docker build -t pocketful-stage-1 . && docker run -d --rm --name pocketful-stage-1 -p 8080:8080 -e PORT=8080 pocketful-stage-1
```

The service listens on `0.0.0.0:$PORT` (default `8080`). It is ready when
`curl http://localhost:8080/health` returns `{"status":"ok"}` (within a second or two).
Stop it with `docker stop pocketful-stage-1`.

Any other port works the same way, e.g. `-p 9000:9000 -e PORT=9000`.

## Run the tests

The acceptance tests are black-box HTTP checks against the running container, one file per
ledger item (`tests/acceptance/test_iNN.py`); `tests/unit` checks the shared rules in
process. They need Python 3.10+ and pytest on the host (`pip install pytest`).

`test_i41.py` moves an export into a second, fresh container on a different port. Start it
next to the first one and point `POCKETFUL_URL_B` at it (the test fails without it):

```sh
docker run -d --rm --name pocketful-stage-1-b -p 8081:8081 -e PORT=8081 pocketful-stage-1
export POCKETFUL_URL_B=http://localhost:8081
```

```sh
python -m pytest tests -q                              # everything
python -m pytest tests/acceptance/test_i15.py -q       # one ledger item
POCKETFUL_URL=http://localhost:9000 python -m pytest tests -q   # another address
```

Every test resets its own fixture through `POST /_test/reset`.

## Without Docker

```sh
PORT=8080 python -m pocketful
```

## Layout

| Path | Responsibility |
|---|---|
| `pocketful/http_api.py` | HTTP transport: routing, bodies, headers, JSON envelope |
| `pocketful/service.py` | Every API operation, each one check-and-act under one lock |
| `pocketful/state.py` | The state model, the one money guard, fixture and export/import |
| `pocketful/fields.py` | Field and query rules (amount, note, visibility, handles, limits) |
| `pocketful/money.py` | The equal-split rule |
| `pocketful/jsonio.py` | Strict JSON parsing and the canonical form used for replays |
| `pocketful/passwords.py` | scrypt password hashing |
| `pocketful/clock.py` | RFC 3339 timestamps, strictly increasing |
| `DECISIONS.md` | Choices made where the requirements leave room |
