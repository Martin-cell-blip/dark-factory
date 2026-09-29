"""Item 8: capture errors and replays."""
import pytest

import seed
from client import expect, new_key
from holdfx import authorize, capture, me, seeded_hold, signed_in


def test_second_capture_after_a_final_one(world):
    held = authorize(world.ann, "ben", 1000)
    capture(world.ben, held["authorization_id"], {"amount": 400})
    capture(world.ben, held["authorization_id"], {"amount": 100}, 409, "authorization_not_open")
    capture(world.ben, held["authorization_id"], {}, 409, "authorization_not_open")


def test_capture_after_expiry(reset):
    reset(seed.fixture(authorizations=[seeded_hold("a_gone", "ann", "ben", 500, hours=-1)]))
    ann, ben = signed_in("ann", "ben")
    capture(ben, "a_gone", {}, 409, "authorization_expired")
    assert me(ann)["held"] == 0 and me(ben)["total"] == 2500


def test_amount_above_the_remainder(world):
    held = authorize(world.ann, "ben", 1000)
    capture(world.ben, held["authorization_id"], {"amount": 1001}, 422,
            "capture_exceeds_authorization")
    capture(world.ben, held["authorization_id"], {"amount": 600, "final": False})
    capture(world.ben, held["authorization_id"], {"amount": 401}, 422,
            "capture_exceeds_authorization")
    assert me(world.ann)["held"] == 400


@pytest.mark.parametrize("amount", [0, -3, 2.5, "100", None, True])
def test_invalid_amount(world, amount):
    held = authorize(world.ann, "ben", 1000)
    capture(world.ben, held["authorization_id"], {"amount": amount}, 422, "validation_failed")
    assert me(world.ann)["held"] == 1000


def test_only_the_receiver_may_capture(world):
    held = authorize(world.ann, "ben", 1000)
    capture(world.ann, held["authorization_id"], {}, 403, "forbidden")
    capture(world.cat, held["authorization_id"], {}, 403, "forbidden")
    capture(world.ben, "a_does_not_exist", {}, 404, "not_found")
    assert me(world.ann)["held"] == 1000


def test_empty_body_and_explicit_amount_are_different_bodies(world):
    held = authorize(world.ann, "ben", 2000)
    key = new_key()
    path = f"/authorizations/{held['authorization_id']}/capture"
    expect(world.ben.post(path, {}, key=key), 201)
    expect(world.ben.post(path, {"amount": 2000}, key=key), 409, "idempotency_key_reuse")


def test_replay_returns_the_original_payment_and_moves_nothing(world):
    held = authorize(world.ann, "ben", 2000)
    key = new_key()
    path = f"/authorizations/{held['authorization_id']}/capture"
    first = expect(world.ben.post(path, {"amount": 800}, key=key), 201).json()
    again = expect(world.ben.post(path, {"amount": 800}, key=key), 200).json()
    assert again == first
    assert me(world.ben)["total"] == 3300 and me(world.ann)["total"] == 9200
    expect(world.ben.post(path, {"amount": 800}), 400, "missing_idempotency_key")
