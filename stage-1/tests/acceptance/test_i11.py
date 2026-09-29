"""Item 11: GET /me shape."""
from client import expect


def test_me_shape(world):
    body = expect(world.ben.get("/me"), 200).json()
    assert body == {"user_id": "u_ben", "display_name": "Ben", "handle": "ben",
                    "balance": 2500, "currency": "EUR", "minor_units": 2}
