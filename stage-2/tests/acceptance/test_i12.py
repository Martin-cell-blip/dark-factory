"""Item 12: POST /payments success shape, defaults and the atomic debit/credit."""
from client import balances_sum, expect


def test_payment_shape(world):
    body = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1500,
                                                "note": "dinner", "visibility": "private"}),
                  201).json()
    assert set(body) == {"payment_id", "from_user_id", "from_handle", "to_user_id",
                         "to_handle", "amount", "currency", "note", "visibility",
                         "request_id", "settlement_id", "created_at"}
    assert body["from_user_id"] == "u_ann" and body["from_handle"] == "ann"
    assert body["to_user_id"] == "u_ben" and body["to_handle"] == "ben"
    assert body["amount"] == 1500 and body["currency"] == "EUR"
    assert body["note"] == "dinner" and body["visibility"] == "private"
    assert body["request_id"] is None and body["settlement_id"] is None
    assert isinstance(body["payment_id"], str) and body["created_at"]


def test_defaults(world):
    body = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1}), 201).json()
    assert body["note"] == "" and body["visibility"] == "public"


def test_debit_and_credit_together(world):
    expect(world.ann.write("/payments", {"to_handle": "cat", "amount": 2345}), 201)
    assert world.ann.balance() == 10000 - 2345
    assert world.cat.balance() == 500 + 2345
    assert balances_sum(world.everyone) == world.total
    for viewer in world.everyone:
        [payment] = viewer.get("/activity").json()["payments"]
        assert payment["amount"] == 2345


def test_exact_balance_can_be_spent(world):
    expect(world.cat.write("/payments", {"to_handle": "ann", "amount": 500}), 201)
    assert world.cat.balance() == 0
