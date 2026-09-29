"""Item 14: stage-1 exports import unchanged; stage-2 export/import round-trips holds."""
import json
from pathlib import Path

import seed
from client import Client, expect, new_key, request
from holdfx import authorize, capture, me, signed_in

STAGE1 = json.loads((Path(__file__).resolve().parent / "upgrade" / "stage1_export.json")
                    .read_text(encoding="utf-8"))


def _import(document):
    return expect(request("POST", "/_test/import", document, timeout=15), 204)


def test_a_stage_one_export_imports_unchanged(reset):
    reset(seed.fixture(users=[seed.user("zed", 5)]))
    _import(STAGE1["export"])
    ann, ben = Client(STAGE1["tokens"]["ann"]), Client(STAGE1["tokens"]["ben"])
    for name, client in (("ann", ann), ("ben", ben)):
        body = me(client)
        assert body["total"] == body["balance"] == body["available"] == STAGE1["balances"][name]
        assert body["held"] == 0
    expect(request("POST", "/auth/login", {"email": "cat@pocket.test",
                                           "password": seed.PASSWORD}), 200)
    paid = STAGE1["payment"]
    replay = expect(ann.post("/payments", paid["body"], key=paid["key"]), 200).json()
    assert replay == paid["response"]
    assert me(ann)["total"] == STAGE1["balances"]["ann"]
    feed = {p["payment_id"]: p for p in expect(ben.get("/activity"), 200).json()["payments"]}
    assert paid["response"]["payment_id"] in feed
    assert all(p["authorization_id"] is None for p in feed.values())
    assert expect(ann.get("/authorizations"), 200).json()["authorizations"] == []
    rid = STAGE1["pending_request_id"]
    expect(ann.write(f"/requests/{rid}/pay", {}), 201)
    failed = STAGE1["failed"]
    expect(ben.post("/payments", {**failed["body"], "amount": 1}, key=failed["key"]), 201)


def test_stage_two_round_trip_keeps_holds_captures_and_replays(reset):
    reset(seed.fixture(authorization_ttl_seconds=3600))
    ann, ben = signed_in("ann", "ben")
    key = new_key()
    body = {"to_handle": "ben", "amount": 3000, "note": "deposit"}
    created = expect(ann.post("/authorizations", body, key=key), 201).json()
    aid = created["authorization_id"]
    capture_key = new_key()
    path = f"/authorizations/{aid}/capture"
    captured = expect(ben.post(path, {"amount": 1000, "final": False}, key=capture_key),
                      201).json()
    gone = authorize(ann, "ben", 200)["authorization_id"]
    expect(ann.post(f"/authorizations/{gone}/void"), 200)
    before = (me(ann), me(ben), expect(ann.get("/authorizations"), 200).json())
    document = expect(request("GET", "/_test/export"), 200).json()
    reset(seed.fixture(users=[seed.user("zed", 5)]))
    _import(document)
    assert (me(ann), me(ben), expect(ann.get("/authorizations"), 200).json()) == before
    assert expect(ann.post("/authorizations", body, key=key), 200).json() == created
    assert expect(ben.post(path, {"amount": 1000, "final": False}, key=capture_key),
                  200).json() == captured
    capture(ben, aid, {"amount": 2000})
    assert me(ann) == {**me(ann), "total": 7000, "held": 0, "available": 7000}
    _import(document)
    assert (me(ann), me(ben)) == before[:2], "import replaces; repeating it restores"


def test_clock_expiry_survives_a_round_trip(reset):
    import time
    reset(seed.fixture(authorization_ttl_seconds=1))
    ann, ben = signed_in("ann", "ben")
    aid = authorize(ann, "ben", 400)["authorization_id"]
    time.sleep(1.3)
    document = expect(request("GET", "/_test/export"), 200).json()
    _import(document)
    capture(ben, aid, {}, 409, "authorization_expired")
    assert me(ann)["held"] == 0


def test_stage_one_replays_are_returned_as_first_stored(reset):
    reset(seed.fixture())
    _import(STAGE1["export"])
    ann = Client(STAGE1["tokens"]["ann"])
    paid = STAGE1["payment"]
    replay = expect(ann.post("/payments", paid["body"], key=paid["key"]), 200)
    assert replay.json() == paid["response"]
    assert "authorization_id" not in replay.json(), "S2-D8: stored responses are not rewritten"
