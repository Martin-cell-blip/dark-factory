"""Item 36 (boundary): stage 3's statement capability is absent."""
from client import expect


def test_statement_is_absent(world):
    resp = world.ann.get("/statement")
    assert resp.status != 200
    expect(resp, 404, "not_found")
