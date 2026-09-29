"""Item 2: GET /me gains total, available and held."""
from client import expect
from holdfx import authorize, me


def test_shape_without_holds(world):
    body = expect(world.ann.get("/me"), 200).json()
    assert list(body) == ["user_id", "display_name", "handle", "balance", "total",
                          "available", "held", "currency", "minor_units"]
    assert body["balance"] == body["total"] == body["available"] == 10000
    assert body["held"] == 0


def test_holds_reduce_available_only(world):
    authorize(world.ann, "ben", 1500)
    authorize(world.ann, "cat", 500)
    body = me(world.ann)
    assert body["balance"] == body["total"] == 10000
    assert body["held"] == 2000 and body["available"] == 8000


def test_available_never_negative(world):
    authorize(world.cat, "ann", 500)
    body = me(world.cat)
    assert body["available"] == 0 and body["held"] == 500 and body["total"] == 500
