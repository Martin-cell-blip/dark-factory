"""Item 9: extended capture mode (final: false) and partial closes."""
import pytest

import seed
from client import expect, new_key
from holdfx import authorize, capture, me, signed_in


def _item(client, authorization_id):
    for item in expect(client.get("/authorizations"), 200).json()["authorizations"]:
        if item["authorization_id"] == authorization_id:
            return item
    raise AssertionError(authorization_id)


@pytest.mark.parametrize("final", ["false", 0, None, [], "true"])
def test_final_must_be_boolean(world, final):
    held = authorize(world.ann, "ben", 1000)
    capture(world.ben, held["authorization_id"], {"amount": 10, "final": final},
            400, "malformed_request")
    assert me(world.ann)["held"] == 1000


def test_nonfinal_captures_up_to_the_remainder(world):
    aid = authorize(world.ann, "ben", 2000)["authorization_id"]
    p1 = capture(world.ben, aid, {"amount": 700, "final": False}).json()
    item = _item(world.ann, aid)
    assert item["status"] == "open" and item["captured_amount"] == 700
    assert item["remaining_amount"] == 1300 and item["payment_id"] == p1["payment_id"]
    assert me(world.ann) == {**me(world.ann), "total": 9300, "held": 1300, "available": 8000}
    p2 = capture(world.ben, aid, {"amount": 300, "final": False}).json()
    p3 = capture(world.ben, aid, {"final": False}).json()
    assert p3["amount"] == 1000, "the default amount is the remainder"
    item = _item(world.ben, aid)
    assert item["status"] == "captured", "capturing the whole remainder closes it"
    assert item["captured_amount"] == 2000 and item["remaining_amount"] == 0
    assert item["payment_ids"] == [p1["payment_id"], p2["payment_id"], p3["payment_id"]]
    assert item["payment_id"] == p3["payment_id"]
    assert me(world.ann)["held"] == 0 and me(world.ben)["total"] == 4500


def test_final_capture_after_partial_ones_releases_the_rest(world):
    aid = authorize(world.ann, "ben", 2000)["authorization_id"]
    capture(world.ben, aid, {"amount": 500, "final": False})
    capture(world.ben, aid, {"amount": 200, "final": True})
    item = _item(world.ann, aid)
    assert item["status"] == "captured" and item["captured_amount"] == 700
    assert item["remaining_amount"] == 0 and len(item["payment_ids"]) == 2
    assert me(world.ann) == {**me(world.ann), "total": 9300, "held": 0, "available": 9300}


def test_void_of_a_partially_captured_authorization(world):
    aid = authorize(world.ann, "ben", 2000)["authorization_id"]
    p1 = capture(world.ben, aid, {"amount": 600, "final": False}).json()
    voided = expect(world.ann.post(f"/authorizations/{aid}/void"), 200).json()
    assert voided["status"] == "voided" and voided["captured_amount"] == 600
    assert voided["remaining_amount"] == 0 and voided["payment_ids"] == [p1["payment_id"]]
    assert me(world.ann) == {**me(world.ann), "total": 9400, "held": 0, "available": 9400}
    feed = expect(world.ann.get("/activity"), 200).json()["payments"]
    assert [p["payment_id"] for p in feed] == [p1["payment_id"]]


def test_expiry_of_a_partially_captured_authorization(reset):
    import time
    reset(seed.fixture(authorization_ttl_seconds=1))
    ann, ben = signed_in("ann", "ben")
    aid = authorize(ann, "ben", 2000)["authorization_id"]
    p1 = capture(ben, aid, {"amount": 250, "final": False}).json()
    time.sleep(1.3)
    item = _item(ann, aid)
    assert item["status"] == "expired" and item["captured_amount"] == 250
    assert item["remaining_amount"] == 0 and item["payment_ids"] == [p1["payment_id"]]
    assert me(ann) == {**me(ann), "total": 9750, "held": 0, "available": 9750}


def test_every_authorization_response_has_remaining_amount(world):
    created = authorize(world.ann, "ben", 900)
    assert created["remaining_amount"] == 900
    listed = expect(world.ann.get("/authorizations"), 200).json()["authorizations"]
    assert all("remaining_amount" in a for a in listed)
    voided = expect(world.ann.post(f"/authorizations/{created['authorization_id']}/void"),
                    200).json()
    assert voided["remaining_amount"] == 0


@pytest.mark.parametrize("second", [{"amount": 700, "final": True}, {"amount": 700, "final": False}])
def test_adding_final_changes_the_body(world, second):
    held = authorize(world.ann, "ben", 2000)
    path = f"/authorizations/{held['authorization_id']}/capture"
    key = new_key()
    expect(world.ben.post(path, {"amount": 700}, key=key), 201)
    expect(world.ben.post(path, second, key=key), 409, "idempotency_key_reuse")
