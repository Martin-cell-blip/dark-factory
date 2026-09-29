"""Item 2: POST /payments/{payment_id}/refunds."""
from client import expect, new_key
from refundfx import refund, settle
from timefx import pay

PAYMENT = {"payment_id", "from_user_id", "from_handle", "to_user_id", "to_handle", "amount",
           "currency", "note", "visibility", "request_id", "settlement_id", "authorization_id",
           "refund_of", "created_at"}


def test_a_refund_is_a_reverse_linked_payment(world):
    original = pay(world.ann, "ben", 1000, note="dinner", visibility="private")
    body = refund(world.ben, original, 200).json()
    assert set(body) == PAYMENT
    assert (body["from_user_id"], body["from_handle"]) == ("u_ben", "ben")
    assert (body["to_user_id"], body["to_handle"]) == ("u_ann", "ann")
    assert body["amount"] == 200 and body["refund_of"] == original["payment_id"]
    assert body["request_id"] is None and body["authorization_id"] is None
    assert body["settlement_id"] is None
    assert body["note"] == "dinner" and body["visibility"] == "private"
    assert body["currency"] == "EUR" and body["payment_id"] != original["payment_id"]
    assert world.ann.balance() == 9200 and world.ben.balance() == 3300


def test_replay_returns_the_original_body(world):
    original = pay(world.ann, "ben", 1000)
    key = new_key()
    first = refund(world.ben, original, 300, key=key).json()
    assert refund(world.ben, original, 300, status=200, key=key).json() == first
    assert world.ben.balance() == 3200
    refund(world.ben, original, 301, status=409, code="idempotency_key_reuse", key=key)


def test_every_other_payment_carries_refund_of_null(world):
    made = [pay(world.ann, "ben", 10)]
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 5}), 201).json()
    made.append(expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json())
    held = expect(world.ann.write("/authorizations", {"to_handle": "cat", "amount": 7}),
                  201).json()
    made.append(expect(world.cat.write(f"/authorizations/{held['authorization_id']}/capture", {}),
                       201).json())
    made += settle(world.ann, ("ben", "cat", 3))["payments"]
    for payment in made:
        assert payment["refund_of"] is None
    for payment in expect(world.ann.get("/activity"), 200).json()["payments"]:
        assert payment["refund_of"] is None


def test_section_seven_on_refunds(world):
    original = pay(world.ann, "ben", 1000)
    path = f"/payments/{original['payment_id']}/refunds"
    expect(world.ben.post(path, {"amount": 10}), 400, "missing_idempotency_key")
    expect(world.ben.post(path, {"amount": 10}, key=""), 400, "missing_idempotency_key")
    expect(world.ben.post(path, {"amount": 10}, key="k" * 256), 422, "validation_failed")
    key = new_key()
    expect(world.ben.post(path, {"amount": 0}, key=key), 422, "validation_failed")
    first = expect(world.ben.post(path, {"amount": 10}, key=key), 201).json()
    expect(world.ben.post(path, {"amount": "x"}, key=key), 409, "idempotency_key_reuse")
    assert expect(world.ben.post(path, {"amount": 10}, key=key), 200).json() == first
    other = pay(world.cat, "ben", 100)
    expect(world.ben.post(f"/payments/{other['payment_id']}/refunds", {"amount": 10}, key=key),
           201)
