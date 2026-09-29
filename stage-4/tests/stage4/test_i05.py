"""Item 5: corrections after stage 4."""
from client import expect
from refundfx import refund
from timefx import ago, correct, pay


def test_ordinary_and_request_payments_stay_correctable(world):
    direct = pay(world.ann, "ben", 300)
    correct(world.ann, direct["payment_id"], 200, direct["created_at"])
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 500}), 201).json()
    paid = expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    correct(world.ann, paid["payment_id"], 450, paid["created_at"])
    assert world.ann.balance() == 10000 - 200 - 450


def test_captures_and_refunds_are_immutable(world):
    held = expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 300}),
                  201).json()
    capture = expect(world.ben.write(f"/authorizations/{held['authorization_id']}/capture", {}),
                     201).json()
    correct(world.ann, capture["payment_id"], 100, ago(seconds=2), status=422,
            code="linked_payment_immutable")
    original = pay(world.ann, "ben", 500)
    back = refund(world.ben, original, 100).json()
    correct(world.ben, back["payment_id"], 50, ago(seconds=2), status=422,
            code="linked_payment_immutable")


def test_a_correction_cannot_go_below_what_was_refunded(world):
    original = pay(world.ann, "ben", 1000)
    refund(world.ben, original, 400)
    correct(world.ann, original["payment_id"], 399, original["created_at"], status=422,
            code="refund_exceeds_payment")
    correct(world.ann, original["payment_id"], 400, original["created_at"])
    assert world.ann.balance() == 10000 - 400 + 400 and world.ben.balance() == 2500


def test_correction_debits_use_available_funds(world):
    original = pay(world.ann, "ben", 1000)
    expect(world.ben.write("/authorizations", {"to_handle": "cat", "amount": 3300}), 201)
    correct(world.ann, original["payment_id"], 700, original["created_at"], status=409,
            code="insufficient_funds")
    correct(world.ann, original["payment_id"], 800, original["created_at"])
