"""In-process checks of revision selection and the historical overdraft sweep."""
from datetime import datetime, timedelta, timezone

from pocketful import history
from pocketful.state import State

T0 = datetime(2026, 9, 1, tzinfo=timezone.utc)


def at(hours: float) -> str:
    return (T0 + timedelta(hours=hours)).isoformat()


def _state(payments, balances=(1000, 100, 0)):
    """Seeded balances are the balances after the seeded payments."""
    users = [{"id": f"u_{h}", "email": f"{h}@x.io", "password": "password1",
              "display_name": h, "handle": h, "balance": b}
             for h, b in zip("abc", balances)]
    return State.from_fixture({"currency": "EUR", "minor_units": 2, "users": users,
                               "payments": payments})


def _pay(pid, frm, to, amount, hours):
    return {"id": pid, "from_user_id": f"u_{frm}", "to_user_id": f"u_{to}", "amount": amount,
            "created_at": at(hours)}


def test_select_picks_the_latest_revision_recorded_by_then():
    state = _state([_pay("p1", "a", "b", 100, 1)])
    state.revisions.append("p1", 40, at(0.5), at(3), "fix")
    assert state.revisions.select("p1", T0) is None
    assert state.revisions.select("p1", T0 + timedelta(hours=2))[0]["amount"] == 100
    revision, effective = state.revisions.select("p1", T0 + timedelta(hours=3))
    assert revision["amount"] == 40 and effective == T0 + timedelta(hours=0.5)


def test_views_and_opening_balances():
    state = _state([_pay("p1", "a", "b", 100, 1), _pay("p2", "b", "c", 60, 2)], (1000, 40, 60))
    assert history.opening_balance(state, "u_a") == 1100
    assert history.balance_at(state, "u_b", T0 + timedelta(hours=1), history.ALWAYS) == 100
    assert history.balance_at(state, "u_b", T0 + timedelta(hours=2), history.ALWAYS) == 40
    window = history.statement(state, "u_b", history.NEVER, history.ALWAYS, history.ALWAYS)
    assert [e["delta"] for e in window["entries"]] == [100, -60]
    assert window["opening_balance"] == 0 and window["closing_balance"] == 40


def test_the_sweep_counts_one_instant_together():
    state = _state([_pay("p1", "a", "b", 100, 1), _pay("p2", "b", "c", 100, 1)], (1000, 0, 100))
    assert history.never_negative(state, "u_b")
    later = T0 + timedelta(hours=2)
    assert not history.never_negative(state, "u_b", {"p1": (100, later)})
    assert history.never_negative(state, "u_b", {"p2": (100, later)})
