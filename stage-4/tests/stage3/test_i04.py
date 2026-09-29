"""Item 4: GET /statement."""
from urllib.parse import quote

import pytest

import seed
from client import expect
from timefx import ago, pay, seeded_payment, signed_in, statement

T = [ago(hours=h) for h in (5, 4, 3, 2)]


@pytest.fixture
def history(reset):
    reset(seed.fixture(payments=[
        seeded_payment("p_1", "ann", "ben", 500, T[0]),
        seeded_payment("p_2", "ben", "ann", 1200, T[1]),
        seeded_payment("p_3", "ben", "cat", 100, T[2], visibility="public"),
        seeded_payment("p_4", "cat", "ann", 50, T[3]),
    ]))
    return signed_in("ann", "ben", "cat")


def test_shape_and_defaults(history):
    ann, _, _ = history
    body = statement(ann)
    assert set(body) == {"opening_balance", "entries", "closing_balance", "has_more", "snapshot"}
    assert body["opening_balance"] == 10000 + 500 - 1200 - 50
    assert [e["payment"]["payment_id"] for e in body["entries"]] == ["p_1", "p_2", "p_4"]
    assert [e["delta"] for e in body["entries"]] == [-500, 1200, 50]
    assert [e["balance_after"] for e in body["entries"]] == [8750, 9950, 10000]
    assert body["closing_balance"] == 10000 and body["has_more"] is False
    for entry in body["entries"]:
        assert set(entry) == {"payment", "delta", "balance_after", "revision", "effective_at",
                              "recorded_at"}
        assert entry["revision"] == 1
    assert isinstance(body["snapshot"], str) and body["snapshot"]


def test_only_the_callers_payments_even_public_ones(history):
    ann, _, cat = history
    assert "p_3" not in [e["payment"]["payment_id"] for e in statement(ann)["entries"]]
    assert [e["payment"]["payment_id"] for e in statement(cat)["entries"]] == ["p_3", "p_4"]


def test_half_open_window(history):
    ann, _, _ = history
    body = statement(ann, from_=T[1], to=T[3])
    assert [e["payment"]["payment_id"] for e in body["entries"]] == ["p_2"]
    assert body["opening_balance"] == 10000 + 500 - 1200 - 50 - 500
    assert body["closing_balance"] == body["opening_balance"] + 1200
    body = statement(ann, from_=T[0], to=T[1])
    assert [e["payment"]["payment_id"] for e in body["entries"]] == ["p_1"]
    empty = statement(ann, from_=T[1], to=T[1])
    assert empty["entries"] == [] and empty["opening_balance"] == empty["closing_balance"]


def test_arithmetic_closes_and_to_defaults_to_now(history):
    ann, _, _ = history
    live = pay(ann, "ben", 300)
    body = statement(ann, from_=T[2])
    assert body["entries"][-1]["payment"]["payment_id"] == live["payment_id"]
    assert body["opening_balance"] + sum(e["delta"] for e in body["entries"]) \
        == body["closing_balance"] == 9700


@pytest.mark.parametrize("name", ["from", "to"])
@pytest.mark.parametrize("bad", ["", "2026-09-24", "2026-09-24T10:00:00", "soon"])
def test_invalid_instants_are_422(history, name, bad):
    ann, _, _ = history
    expect(ann.get(f"/statement?{name}={quote(bad, safe='')}"), 422, "validation_failed")


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=1e1", "offset=-1",
                                   "limit=%2B4", "offset=x"])
def test_paging_parameters_as_on_requests(history, query):
    ann, _, _ = history
    expect(ann.get(f"/statement?{query}"), 422, "validation_failed")


def test_limit_and_offset(history):
    ann, _, _ = history
    page = statement(ann, limit=2)
    assert len(page["entries"]) == 2 and page["has_more"] is True
    rest = statement(ann, snapshot=page["snapshot"], limit=2, offset=2)
    assert len(rest["entries"]) == 1 and rest["has_more"] is False


def test_statement_needs_a_token(history):
    from client import request
    expect(request("GET", "/statement"), 401, "unauthenticated")
