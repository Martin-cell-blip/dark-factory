"""Item 18: POST /requests."""
import pytest

from client import expect


def test_request_shape(world):
    body = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 1200,
                                                "note": "taxi"}), 201).json()
    assert set(body) == {"request_id", "requester_id", "requester_handle", "payer_id",
                         "payer_handle", "amount", "currency", "note", "status",
                         "payment_id", "created_at"}
    assert body["requester_id"] == "u_ben" and body["requester_handle"] == "ben"
    assert body["payer_id"] == "u_ann" and body["payer_handle"] == "ann"
    assert body["amount"] == 1200 and body["currency"] == "EUR" and body["note"] == "taxi"
    assert body["status"] == "pending" and body["payment_id"] is None


def test_payer_balance_is_not_checked(world):
    body = expect(world.ann.write("/requests", {"payer_handle": "cat", "amount": 999999}),
                  201).json()
    assert body["status"] == "pending"
    assert world.cat.balance() == 500
    assert body["note"] == ""


def test_self_request(world):
    expect(world.ann.write("/requests", {"payer_handle": "ann", "amount": 5}),
           422, "self_request")


@pytest.mark.parametrize("note", ["x" * 201, None, 3])
def test_bad_note(world, note):
    expect(world.ann.write("/requests", {"payer_handle": "ben", "amount": 5, "note": note}),
           422, "validation_failed")


def test_unknown_handle(world):
    expect(world.ann.write("/requests", {"payer_handle": "ghost", "amount": 5}),
           404, "not_found")
    assert world.ann.get("/requests").json()["requests"] == []
