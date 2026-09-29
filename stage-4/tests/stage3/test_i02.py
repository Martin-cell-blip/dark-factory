"""Item 2: payment timestamps."""
from datetime import datetime

import pytest

import seed
from client import expect, request
from timefx import ago, ahead, me_at, pay, seeded_payment, signed_in, statement


def _instant_ok(stamp):
    moment = datetime.fromisoformat(stamp)
    assert moment.tzinfo is not None and "T" in stamp


def test_every_payment_carries_created_at(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann, ben, cat = signed_in("ann", "ben", "cat")
    made = [pay(ann, "ben", 10)]
    rq = expect(ben.write("/requests", {"payer_handle": "ann", "amount": 5}), 201).json()
    made.append(expect(ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json())
    held = expect(ann.write("/authorizations", {"to_handle": "cat", "amount": 7}), 201).json()
    made.append(expect(cat.write(f"/authorizations/{held['authorization_id']}/capture", {}),
                       201).json())
    made += expect(ann.write("/settlements", {"transfers": [
        {"from_handle": "ben", "to_handle": "cat", "amount": 1}]}), 201).json()["payments"]
    for payment in made:
        _instant_ok(payment["created_at"])
    for payment in expect(ann.get("/activity"), 200).json()["payments"]:
        _instant_ok(payment["created_at"])
    for entry in statement(ann)["entries"]:
        _instant_ok(entry["payment"]["created_at"])


def test_seeded_created_at_orders_the_feed(reset):
    reset(seed.fixture(payments=[
        seeded_payment("p_mid", "ann", "ben", 10, ago(days=2)),
        seeded_payment("p_new", "ben", "ann", 20, ago(days=1)),
        seeded_payment("p_old", "ann", "cat", 30, ago(days=3)),
        seeded_payment("p_reset", "cat", "ben", 5),
    ]))
    [ann] = signed_in("ann")
    later = pay(ann, "ben", 1)["payment_id"]
    feed = [p["payment_id"] for p in expect(ann.get("/activity"), 200).json()["payments"]]
    assert feed == [later, "p_reset", "p_new", "p_mid", "p_old"]
    stamps = {p["payment_id"]: p["created_at"] for p in
              expect(ann.get("/activity"), 200).json()["payments"]}
    assert datetime.fromisoformat(stamps["p_reset"]) > datetime.fromisoformat(stamps["p_new"])
    assert datetime.fromisoformat(stamps[later]) > datetime.fromisoformat(stamps["p_reset"])


def test_seeded_payments_do_not_change_balances(reset):
    reset(seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 500, ago(hours=5))]))
    ann, ben = signed_in("ann", "ben")
    assert ann.balance() == 10000 and ben.balance() == 2500
    assert me_at(ann, as_of=ago(hours=6))["balance"] == 10500


def test_future_seeded_created_at_is_refused(reset):
    reset(seed.fixture())
    [ann] = signed_in("ann")
    bad = seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 5, ahead(hours=1))])
    expect(request("POST", "/_test/reset", bad), 422, "validation_failed")
    assert ann.balance() == 10000


@pytest.mark.parametrize("stamp", ["yesterday", "2026-09-24", "2026-09-24T10:00:00"])
def test_invalid_seeded_created_at_is_refused(reset, stamp):
    bad = seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 5, stamp)])
    expect(request("POST", "/_test/reset", bad), 422, "validation_failed")
