"""Item 6: POST /correction-batches."""
import pytest

from client import expect, request
from refundfx import batch, item, refund, revisions, settle
from timefx import ahead, pay


def test_who_may_submit(world):
    payment = pay(world.ben, "cat", 100)
    body = {"corrections": [item(payment, 50)]}
    expect(request("POST", "/correction-batches", body, key="k"), 401, "unauthenticated")
    expect(world.ben.write("/correction-batches", body), 403, "forbidden")
    expect(world.ann.post("/correction-batches", body), 400, "missing_idempotency_key")
    batch(world.ann, [item(payment, 50)])
    assert world.ben.balance() == 2450 and world.cat.balance() == 550


@pytest.mark.parametrize("corrections", [[], "x", None, [1], [{"expected_revision": 1}]])
def test_malformed_batches_are_422(world, corrections):
    expect(world.ann.write("/correction-batches", {"corrections": corrections}),
           422, "validation_failed")


def test_size_and_distinct_payments(world):
    payments = [pay(world.ben, "cat", 1) for _ in range(33)]
    batch(world.ann, [item(p, 0) for p in payments], status=422, code="validation_failed")
    batch(world.ann, [item(payments[0], 0), item(payments[0], 1)], status=422,
          code="validation_failed")
    batch(world.ann, [item(p, 0) for p in payments[:32]])


@pytest.mark.parametrize("change,status", [
    ({"amount": -1}, 422), ({"amount": "1"}, 422), ({"reason": ""}, 422),
    ({"expected_revision": 0}, 422), ({"effective_at": "2026-09-24"}, 422),
    ({"effective_at": ahead(hours=1)}, 422), ({"reason": 7}, 400),
])
def test_item_validation(world, change, status):
    payment = pay(world.ben, "cat", 100)
    code = "validation_failed" if status == 422 else "malformed_request"
    batch(world.ann, [{**item(payment, 50), **change}], status=status, code=code)


def test_unknown_stale_and_immutable_items(world):
    payment = pay(world.ben, "cat", 100)
    batch(world.ann, [item({"payment_id": "p_missing"}, 1)], status=404, code="not_found")
    batch(world.ann, [item(payment, 50, expected_revision=2)], status=409, code="stale_revision")
    held = expect(world.ben.write("/authorizations", {"to_handle": "cat", "amount": 30}),
                  201).json()
    capture = expect(world.cat.write(f"/authorizations/{held['authorization_id']}/capture", {}),
                     201).json()
    batch(world.ann, [item(capture, 1)], status=422, code="linked_payment_immutable")
    back = refund(world.cat, payment, 10).json()
    batch(world.ann, [item(back, 1)], status=422, code="linked_payment_immutable")


def test_the_operator_corrects_request_and_settlement_payments(world):
    rq = expect(world.cat.write("/requests", {"payer_handle": "ben", "amount": 200}), 201).json()
    paid = expect(world.ben.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    members = settle(world.ann, ("ben", "cat", 100), ("cat", "ben", 40))["payments"]
    body = batch(world.ann, [{**item(paid, 150), "colour": "red"}, item(members[0], 90,
                                                                       members[0]["created_at"]),
                             item(members[1], 40, members[1]["created_at"])],
                 key=None).json()
    assert [r["payment_id"] for r in body["revisions"]] == [paid["payment_id"],
                                                           members[0]["payment_id"],
                                                           members[1]["payment_id"]]
    assert world.ben.balance() == 2500 - 150 - 90 + 40
    assert revisions(world.ben, paid["payment_id"])[-1]["amount"] == 150
