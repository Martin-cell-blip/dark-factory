"""Item 8: corrections and idempotency."""
from client import expect, new_key
from timefx import ago, correct, pay


def _path(payment):
    return f"/payments/{payment['payment_id']}/corrections"


def _body(revision=1, amount=100, when=None):
    return {"expected_revision": revision, "amount": amount,
            "effective_at": when or ago(seconds=5), "reason": "fix"}


def test_stale_revision(world):
    payment = pay(world.ann, "ben", 300)
    correct(world.ann, payment["payment_id"], 200, ago(seconds=5))
    correct(world.ann, payment["payment_id"], 100, ago(seconds=5), expected_revision=1,
            status=409, code="stale_revision")
    correct(world.ann, payment["payment_id"], 100, ago(seconds=5), expected_revision=3,
            status=409, code="stale_revision")
    assert world.ann.balance() == 9800


def test_replay_returns_the_original_revision_after_newer_ones(world):
    payment = pay(world.ann, "ben", 300)
    key, body = new_key(), _body()
    first = expect(world.ann.post(_path(payment), body, key=key), 201).json()
    correct(world.ann, payment["payment_id"], 50, ago(seconds=2), expected_revision=2)
    again = expect(world.ann.post(_path(payment), body, key=key), 200).json()
    assert again == first and again["revision"] == 2
    assert world.ann.balance() == 9950
    expect(world.ann.post(_path(payment), _body(amount=101), key=key), 409, "idempotency_key_reuse")
    expect(world.ann.post(_path(payment), {"amount": "bad"}, key=key), 409, "idempotency_key_reuse")


def test_section_seven_set(world):
    payment = pay(world.ann, "ben", 300)
    body = _body()
    expect(world.ann.post(_path(payment), body), 400, "missing_idempotency_key")
    expect(world.ann.post(_path(payment), body, key=""), 400, "missing_idempotency_key")
    expect(world.ann.post(_path(payment), body, key="k" * 256), 422, "validation_failed")
    key = new_key()
    expect(world.ann.post(_path(payment), _body(revision=9), key=key), 409, "stale_revision")
    expect(world.ann.post(_path(payment), body, key=key), 201)
    other = pay(world.ben, "ann", 300)
    expect(world.ben.post(_path(other), _body(), key=key), 201)
