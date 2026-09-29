"""Item 32: settlements net across the batch and commit all or nothing."""
import pytest

import seed
from client import balances_sum, expect, login


@pytest.fixture
def op(reset):
    fx = seed.fixture(users=[seed.user("opr", 0), seed.user("x", 100), seed.user("y", 0),
                             seed.user("z", 0)], settlement_operator_ids=["u_opr"])
    reset(fx)
    return {h: login(f"{h}@pocket.test", seed.PASSWORD) for h in ("opr", "x", "y", "z")}, \
        seed.total(fx)


def _t(frm, to, amount):
    return {"from_handle": frm, "to_handle": to, "amount": amount}


def test_chain_funded_inside_the_batch(op):
    people, total = op
    body = {"transfers": [_t("y", "z", 100), _t("x", "y", 100)]}
    expect(people["opr"].write("/settlements", body), 201)
    assert [people[h].balance() for h in ("x", "y", "z")] == [0, 0, 100]
    assert balances_sum(people.values()) == total


def test_cycle_nets_to_zero(op):
    people, _ = op
    body = {"transfers": [_t("y", "z", 500), _t("z", "x", 500), _t("x", "y", 500)]}
    expect(people["opr"].write("/settlements", body), 201)
    assert [people[h].balance() for h in ("x", "y", "z")] == [100, 0, 0]


def test_any_negative_wallet_rejects_the_whole_batch(op):
    people, total = op
    body = {"transfers": [_t("x", "z", 50), _t("y", "z", 1)]}
    expect(people["opr"].write("/settlements", body), 409, "insufficient_funds")
    assert [people[h].balance() for h in ("x", "y", "z")] == [100, 0, 0]
    for person in people.values():
        assert person.get("/activity").json()["payments"] == []
    assert balances_sum(people.values()) == total


def test_exactly_zero_is_affordable(op):
    people, _ = op
    body = {"transfers": [_t("x", "y", 60), _t("x", "z", 40)]}
    expect(people["opr"].write("/settlements", body), 201)
    assert [people[h].balance() for h in ("x", "y", "z")] == [0, 60, 40]
