"""Item 8: batch precedence and atomicity."""
from client import expect, new_key
from refundfx import batch, item, refund, revisions, settle
from timefx import ago, pay, statement


def test_item_errors_in_input_order(world):
    good = pay(world.ben, "cat", 100)
    other = pay(world.ben, "cat", 200)
    batch(world.ann, [item({"payment_id": "p_missing"}, 1), item(good, 1, expected_revision=5)],
          status=404, code="not_found")
    batch(world.ann, [item(good, 1, expected_revision=5), item({"payment_id": "p_missing"}, 1)],
          status=409, code="stale_revision")
    back = refund(world.cat, other, 150).json()
    batch(world.ann, [item(other, 100), item(back, 1)], status=422,
          code="refund_exceeds_payment")
    batch(world.ann, [item(back, 1), item(other, 100)], status=422,
          code="linked_payment_immutable")


def test_item_errors_before_completeness_before_funds_before_history(world):
    members = settle(world.ann, ("ben", "cat", 100), ("cat", "ben", 40))["payments"]
    stale = pay(world.ben, "cat", 10)
    batch(world.ann, [item(members[0], 1, members[0]["created_at"]),
                      item(stale, 1, expected_revision=3)], status=409, code="stale_revision")
    rich = pay(world.cat, "ann", 400)
    batch(world.ann, [item(members[0], 1, members[0]["created_at"]), item(rich, 5000)],
          status=422, code="incomplete_settlement")
    batch(world.ann, [item(rich, 5000)], status=409, code="insufficient_funds")
    to_cat = pay(world.ann, "cat", 1000)
    pay(world.cat, "ben", 1000)
    pay(world.ben, "cat", 2000)
    batch(world.ann, [item(to_cat, 100, to_cat["created_at"])], status=409,
          code="historical_overdraft")


def test_affordability_is_combined(world):
    """Cat spends everything; raising one payment is affordable only because the same batch
    lowers another of Cat's payments."""
    out = pay(world.cat, "ben", 499)
    back = pay(world.cat, "ann", 1)
    assert world.cat.balance() == 0
    batch(world.ann, [item(out, 500)], status=409, code="insufficient_funds")
    batch(world.ann, [item(out, 500), item(back, 0)])
    assert world.cat.balance() == 0 and world.ben.balance() == 3000


def test_a_rejected_batch_changes_nothing(world):
    first = pay(world.ann, "ben", 1000)
    second = pay(world.ben, "cat", 100)
    before = ([c.balance() for c in world.everyone], statement(world.ben)["entries"])
    key = new_key()
    body = {"corrections": [item(first, 10), item(second, 5000)]}
    expect(world.ann.post("/correction-batches", body, key=key), 409, "insufficient_funds")
    assert ([c.balance() for c in world.everyone], statement(world.ben)["entries"]) == before
    assert len(revisions(world.ann, first["payment_id"])) == 1
    expect(world.ann.post("/correction-batches", {"corrections": [item(first, 10)]}, key=key),
           201)
    assert world.ben.balance() == 2500 - 100 + 10
