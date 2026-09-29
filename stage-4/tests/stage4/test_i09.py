"""Item 9: the batch response."""
from datetime import datetime

from client import expect, new_key
from refundfx import batch, item, revisions
from timefx import ahead, correct, pay


def test_response_shape_and_shared_recorded_at(world):
    first = pay(world.ben, "cat", 100)
    second = pay(world.cat, "ben", 50)
    fixed = correct(world.ben, first["payment_id"], 90, first["created_at"]).json()
    body = batch(world.ann, [item(first, 80, expected_revision=2), item(second, 40)]).json()
    assert set(body) == {"correction_batch_id", "recorded_at", "revisions"}
    assert [r["payment_id"] for r in body["revisions"]] == [first["payment_id"],
                                                           second["payment_id"]]
    assert [r["revision"] for r in body["revisions"]] == [3, 2]
    for revision in body["revisions"]:
        assert revision["recorded_at"] == body["recorded_at"]
        assert revision["correction_batch_id"] == body["correction_batch_id"]
        assert set(revision) == {"payment_id", "revision", "amount", "effective_at",
                                 "recorded_at", "reason", "correction_batch_id"}
    recorded = datetime.fromisoformat(body["recorded_at"])
    assert recorded > datetime.fromisoformat(fixed["recorded_at"])
    assert recorded > datetime.fromisoformat(second["created_at"])
    assert revisions(world.cat, second["payment_id"])[-1] == body["revisions"][1]
    assert revisions(world.cat, second["payment_id"])[0]["correction_batch_id"] is None


def test_replay_and_future_effective_times(world):
    payment = pay(world.ben, "cat", 100)
    key = new_key()
    body = {"corrections": [item(payment, 70)]}
    first = expect(world.ann.post("/correction-batches", body, key=key), 201).json()
    correct(world.ben, payment["payment_id"], 60, payment["created_at"], expected_revision=2)
    assert expect(world.ann.post("/correction-batches", body, key=key), 200).json() == first
    assert world.cat.balance() == 560
    batch(world.ann, [item(payment, 50, ahead(hours=1), expected_revision=3)], status=422,
          code="validation_failed")
