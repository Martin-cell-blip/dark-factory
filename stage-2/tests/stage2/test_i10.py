"""Item 10: POST /authorizations/{id}/void."""
import seed
from client import expect
from holdfx import authorize, capture, me, seeded_hold, signed_in


def test_void_releases_the_hold_and_repeats(world):
    aid = authorize(world.ann, "ben", 1000)["authorization_id"]
    body = expect(world.ann.post(f"/authorizations/{aid}/void"), 200).json()
    assert body["authorization_id"] == aid and body["status"] == "voided"
    assert me(world.ann) == {**me(world.ann), "held": 0, "available": 10000}
    again = expect(world.ann.post(f"/authorizations/{aid}/void"), 200).json()
    assert again["status"] == "voided"
    capture(world.ben, aid, {}, 409, "authorization_not_open")


def test_captured_or_expired_cannot_be_voided(reset):
    reset(seed.fixture(authorizations=[
        seeded_hold("a_exp", "ann", "ben", 100, hours=-1),
        seeded_hold("a_old", "ann", "ben", 100, status="expired", hours=-1)]))
    ann, ben = signed_in("ann", "ben")
    aid = authorize(ann, "ben", 300)["authorization_id"]
    capture(ben, aid)
    for target in (aid, "a_exp", "a_old"):
        expect(ann.post(f"/authorizations/{target}/void"), 409, "authorization_not_open")


def test_only_the_payer_may_void(world):
    aid = authorize(world.ann, "ben", 1000)["authorization_id"]
    expect(world.ben.post(f"/authorizations/{aid}/void"), 403, "forbidden")
    expect(world.cat.post(f"/authorizations/{aid}/void"), 403, "forbidden")
    expect(world.ann.post("/authorizations/a_missing/void"), 404, "not_found")
    assert me(world.ann)["held"] == 1000


def test_void_needs_no_idempotency_key(world):
    aid = authorize(world.ann, "ben", 1000)["authorization_id"]
    expect(world.ann.post(f"/authorizations/{aid}/void"), 200)
