"""Item 3: GET /me?as_of=."""
from urllib.parse import quote

import pytest

import seed
from client import expect
from timefx import ahead, ago, me_at, pay, seeded_payment, signed_in

STAMP_1, STAMP_2 = ago(hours=3), ago(hours=2)


@pytest.fixture
def history(reset):
    reset(seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 500, STAMP_1),
                                 seeded_payment("p_2", "ben", "ann", 200, STAMP_2)]))
    return signed_in("ann", "ben")


def test_without_temporal_parameters_nothing_changes(history):
    ann, _ = history
    body = expect(ann.get("/me"), 200).json()
    assert list(body) == ["user_id", "display_name", "handle", "balance", "total", "available",
                          "held", "currency", "minor_units"]
    assert body["balance"] == 10000 and "as_of" not in body
    expect(ann.get("/me?colour=blue"), 200)


def test_balance_at_each_instant(history):
    ann, ben = history
    assert me_at(ann, as_of=ago(hours=4))["balance"] == 10300, "opening balance"
    assert me_at(ann, as_of=STAMP_1)["balance"] == 9800, "a payment at as_of counts"
    assert me_at(ann, as_of=ago(hours=2, minutes=30))["balance"] == 9800
    assert me_at(ann, as_of=STAMP_2)["balance"] == 10000
    assert me_at(ann, as_of=ago(minutes=1))["balance"] == 10000
    assert me_at(ben, as_of=ago(hours=4))["balance"] == 2200
    assert me_at(ben, as_of=STAMP_1)["balance"] == 2700


def test_after_the_latest_payment_is_the_current_balance(history):
    ann, _ = history
    pay(ann, "cat", 300)
    body = me_at(ann, as_of=ahead(hours=1))
    assert body["balance"] == body["total"] == body["available"] == 9700
    assert body["held"] == 0


@pytest.mark.parametrize("stamp", ["2026-09-24T13:20:00Z", "2026-09-24T15:20:00.250+02:00",
                                   "2026-09-24T13:20:00+00:00"])
def test_as_of_is_echoed_exactly(history, stamp):
    ann, _ = history
    assert me_at(ann, as_of=stamp)["as_of"] == stamp


@pytest.mark.parametrize("bad", ["", "2026-09-24", "2026-09-24T13:20:00", "13:20",
                                 "2026-09-24 13:20:00+00:00x", "2026-09-24T13:20+00:00",
                                 "tomorrow", "1727180400"])
def test_invalid_as_of_is_422(history, bad):
    ann, _ = history
    expect(ann.get(f"/me?as_of={quote(bad, safe='')}"), 422, "validation_failed")


def test_as_of_rejects_an_unencoded_plus_turned_space_only_when_invalid(history):
    ann, _ = history
    body = expect(ann.get("/me?as_of=2026-09-24T13:20:00+00:00"), 200).json()
    assert body["as_of"] == "2026-09-24T13:20:00+00:00"
