"""Item 14: stable statement pagination with snapshot tokens."""
import pytest

import seed
from client import expect
from timefx import ago, correct, pay, seeded_payment, signed_in, statement


@pytest.fixture
def history(reset):
    reset(seed.fixture(payments=[seeded_payment(f"p_{i}", "ann", "ben", 10 * (i + 1),
                                                ago(hours=10 - i)) for i in range(6)]))
    return signed_in("ann", "ben")


def test_a_snapshot_pages_one_frozen_result(history):
    ann, ben = history
    first = statement(ann, limit=2)
    token = first["snapshot"]
    pay(ann, "ben", 999)
    correct(ann, "p_0", 1, ago(hours=11))
    pay(ben, "ann", 5)
    pages = [first] + [statement(ann, snapshot=token, limit=2, offset=o) for o in (2, 4)]
    entries = [e for page in pages for e in page["entries"]]
    assert [e["payment"]["payment_id"] for e in entries] == [f"p_{i}" for i in range(6)]
    assert entries[0]["delta"] == -10 and entries[-1]["balance_after"] == 10000
    assert all(p["opening_balance"] == 10210 and p["closing_balance"] == 10000 for p in pages)
    assert [p["has_more"] for p in pages] == [True, True, False]
    assert all(p["snapshot"] == token for p in pages)
    fresh = statement(ann)
    assert fresh["snapshot"] != token and len(fresh["entries"]) == 8


@pytest.mark.parametrize("extra", ["from", "to", "known_at"])
def test_window_parameters_with_a_snapshot_are_422(history, extra):
    ann, _ = history
    token = statement(ann)["snapshot"]
    expect(ann.get(f"/statement?snapshot={token}&{extra}=2026-09-24T10:00:00%2B00:00"),
           422, "validation_failed")


def test_unknown_foreign_and_reset_tokens_are_404(history, reset):
    ann, ben = history
    token = statement(ann)["snapshot"]
    expect(ann.get("/statement?snapshot=no-such-token"), 404, "not_found")
    expect(ben.get(f"/statement?snapshot={token}"), 404, "not_found")
    expect(ann.get(f"/statement?snapshot={token}&colour=red&limit=1"), 200)
    reset(seed.fixture())
    [again] = signed_in("ann")
    expect(again.get(f"/statement?snapshot={token}"), 404, "not_found")


def test_default_to_is_frozen(world):
    first = statement(world.ann)
    pay(world.ann, "ben", 10)
    again = statement(world.ann, snapshot=first["snapshot"])
    assert again["entries"] == [] and again["closing_balance"] == 10000
