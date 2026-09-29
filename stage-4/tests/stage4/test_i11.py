"""Item 11: concurrency on refunds and batches."""
from burst import burst, statuses
from client import expect, new_key
from refundfx import item
from timefx import ago, me_at, pay


def test_single_and_batch_on_one_revision(world):
    payment = pay(world.ben, "cat", 300)
    single = lambda amount: world.ben.write(f"/payments/{payment['payment_id']}/corrections", {
        "expected_revision": 1, "amount": amount, "effective_at": ago(seconds=2), "reason": "s"})
    batched = lambda amount: world.ann.write("/correction-batches",
                                             {"corrections": [item(payment, amount)]})
    responses = burst([(lambda a=a: single(a)) if a % 2 else (lambda a=a: batched(a))
                       for a in range(1, 31)])
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(409) == 29, codes
    assert {r.json()["error"]["code"] for r in responses if r.status == 409} == {"stale_revision"}


def test_batches_sharing_one_payment(world):
    shared = pay(world.ben, "cat", 300)
    others = [pay(world.ben, "cat", 10) for _ in range(10)]
    responses = burst([lambda o=o: world.ann.write("/correction-batches", {"corrections": [
        item(shared, 250), item(o, 5)]}) for o in others])
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(409) == 9, codes


def test_concurrent_refunds_never_exceed(world):
    payment = pay(world.ann, "ben", 1000)
    responses = burst([lambda: world.ben.write(f"/payments/{payment['payment_id']}/refunds",
                                               {"amount": 70}) for _ in range(30)])
    codes = statuses(responses)
    assert codes.count(201) == 14 and codes.count(422) == 16, codes
    assert world.ben.balance() == 3500 - 980


def test_one_key_on_the_new_paths(world):
    payment = pay(world.ann, "ben", 1000)
    for path, client, body in (
            (f"/payments/{payment['payment_id']}/refunds", world.ben, {"amount": 100}),
            ("/correction-batches", world.ann, {"corrections": [item(payment, 900)]})):
        key = new_key()
        responses = burst([lambda: client.post(path, body, key=key)] * 20)
        codes = statuses(responses)
        assert codes.count(201) == 1 and codes.count(200) == 19, codes
        assert all(r.json() == responses[0].json() for r in responses)
    views = [me_at(c, as_of="2999-01-01T00:00:00+00:00") for c in world.everyone]
    assert sum(v["total"] for v in views) == world.total
    assert all(v["available"] >= 0 for v in views)
    assert expect(world.ann.get("/me"), 200).json()["balance"] == 10000 - 900 + 100
