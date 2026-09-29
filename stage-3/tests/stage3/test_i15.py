"""Item 15: concurrency on corrections and snapshots."""
from burst import burst, statuses
from client import expect, new_key
from timefx import ago, me_at, pay, statement


def test_one_expected_revision_wins(world):
    payment = pay(world.ann, "ben", 300)
    path = f"/payments/{payment['payment_id']}/corrections"
    responses = burst([lambda amount=amount: world.ann.write(path, {
        "expected_revision": 1, "amount": amount, "effective_at": ago(seconds=1),
        "reason": "race"}) for amount in range(1, 31)])
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(409) == 29, codes
    assert {r.json()["error"]["code"] for r in responses if r.status == 409} == {"stale_revision"}
    winner = next(r.json() for r in responses if r.status == 201)
    assert world.ann.balance() == 10000 - winner["amount"]
    assert world.ann.balance() + world.ben.balance() + world.cat.balance() == world.total


def test_one_key_takes_effect_once(world):
    payment = pay(world.ann, "ben", 300)
    path = f"/payments/{payment['payment_id']}/corrections"
    key = new_key()
    body = {"expected_revision": 1, "amount": 120, "effective_at": ago(seconds=1),
            "reason": "same"}
    responses = burst([lambda: world.ann.post(path, body, key=key)] * 20)
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(200) == 19, codes
    assert all(r.json() == responses[0].json() for r in responses)
    assert world.ann.balance() == 9880


def test_snapshots_stay_frozen_under_concurrent_writes(world):
    payments = [pay(world.ann, "ben", 10) for _ in range(5)]
    frozen = statement(world.ann)
    work = []
    for i in range(30):
        if i % 3 == 0:
            work.append(lambda: world.ann.write("/payments", {"to_handle": "cat", "amount": 1}))
        elif i % 3 == 1:
            target = payments[i % 5]["payment_id"]
            work.append(lambda target=target: world.ann.write(
                f"/payments/{target}/corrections", {"expected_revision": 1, "amount": 5,
                                                    "effective_at": ago(seconds=1),
                                                    "reason": "busy"}))
        else:
            work.append(lambda: world.ann.get(f"/statement?snapshot={frozen['snapshot']}"))
    statuses(burst(work))
    again = statement(world.ann, snapshot=frozen["snapshot"])
    assert again["entries"] == frozen["entries"]
    assert again["closing_balance"] == frozen["closing_balance"]
    views = [me_at(c, as_of=ago(seconds=0)) for c in world.everyone]
    assert sum(v["balance"] for v in views) == world.total
    assert all(v["balance"] >= 0 and v["available"] >= 0 for v in views)
