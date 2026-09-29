"""Item 39 (boundary): stage 2's authorizations capability is absent."""
from client import expect


def test_authorizations_endpoint_is_absent(world):
    body = {"to_handle": "ben", "amount": 100, "payer_handle": "ben", "note": "hold"}
    resp = world.ann.write("/authorizations", body)
    assert resp.status != 201
    expect(resp, 404, "not_found")
    assert world.ann.balance() == 10000
