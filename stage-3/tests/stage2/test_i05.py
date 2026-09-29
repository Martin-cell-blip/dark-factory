"""Item 5: POST /authorizations errors; an open authorisation is not a feed item."""
import pytest

from client import expect
from holdfx import authorize, me


def test_available_below_amount(world):
    authorize(world.cat, "ann", 400)
    expect(world.cat.write("/authorizations", {"to_handle": "ann", "amount": 101}),
           409, "insufficient_funds")
    assert me(world.cat)["held"] == 400


@pytest.mark.parametrize("amount", [0, -1, 1.5, "10", None, True, 1000000001])
def test_invalid_amount(world, amount):
    expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": amount}),
           422, "validation_failed")


def test_self_note_visibility_unknown(world):
    expect(world.ann.write("/authorizations", {"to_handle": "ann", "amount": 5}),
           422, "self_payment")
    expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 5,
                                               "note": "x" * 201}), 422, "validation_failed")
    expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 5,
                                               "visibility": "friends"}),
           422, "validation_failed")
    expect(world.ann.write("/authorizations", {"to_handle": "ghost", "amount": 5}),
           404, "not_found")
    expect(world.ann.write("/authorizations", {"amount": 5}), 422, "validation_failed")
    expect(world.ann.write("/authorizations", {"to_handle": 5, "amount": 5}),
           400, "malformed_request")
    assert me(world.ann)["held"] == 0


def test_open_authorization_is_never_an_activity_item(world):
    authorize(world.ann, "ben", 700, visibility="public")
    for client in world.everyone:
        assert expect(client.get("/activity"), 200).json()["payments"] == []
