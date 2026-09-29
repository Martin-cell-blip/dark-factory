"""Item 25: POST /splits errors."""
import pytest

from client import expect


@pytest.mark.parametrize("amount", [0, -1, 1.5, "10", None, True, 1000000001])
def test_invalid_amount(world, amount):
    expect(world.ann.write("/splits", {"amount": amount, "participant_handles": ["ben"]}),
           422, "validation_failed")


@pytest.mark.parametrize("handles", [[], ["ben", "ben"], ["ann", "cat", "ann"]])
def test_empty_or_duplicate_participants(world, handles):
    expect(world.ann.write("/splits", {"amount": 10, "participant_handles": handles}),
           422, "validation_failed")


def test_note_too_long(world):
    expect(world.ann.write("/splits", {"amount": 10, "participant_handles": ["ben"],
                                       "note": "n" * 201}), 422, "validation_failed")


def test_any_unknown_handle_creates_nothing(world):
    expect(world.ann.write("/splits", {"amount": 10, "participant_handles":
                                       ["ben", "ghost", "cat"]}), 404, "not_found")
    assert world.ann.get("/requests").json()["requests"] == []
