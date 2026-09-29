"""Item 30: who may submit POST /settlements."""
import pytest

import seed
from client import expect, login, request

BODY = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 10}]}


@pytest.fixture
def op(reset):
    reset(seed.fixture(settlement_operator_ids=["u_cat"]))
    return {h: login(f"{h}@pocket.test", seed.PASSWORD) for h in ("ann", "ben", "cat")}


def test_no_token_is_401(op):
    expect(request("POST", "/settlements", BODY, key="k"), 401, "unauthenticated")


def test_non_operator_is_403(op):
    expect(op["ann"].write("/settlements", BODY), 403, "forbidden")
    expect(op["ben"].write("/settlements", BODY), 403, "forbidden")
    assert op["ben"].balance() == 2500


def test_operator_needs_a_key(op):
    expect(op["cat"].post("/settlements", BODY), 400, "missing_idempotency_key")
    expect(op["cat"].write("/settlements", BODY), 201)


def test_operator_gains_no_access_to_others_requests_or_private_items(op):
    ann, ben, cat = op["ann"], op["ben"], op["cat"]
    rq = expect(ann.write("/requests", {"payer_handle": "ben", "amount": 5}), 201).json()
    expect(ann.write("/payments", {"to_handle": "ben", "amount": 5, "visibility": "private"}),
           201)
    assert cat.get("/requests").json()["requests"] == []
    assert cat.get("/activity").json()["payments"] == []
    expect(cat.write(f"/requests/{rq['request_id']}/pay", {}), 403, "forbidden")
    expect(cat.post(f"/requests/{rq['request_id']}/decline"), 403, "forbidden")
    expect(cat.post(f"/requests/{rq['request_id']}/cancel"), 403, "forbidden")


def test_operators_from_fixture_only(reset):
    reset(seed.fixture())
    cat = login("cat@pocket.test", seed.PASSWORD)
    expect(cat.write("/settlements", BODY), 403, "forbidden")
