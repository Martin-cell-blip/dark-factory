"""Item 12: known_at on GET /me and GET /statement."""
import time
from urllib.parse import quote

import pytest

from client import expect
from timefx import ago, ahead, at, correct, me_at, pay, statement


@pytest.fixture
def corrected(world):
    """Ann pays Ben 300 at `paid`; at `fixed` she corrects it to 100, effective a day ago."""
    payment = pay(world.ann, "ben", 300)
    time.sleep(0.05)
    effective = ago(days=1)
    fix = correct(world.ann, payment["payment_id"], 100, effective).json()
    return world, payment, fix, effective


def test_me_selects_revisions_known_at_an_instant(corrected):
    world, payment, fix, effective = corrected
    before_payment = at(payment["created_at"], microseconds=-1)
    between = at(fix["recorded_at"], microseconds=-1)
    assert me_at(world.ann, known_at=before_payment)["balance"] == 10000
    assert me_at(world.ann, known_at=payment["created_at"])["balance"] == 9700
    assert me_at(world.ann, known_at=between)["balance"] == 9700
    assert me_at(world.ann, known_at=fix["recorded_at"])["balance"] == 9900
    assert me_at(world.ann, known_at=ahead(days=1))["balance"] == 9900
    old_view = me_at(world.ann, as_of=at(effective, hours=1), known_at=between)
    assert old_view["balance"] == 10000, "the original took effect later"
    new_view = me_at(world.ann, as_of=at(effective, hours=1), known_at=fix["recorded_at"])
    assert new_view["balance"] == 9900, "the correction took effect a day ago"
    assert me_at(world.ann, as_of=effective)["balance"] == 9900, "as_of stays inclusive"


def test_statement_selects_revisions_known_at_an_instant(corrected):
    world, payment, fix, effective = corrected
    between = at(fix["recorded_at"], microseconds=-1)
    old = statement(world.ann, known_at=between)
    [entry] = old["entries"]
    assert entry["revision"] == 1 and entry["delta"] == -300
    assert entry["payment"]["amount"] == 300 and old["known_at"] == between
    new = statement(world.ann)
    [entry] = new["entries"]
    assert entry["revision"] == 2 and entry["delta"] == -100
    assert entry["effective_at"] == effective and entry["recorded_at"] == fix["recorded_at"]
    assert statement(world.ann, known_at=at(payment["created_at"], microseconds=-1))["entries"] == []
    window = statement(world.ann, from_=effective, to=at(effective, hours=1))
    assert [e["revision"] for e in window["entries"]] == [2], "the window stays half-open"
    assert statement(world.ann, from_=at(effective, microseconds=1))["entries"] == []


def test_future_instants_and_echo(corrected):
    world, _, _, _ = corrected
    future = ahead(days=3)
    body = me_at(world.ann, as_of=future, known_at=future)
    assert body["balance"] == 9900 and body["known_at"] == future and body["as_of"] == future
    assert statement(world.ann, to=future, known_at=future)["closing_balance"] == 9900


@pytest.mark.parametrize("bad", ["", "2026-09-24", "2026-09-24T10:00:00", "now"])
def test_invalid_known_at_is_422(world, bad):
    expect(world.ann.get(f"/me?known_at={quote(bad, safe='')}"), 422, "validation_failed")
    expect(world.ann.get(f"/statement?known_at={quote(bad, safe='')}"), 422, "validation_failed")
