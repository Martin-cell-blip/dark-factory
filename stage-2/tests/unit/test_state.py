"""In-process checks of the state: the money guard, fixtures and export round trips."""
import pytest

from pocketful.errors import ApiError
from pocketful.passwords import verify_password
from pocketful.state import State


def _fixture(**extra):
    users = [{"id": f"u_{h}", "email": f"{h}@x.io", "password": "password1",
              "display_name": h, "handle": h, "balance": b} for h, b in (("a", 100), ("b", 0))]
    return {"currency": "JPY", "minor_units": 0, "users": users, **extra}


def test_commit_is_all_or_nothing():
    state = State.from_fixture(_fixture())
    a, b = state.users["u_a"], state.users["u_b"]
    move = lambda frm, to, amount: {"from": frm, "to": to, "amount": amount, "note": "",
                                    "visibility": "public"}
    with pytest.raises(ApiError) as error:
        state.commit_payments([move(a, b, 50), move(b, a, 60)], "2026-01-01T00:00:00+00:00")
    assert error.value.code == "insufficient_funds"
    assert (a["balance"], b["balance"], state.payments) == (100, 0, [])
    state.commit_payments([move(b, a, 60), move(a, b, 100)], "2026-01-01T00:00:00+00:00")
    assert (a["balance"], b["balance"], len(state.payments)) == (60, 40, 2)


@pytest.mark.parametrize("change", [
    lambda f: f["users"][0].update(balance=-1),
    lambda f: f["users"][1].update(handle="a"),
    lambda f: f["users"][1].update(handle="Bad"),
    lambda f: f.update(minor_units=1),
    lambda f: f.update(payments=[{"id": "p", "from_user_id": "u_a", "to_user_id": "u_zz",
                                  "amount": 1}]),
    lambda f: f.update(requests=[{"id": "r", "requester_id": "u_a", "payer_id": "u_b",
                                  "amount": 1, "status": "lost"}]),
])
def test_invalid_fixture_is_422(change):
    fixture = _fixture()
    change(fixture)
    with pytest.raises(ApiError) as error:
        State.from_fixture(fixture)
    assert (error.value.status, error.value.code) == (422, "validation_failed")


def test_export_round_trip_keeps_hashes_and_records():
    state = State.from_fixture(_fixture(payments=[
        {"id": "p_1", "from_user_id": "u_a", "to_user_id": "u_b", "amount": 5}]))
    token = state.issue_token("u_a")
    document = state.export()
    assert "password1" not in str(document)
    copy = State.from_export(document)
    assert copy.export() == document
    assert copy.tokens[token] == "u_a"
    assert verify_password("password1", copy.users["u_a"]["password_hash"])
    assert copy.clock.now() > document["state"]["payments"][0]["created_at"]
