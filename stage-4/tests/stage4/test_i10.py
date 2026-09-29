"""Item 10: originals preserved."""
from client import expect, new_key
from refundfx import batch, item
from timefx import pay, statement


def test_receipts_retries_statements_and_snapshots(world):
    key = new_key()
    original = expect(world.ben.post("/payments", {"to_handle": "cat", "amount": 300}, key=key),
                      201).json()
    settle_key = new_key()
    settle_body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 100},
                                 {"from_handle": "cat", "to_handle": "ben", "amount": 20}]}
    settled = expect(world.ann.post("/settlements", settle_body, key=settle_key), 201).json()
    frozen = statement(world.ben)
    members = settled["payments"]
    batch(world.ann, [item(original, 200), item(members[0], 50, members[0]["created_at"]),
                      item(members[1], 20, members[1]["created_at"])])
    assert expect(world.ben.post("/payments", {"to_handle": "cat", "amount": 300}, key=key),
                  200).json() == original
    assert expect(world.ann.post("/settlements", settle_body, key=settle_key),
                  200).json() == settled
    feed = {p["payment_id"]: p for p in expect(world.cat.get("/activity"), 200).json()["payments"]}
    assert feed[original["payment_id"]] == original
    assert feed[members[0]["payment_id"]]["amount"] == 100
    fresh = {e["payment"]["payment_id"]: e for e in statement(world.ben)["entries"]}
    assert fresh[original["payment_id"]]["delta"] == -200
    assert fresh[members[0]["payment_id"]]["delta"] == -50
    assert statement(world.ben, snapshot=frozen["snapshot"])["entries"] == frozen["entries"]
    pay(world.ben, "cat", 1)
