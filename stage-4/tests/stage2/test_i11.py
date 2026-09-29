"""Item 11: authorisations expire by the clock, with no request at the deadline."""
import time

import seed
from client import expect
from holdfx import authorize, capture, me, signed_in


def _statuses(client, query=""):
    body = expect(client.get(f"/authorizations{query}"), 200).json()
    return {a["authorization_id"]: a["status"] for a in body["authorizations"]}


def test_expiry_releases_the_hold_on_the_next_read(reset):
    reset(seed.fixture(authorization_ttl_seconds=1))
    ann, ben = signed_in("ann", "ben")
    aid = authorize(ann, "ben", 3000)["authorization_id"]
    assert me(ann)["available"] == 7000
    time.sleep(1.3)
    assert me(ann) == {**me(ann), "total": 10000, "held": 0, "available": 10000}
    assert _statuses(ann) == {aid: "expired"}
    assert _statuses(ann, "?status=expired") == {aid: "expired"}
    assert _statuses(ann, "?status=open") == {}
    assert _statuses(ben, "?status=expired&direction=incoming") == {aid: "expired"}
    capture(ben, aid, {}, 409, "authorization_expired")
    capture(ben, aid, {"amount": 1}, 409, "authorization_expired")


def test_expired_hold_frees_funds_for_a_payment(reset):
    reset(seed.fixture(authorization_ttl_seconds=1))
    [cat] = signed_in("cat")
    authorize(cat, "ann", 500)
    expect(cat.write("/payments", {"to_handle": "ben", "amount": 500}), 409,
           "insufficient_funds")
    time.sleep(1.3)
    expect(cat.write("/payments", {"to_handle": "ben", "amount": 500}), 201)
    assert me(cat) == {**me(cat), "total": 0, "held": 0, "available": 0}


def test_unexpired_holds_stay_open(world):
    aid = authorize(world.ann, "ben", 100)["authorization_id"]
    assert _statuses(world.ann, "?status=open") == {aid: "open"}
    assert _statuses(world.ann, "?status=expired") == {}
