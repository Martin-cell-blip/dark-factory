"""Item 3: the stage-2 fixture (authorization_ttl_seconds and authorizations)."""
from datetime import datetime

import pytest

import seed
from client import expect, request
from holdfx import authorize, me, seeded_hold, signed_in


def test_ttl_defaults_to_600(reset):
    reset(seed.fixture())
    [ann] = signed_in("ann")
    body = authorize(ann, "ben", 100)
    created = datetime.fromisoformat(body["created_at"])
    assert (datetime.fromisoformat(body["expires_at"]) - created).total_seconds() == 600


def test_ttl_applies_when_supplied(reset):
    reset(seed.fixture(authorization_ttl_seconds=90))
    [ann] = signed_in("ann")
    body = authorize(ann, "ben", 100)
    delta = datetime.fromisoformat(body["expires_at"]) - datetime.fromisoformat(body["created_at"])
    assert delta.total_seconds() == 90


@pytest.mark.parametrize("ttl", [0, -5, 1.5, "600", True, None, []])
def test_ttl_must_be_a_positive_integer(reset, ttl):
    reset(seed.fixture())
    [ann] = signed_in("ann")
    expect(request("POST", "/_test/reset", seed.fixture(authorization_ttl_seconds=ttl)),
           422, "validation_failed")
    assert me(ann)["total"] == 10000, "a refused reset changes nothing"


def test_seeded_holds_are_reflected_immediately(reset):
    reset(seed.fixture(authorizations=[
        seeded_hold("a_open", "ann", "ben", 2000, note="deposit", visibility="private"),
        seeded_hold("a_done", "ann", "ben", 300, status="captured"),
        seeded_hold("a_void", "ben", "ann", 400, status="voided"),
        seeded_hold("a_old", "ann", "cat", 700, status="expired", hours=-2),
        seeded_hold("a_late", "ann", "cat", 900, status="open", hours=-2),
    ]))
    ann, ben = signed_in("ann", "ben")
    body = me(ann)
    assert body["balance"] == body["total"] == 10000
    assert body["held"] == 2000 and body["available"] == 8000
    listed = {a["authorization_id"]: a for a in
              expect(ann.get("/authorizations"), 200).json()["authorizations"]}
    assert set(listed) == {"a_open", "a_done", "a_void", "a_old", "a_late"}
    assert listed["a_open"]["status"] == "open" and listed["a_open"]["note"] == "deposit"
    assert listed["a_open"]["visibility"] == "private"
    assert listed["a_open"]["remaining_amount"] == 2000
    assert listed["a_done"]["status"] == "captured"
    assert listed["a_void"]["status"] == "voided"
    assert listed["a_late"]["status"] == "expired", "open but past expires_at is expired"
    assert me(ben)["held"] == 0


def test_authorizations_may_be_omitted(reset):
    fx = seed.fixture()
    assert "authorizations" not in fx
    reset(fx)
    [ann] = signed_in("ann")
    assert expect(ann.get("/authorizations"), 200).json()["authorizations"] == []


def test_seeded_holds_above_balance_are_refused(reset):
    reset(seed.fixture())
    [ann] = signed_in("ann")
    bad = seed.fixture(authorizations=[seeded_hold("a_1", "cat", "ann", 300),
                                       seeded_hold("a_2", "cat", "ben", 201)])
    expect(request("POST", "/_test/reset", bad), 422, "validation_failed")
    assert me(ann)["total"] == 10000
    ok = seed.fixture(authorizations=[seeded_hold("a_1", "cat", "ann", 300),
                                      seeded_hold("a_2", "cat", "ben", 200),
                                      seeded_hold("a_3", "cat", "ben", 999, hours=-3)])
    expect(request("POST", "/_test/reset", ok), 204)
    [cat] = signed_in("cat")
    assert me(cat)["available"] == 0 and me(cat)["held"] == 500


@pytest.mark.parametrize("change", [
    {"status": "pending"}, {"expires_at": "tomorrow"}, {"amount": 0},
    {"from_user_id": "u_nobody"}, {"to_user_id": "u_ann"},
])
def test_invalid_seeded_authorization_is_422(reset, change):
    hold = {**seeded_hold("a_1", "ann", "ben", 100), **change}
    expect(request("POST", "/_test/reset", seed.fixture(authorizations=[hold])),
           422, "validation_failed")


def test_seeded_ids_and_expiry_verbatim(reset):
    hold = seeded_hold("hold-Seed.7", "ann", "ben", 50)
    reset(seed.fixture(authorizations=[hold]))
    [ben] = signed_in("ben")
    [item] = expect(ben.get("/authorizations"), 200).json()["authorizations"]
    assert item["authorization_id"] == "hold-Seed.7"
    assert item["expires_at"] == hold["expires_at"]
