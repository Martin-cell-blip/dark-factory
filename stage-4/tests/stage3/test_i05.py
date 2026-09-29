"""Item 5: statement ordering and pagination."""
import seed
from timefx import ago, correct, pay, seeded_payment, signed_in, statement

SAME = ago(hours=3)


def test_ties_break_by_payment_id(reset):
    reset(seed.fixture(payments=[
        seeded_payment("p_c", "ann", "ben", 3, SAME), seeded_payment("p_a", "ben", "ann", 1, SAME),
        seeded_payment("p_b", "ann", "cat", 2, SAME), seeded_payment("p_0", "ann", "ben", 9,
                                                                     ago(hours=4))]))
    [ann] = signed_in("ann")
    ids = [e["payment"]["payment_id"] for e in statement(ann)["entries"]]
    assert ids == ["p_0", "p_a", "p_b", "p_c"]


def test_order_follows_the_selected_effective_time(world):
    first = pay(world.ann, "ben", 100)
    second = pay(world.ann, "ben", 200)
    correct(world.ann, second["payment_id"], 200, ago(days=1))
    ids = [e["payment"]["payment_id"] for e in statement(world.ann)["entries"]]
    assert ids == [second["payment_id"], first["payment_id"]]


def test_pagination_never_changes_balances(reset):
    reset(seed.fixture(payments=[seeded_payment(f"p_{i:02d}", "ann" if i % 2 else "ben",
                                                "ben" if i % 2 else "ann", 10 + i,
                                                ago(hours=30 - i)) for i in range(25)]))
    [ann] = signed_in("ann")
    whole = statement(ann, limit=200)
    for limit in (1, 4, 7, 25):
        first = statement(ann, limit=limit)
        assert first["opening_balance"] == whole["opening_balance"]
        assert first["closing_balance"] == whole["closing_balance"]
        seen = list(first["entries"])
        offset = limit
        while True:
            page = statement(ann, snapshot=first["snapshot"], limit=limit, offset=offset)
            assert page["opening_balance"] == whole["opening_balance"]
            assert page["closing_balance"] == whole["closing_balance"]
            seen += page["entries"]
            assert page["has_more"] is (offset + limit < 25)
            if not page["has_more"]:
                break
            offset += limit
        assert [e["balance_after"] for e in seen] == [e["balance_after"] for e in whole["entries"]]
    beyond = statement(ann, snapshot=whole["snapshot"], offset=40)
    assert beyond["entries"] == [] and beyond["has_more"] is False
    last = statement(ann, snapshot=whole["snapshot"], limit=10, offset=20)
    assert len(last["entries"]) == 5 and last["has_more"] is False
