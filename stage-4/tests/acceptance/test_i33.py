"""Item 33: the settlement response and its member payments."""
import pytest

import seed
from client import expect, login, new_key


@pytest.fixture
def op(reset):
    reset(seed.fixture(settlement_operator_ids=["u_cat"]))
    return {h: login(f"{h}@pocket.test", seed.PASSWORD) for h in ("ann", "ben", "cat")}


BODY = {"transfers": [
    {"from_handle": "ann", "to_handle": "ben", "amount": 100, "note": "one"},
    {"from_handle": "ben", "to_handle": "ann", "amount": 30, "visibility": "private"},
    {"from_handle": "ann", "to_handle": "cat", "amount": 7},
]}


def test_response_and_members(op):
    body = expect(op["cat"].write("/settlements", BODY), 201).json()
    assert set(body) == {"settlement_id", "committed_at", "payments"}
    payments = body["payments"]
    assert [(p["from_handle"], p["to_handle"], p["amount"]) for p in payments] == \
        [("ann", "ben", 100), ("ben", "ann", 30), ("ann", "cat", 7)]
    for p in payments:
        assert p["settlement_id"] == body["settlement_id"]
        assert p["request_id"] is None and p["created_at"] == body["committed_at"]
        assert p["currency"] == "EUR"
    assert payments[0]["note"] == "one" and payments[1]["visibility"] == "private"
    assert op["ann"].balance() == 10000 - 100 + 30 - 7


def test_members_follow_feed_visibility(op):
    body = expect(op["cat"].write("/settlements", BODY), 201).json()
    ids = [p["payment_id"] for p in body["payments"]]
    seen_by_cat = {p["payment_id"] for p in op["cat"].get("/activity").json()["payments"]}
    assert seen_by_cat == {ids[0], ids[2]}
    seen_by_ann = op["ann"].get("/activity").json()["payments"]
    assert {p["payment_id"] for p in seen_by_ann} == set(ids)
    assert all(p["settlement_id"] == body["settlement_id"] for p in seen_by_ann)


def test_nonmembers_expose_null(op):
    payment = expect(op["ann"].write("/payments", {"to_handle": "ben", "amount": 1}), 201).json()
    assert payment["settlement_id"] is None
    [feed] = op["ben"].get("/activity").json()["payments"]
    assert feed["settlement_id"] is None


def test_replay_returns_the_original_complete_response(op):
    key = new_key()
    first = expect(op["cat"].post("/settlements", BODY, key=key), 201).json()
    again = expect(op["cat"].post("/settlements", BODY, key=key), 200).json()
    assert again == first
    assert op["ann"].balance() == 10000 - 100 + 30 - 7
