"""Item 5: amount rules on every endpoint that takes amount."""
import pytest

import seed
from client import expect, login

BAD = [True, False, "1000", None, 10.5, 0, -5, 0.0, 1000000001, 1e10, [], {}]
ENDPOINTS = [
    ("/payments", lambda amount: {"to_handle": "ben", "amount": amount}),
    ("/requests", lambda amount: {"payer_handle": "ben", "amount": amount}),
    ("/splits", lambda amount: {"amount": amount, "participant_handles": ["ann", "ben"]}),
    ("/settlements", lambda amount: {"transfers": [{"from_handle": "ann", "to_handle": "ben",
                                                    "amount": amount}]}),
]


@pytest.fixture
def operator(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    return login("ann@pocket.test", seed.PASSWORD)


@pytest.mark.parametrize("raw", [b"1000", b"1000.0", b"1e3", b"1E3", b"10e2"])
def test_integral_spellings_are_the_same_amount(world, raw):
    body = b'{"to_handle": "ben", "amount": ' + raw + b"}"
    resp = expect(world.ann.write("/payments", raw=body), 201)
    assert resp.json()["amount"] == 1000
    assert world.ben.balance() == 3500


@pytest.mark.parametrize("value", BAD, ids=repr)
def test_invalid_amounts_are_422_everywhere(operator, value):
    for path, make in ENDPOINTS:
        expect(operator.write(path, make(value)), 422, "validation_failed")
    assert operator.balance() == 10000


def test_bounds_are_inclusive(operator):
    for path, make in ENDPOINTS:
        expect(operator.write(path, make(1)), 201)
    expect(operator.write("/requests", {"payer_handle": "ben", "amount": 1000000000}), 201)
    expect(operator.write("/splits", {"amount": 1000000000,
                                      "participant_handles": ["ben"]}), 201)
