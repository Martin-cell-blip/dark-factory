"""Item 3: refund rules."""
import pytest

from client import expect
from refundfx import refund, settle
from timefx import correct, pay


@pytest.mark.parametrize("amount", [0, -1, 1.5, "5", None, True, 1000000001])
def test_invalid_amount(world, amount):
    original = pay(world.ann, "ben", 1000)
    refund(world.ben, original, amount, status=422, code="validation_failed")
    assert world.ben.balance() == 3500


def test_only_the_original_receiver(world):
    original = pay(world.ann, "ben", 1000)
    refund(world.ann, original, 10, status=403, code="forbidden")
    refund(world.cat, original, 10, status=403, code="forbidden")
    refund(world.ben, {"payment_id": "p_missing"}, 10, status=404, code="not_found")


def test_targets(world):
    direct = pay(world.ann, "ben", 100)
    refund(world.ben, direct, 10)
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 50}), 201).json()
    paid = expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    refund(world.ben, paid, 50)
    held = expect(world.ann.write("/authorizations", {"to_handle": "cat", "amount": 70}),
                  201).json()
    capture = expect(world.cat.write(f"/authorizations/{held['authorization_id']}/capture", {}),
                     201).json()
    refund(world.cat, capture, 70)
    member = settle(world.ann, ("ben", "cat", 30))["payments"][0]
    refund(world.cat, member, 30)
    back = refund(world.ben, direct, 5).json()
    refund(world.ann, back, 1, status=422, code="invalid_refund_target")


def test_cumulative_refunds_are_bounded_by_the_corrected_amount(world):
    original = pay(world.ann, "ben", 1000)
    refund(world.ben, original, 600)
    refund(world.ben, original, 401, status=422, code="refund_exceeds_payment")
    refund(world.ben, original, 400)
    refund(world.ben, original, 1, status=422, code="refund_exceeds_payment")
    lowered = pay(world.ann, "ben", 1000)
    correct(world.ann, lowered["payment_id"], 300, lowered["created_at"])
    refund(world.ben, lowered, 301, status=422, code="refund_exceeds_payment")
    refund(world.ben, lowered, 300)


def test_receiver_needs_available_funds(world):
    original = pay(world.ann, "cat", 400)
    pay(world.cat, "ben", 800)
    refund(world.cat, original, 101, status=409, code="insufficient_funds")
    refund(world.cat, original, 100)
    assert world.cat.balance() == 0
    second = pay(world.ann, "cat", 300)
    expect(world.cat.write("/authorizations", {"to_handle": "ben", "amount": 250}), 201)
    refund(world.cat, second, 51, status=409, code="insufficient_funds")
    refund(world.cat, second, 50)


def test_check_order(world):
    original = pay(world.ann, "cat", 400)
    back = refund(world.cat, original, 10).json()
    refund(world.ann, {"payment_id": "p_missing"}, 0, status=422, code="validation_failed")
    refund(world.ann, back, 999999, status=422, code="invalid_refund_target")
    refund(world.ben, back, 1, status=403, code="forbidden")
    pay(world.cat, "ben", 890)
    refund(world.cat, original, 391, status=422, code="refund_exceeds_payment")
    refund(world.cat, original, 390, status=409, code="insufficient_funds")
