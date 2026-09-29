"""Item 11: GET /me shape (stage 2 adds total, available and held)."""
from client import expect


def test_me_shape(world):
    body = expect(world.ben.get("/me"), 200).json()
    assert body == {"user_id": "u_ben", "display_name": "Ben", "handle": "ben",
                    "balance": 2500, "total": 2500, "available": 2500, "held": 0,
                    "currency": "EUR", "minor_units": 2}
