"""Item 26: the section 9 equal split."""
import pytest

import seed
from client import balances_sum, expect, login

HANDLES = ["h0", "h1", "h2", "h3", "h4", "h5"]


@pytest.fixture
def six(reset):
    fx = seed.fixture(users=[seed.user(h, 50000) for h in HANDLES])
    reset(fx)
    return [login(f"{h}@pocket.test", seed.PASSWORD) for h in HANDLES], seed.total(fx)


def _shares(client, amount, handles):
    body = expect(client.write("/splits", {"amount": amount, "participant_handles": handles}),
                  201).json()
    return [s["amount"] for s in body["shares"]], body


@pytest.mark.parametrize("amount,n,expected", [
    (1000, 3, [334, 333, 333]), (1, 3, [1, 0, 0]), (10, 3, [4, 3, 3]),
    (999, 3, [333, 333, 333]), (5, 5, [1, 1, 1, 1, 1]), (7, 6, [2, 1, 1, 1, 1, 1]),
    (1000000000, 6, [166666667, 166666667, 166666667, 166666667, 166666666, 166666666]),
])
def test_table(six, amount, n, expected):
    people, _ = six
    shares, _ = _shares(people[0], amount, HANDLES[:n])
    assert shares == expected and sum(shares) == amount


def test_reordering_moves_the_extra_unit(six):
    people, _ = six
    _, first = _shares(people[0], 1000, ["h0", "h1", "h2"])
    _, second = _shares(people[0], 1000, ["h2", "h0", "h1"])
    assert first["shares"][0] == {"handle": "h0", "amount": 334}
    assert second["shares"][0] == {"handle": "h2", "amount": 334}
    assert {"handle": "h0", "amount": 333} in second["shares"]


def test_splits_are_independent_and_paying_them_conserves_money(six):
    people, total = six
    for amount in (1000, 1000, 10, 1, 999, 12345):
        shares, body = _shares(people[0], amount, HANDLES[:3])
        assert shares == _shares(people[0], amount, HANDLES[:3])[0]
        for req in body["requests"]:
            payer = people[HANDLES.index(req["payer_handle"])]
            if req["amount"]:
                expect(payer.write(f"/requests/{req['request_id']}/pay", {}), 201)
    assert balances_sum(people) == total
