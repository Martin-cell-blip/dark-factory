"""Item 17: invariants hold under 50 requests in flight."""
import random

import seed
from burst import burst, statuses
from client import balances_sum, expect, login


def _people(reset, n=10, balance=1000):
    fx = seed.fixture(users=[seed.user(f"p{i}", balance) for i in range(n)])
    reset(fx)
    return [login(f"p{i}@pocket.test", seed.PASSWORD) for i in range(n)], seed.total(fx)


def test_concurrent_spends_never_overdraw(reset):
    people, total = _people(reset)
    spender = people[0]
    responses = burst([lambda i=i: spender.write("/payments", {
        "to_handle": f"p{1 + i % 9}", "amount": 30}) for i in range(50)])
    codes = statuses(responses)
    assert codes.count(201) == 33 and codes.count(409) == 17, codes
    assert spender.balance() == 10
    assert balances_sum(people) == total


def test_mixed_load_conserves_money_and_stays_nonnegative(reset):
    people, total = _people(reset)
    rng = random.Random(7)

    def call(i):
        a, b = rng.sample(range(10), 2)
        if i % 5 == 4:
            return people[a].get("/activity?limit=5")
        return people[a].write("/payments", {"to_handle": f"p{b}", "amount": rng.randint(1, 700)})

    calls = [lambda i=i: call(i) for i in range(150)]
    for chunk in range(0, 150, 50):
        statuses(burst(calls[chunk:chunk + 50]))
        balances = [p.balance() for p in people]
        assert min(balances) >= 0 and sum(balances) == total


def test_request_moves_money_at_most_once(reset):
    people, total = _people(reset, n=2, balance=5000)
    payer, requester = people
    rq = expect(requester.write("/requests", {"payer_handle": "p0", "amount": 400}), 201).json()
    responses = burst([lambda: payer.write(f"/requests/{rq['request_id']}/pay", {})] * 50)
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(409) == 49, codes
    assert all(r.json()["error"]["code"] == "request_not_pending"
               for r in responses if r.status == 409)
    assert payer.balance() == 4600 and requester.balance() == 5400
    assert balances_sum(people) == total
