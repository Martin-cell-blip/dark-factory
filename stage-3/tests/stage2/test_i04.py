"""Item 4: POST /authorizations success shape."""
from datetime import datetime

from client import expect, new_key

SHAPE = ["authorization_id", "from_user_id", "from_handle", "to_user_id", "to_handle",
         "amount", "captured_amount", "remaining_amount", "currency", "note", "visibility",
         "status", "expires_at", "payment_id", "payment_ids", "created_at"]


def test_created_authorization(world):
    body = expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 2000,
                                                      "note": "deposit",
                                                      "visibility": "private"}), 201).json()
    assert sorted(body) == sorted(SHAPE)
    assert body["from_user_id"] == "u_ann" and body["from_handle"] == "ann"
    assert body["to_user_id"] == "u_ben" and body["to_handle"] == "ben"
    assert body["amount"] == 2000 and body["captured_amount"] == 0
    assert body["remaining_amount"] == 2000 and body["currency"] == "EUR"
    assert body["note"] == "deposit" and body["visibility"] == "private"
    assert body["status"] == "open" and body["payment_id"] is None
    assert body["payment_ids"] == []
    assert isinstance(body["authorization_id"], str) and len(body["authorization_id"]) <= 64
    created = datetime.fromisoformat(body["created_at"])
    assert created.tzinfo is not None
    assert (datetime.fromisoformat(body["expires_at"]) - created).total_seconds() == 600


def test_defaults_like_payments(world):
    body = expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 1}),
                  201).json()
    assert body["note"] == "" and body["visibility"] == "public"


def test_idempotency_key_required_and_replayed(world):
    body = {"to_handle": "ben", "amount": 300}
    expect(world.ann.post("/authorizations", body), 400, "missing_idempotency_key")
    key = new_key()
    first = expect(world.ann.post("/authorizations", body, key=key), 201).json()
    again = expect(world.ann.post("/authorizations", body, key=key), 200).json()
    assert again == first
    assert expect(world.ann.get("/me"), 200).json()["held"] == 300
    expect(world.ann.post("/authorizations", {**body, "amount": 301}, key=key),
           409, "idempotency_key_reuse")
