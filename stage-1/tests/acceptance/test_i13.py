"""Item 13: POST /payments errors leave no trace."""
import pytest

import seed
from client import balances_sum, expect, login


def _no_trace(world):
    assert [c.balance() for c in world.everyone] == [10000, 2500, 500]
    for viewer in world.everyone:
        assert viewer.get("/activity").json()["payments"] == []


def test_insufficient_funds(world):
    expect(world.cat.write("/payments", {"to_handle": "ben", "amount": 501}),
           409, "insufficient_funds")
    _no_trace(world)


def test_self_payment(world):
    expect(world.ann.write("/payments", {"to_handle": "ann", "amount": 5}), 422, "self_payment")
    _no_trace(world)


@pytest.mark.parametrize("note", ["x" * 201, None, 5, ["a"], {"a": 1}, True])
def test_bad_note(world, note):
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 5, "note": note}),
           422, "validation_failed")
    _no_trace(world)


def test_note_of_200_is_fine(world):
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 5, "note": "é" * 200}),
           201)


@pytest.mark.parametrize("visibility", ["friends", "PUBLIC", "", None, 1, True])
def test_bad_visibility(world, visibility):
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 5,
                                         "visibility": visibility}), 422, "validation_failed")
    _no_trace(world)


@pytest.mark.parametrize("handle", ["nobody", "", "ANN", "ann "])
def test_unknown_handle(world, handle):
    expect(world.ann.write("/payments", {"to_handle": handle, "amount": 5}), 404, "not_found")
    _no_trace(world)
    assert balances_sum(world.everyone) == world.total


EMOJI = "\U0001f600"


def test_note_length_counts_code_points_everywhere(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann = login("ann@pocket.test", seed.PASSWORD)
    for note, status in ((EMOJI * 200, 201), (EMOJI * 201, 422), ("e\u0301" * 100, 201),
                         ("e\u0301" * 100 + "x", 422)):
        bodies = [("/payments", {"to_handle": "ben", "amount": 1, "note": note}),
                  ("/requests", {"payer_handle": "ben", "amount": 1, "note": note}),
                  ("/splits", {"amount": 2, "participant_handles": ["ben"], "note": note}),
                  ("/settlements", {"transfers": [{"from_handle": "ben", "to_handle": "cat",
                                                   "amount": 1, "note": note}]})]
        for path, body in bodies:
            resp = expect(ann.write(path, body), status)
            if status == 422:
                assert resp.json()["error"]["code"] == "validation_failed"
