"""Item 10: the original payment and its original responses are preserved."""
from client import expect, new_key
from timefx import ago, correct


def test_originals_stay_unchanged(world):
    key = new_key()
    body = {"to_handle": "ben", "amount": 300, "note": "lunch"}
    original = expect(world.ann.post("/payments", body, key=key), 201).json()
    before_feed = expect(world.cat.get("/activity"), 200).json()
    correct(world.ann, original["payment_id"], 100, ago(seconds=2))
    correct(world.ann, original["payment_id"], 0, ago(seconds=1), expected_revision=2)
    assert expect(world.ann.post("/payments", body, key=key), 200).json() == original
    after_feed = expect(world.cat.get("/activity"), 200).json()
    assert after_feed == before_feed
    [item] = after_feed["payments"]
    assert item == original and item["amount"] == 300


def test_a_paid_request_replay_is_unchanged(world):
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 400}), 201).json()
    key = new_key()
    paid = expect(world.ann.post(f"/requests/{rq['request_id']}/pay", {}, key=key), 201).json()
    correct(world.ann, paid["payment_id"], 250, paid["created_at"])
    again = expect(world.ann.post(f"/requests/{rq['request_id']}/pay", {}, key=key), 200).json()
    assert again == paid
    [listed] = expect(world.ben.get("/requests"), 200).json()["requests"]
    assert listed["status"] == "paid" and listed["amount"] == 400
    assert len(expect(world.ben.get("/activity"), 200).json()["payments"]) == 1
