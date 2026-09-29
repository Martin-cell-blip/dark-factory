"""Item 31: POST /settlements validation."""
import pytest

import seed
from client import expect, login, new_key


@pytest.fixture
def op(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    return login("ann@pocket.test", seed.PASSWORD), login("ben@pocket.test", seed.PASSWORD)


def _t(frm="ben", to="cat", amount=10, **extra):
    return {"from_handle": frm, "to_handle": to, "amount": amount, **extra}


def _untouched(ann, ben):
    assert ann.balance() == 10000 and ben.balance() == 2500
    assert ann.get("/activity").json()["payments"] == []


@pytest.mark.parametrize("body", [
    {}, {"transfers": []}, {"transfers": [_t()] * 33}, {"transfers": "x"},
    {"transfers": {"a": 1}}, {"transfers": [1]}, {"transfers": [None]},
    {"transfers": [{"to_handle": "cat", "amount": 1}]},
    {"transfers": [{"from_handle": "ben", "amount": 1}]},
    {"transfers": [{"from_handle": 5, "to_handle": "cat", "amount": 1}]},
])
def test_malformed_batch_shape_is_422(op, body):
    ann, ben = op
    expect(ann.write("/settlements", body), 422, "validation_failed")
    _untouched(ann, ben)


def test_thirty_two_is_the_maximum(op):
    ann, _ = op
    expect(ann.write("/settlements", {"transfers": [_t(amount=1)] * 32}), 201)


@pytest.mark.parametrize("entry", [
    _t(amount=0), _t(amount="5"), _t(amount=1.5), _t(note=None), _t(note="n" * 201),
    _t(visibility="friends"), _t(visibility=None),
])
def test_entry_follows_payment_rules(op, entry):
    ann, ben = op
    expect(ann.write("/settlements", {"transfers": [_t(), entry]}), 422, "validation_failed")
    _untouched(ann, ben)


def test_unknown_handle_and_self_transfer(op):
    ann, ben = op
    expect(ann.write("/settlements", {"transfers": [_t(to="ghost")]}), 404, "not_found")
    expect(ann.write("/settlements", {"transfers": [_t(frm="ghost")]}), 404, "not_found")
    expect(ann.write("/settlements", {"transfers": [_t(to="ben")]}), 422, "self_payment")
    _untouched(ann, ben)


def test_entry_errors_in_input_order_before_funds(op):
    ann, ben = op
    too_much = _t(amount=999999)
    expect(ann.write("/settlements", {"transfers": [too_much, _t(to="ghost"), _t(to="ben")]}),
           404, "not_found")
    expect(ann.write("/settlements", {"transfers": [too_much, _t(to="ben"), _t(to="ghost")]}),
           422, "self_payment")
    expect(ann.write("/settlements", {"transfers": [_t(amount=0), _t(to="ghost")]}),
           422, "validation_failed")
    expect(ann.write("/settlements", {"transfers": [too_much]}), 409, "insufficient_funds")
    _untouched(ann, ben)


def test_defaults_and_unknown_fields(op):
    ann, _ = op
    body = expect(ann.write("/settlements", {"transfers": [_t(colour="red")], "extra": 1}),
                  201).json()
    [payment] = body["payments"]
    assert payment["note"] == "" and payment["visibility"] == "public"


def test_failed_validation_claims_no_key(op):
    ann, ben = op
    key = new_key()
    expect(ann.post("/settlements", {"transfers": [_t(amount=0)]}, key=key), 422)
    expect(ann.post("/settlements", {"transfers": [_t()]}, key=key), 201)
    assert ben.balance() == 2490
