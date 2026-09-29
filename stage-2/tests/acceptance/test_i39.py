"""Item 39 was stage 1's boundary (no authorizations). Stage 2 adds them, so the check
now confirms the capability is present and that a hold moves no money."""
from client import expect


def test_authorizations_endpoint_is_present(world):
    body = {"to_handle": "ben", "amount": 100, "note": "hold"}
    resp = expect(world.ann.write("/authorizations", body), 201)
    assert resp.json()["status"] == "open"
    assert world.ann.balance() == 10000
