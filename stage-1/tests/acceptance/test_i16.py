"""Item 16: concurrent identical requests with one unused key take effect once."""
import pytest

import seed
from burst import burst, statuses
from client import expect, login, new_key


@pytest.fixture
def parties(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    return tuple(login(f"{h}@pocket.test", seed.PASSWORD) for h in ("ann", "ben", "cat"))


def _race(client, path, body, copies=20):
    key = new_key()
    responses = burst([lambda: client.post(path, body, key=key)] * copies)
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(200) == copies - 1, codes
    bodies = [r.json() for r in responses]
    assert all(b == bodies[0] for b in bodies)
    return bodies[0]


def test_payments(parties):
    ann, ben, _ = parties
    _race(ann, "/payments", {"to_handle": "ben", "amount": 100})
    assert ann.balance() == 9900 and ben.balance() == 2600


def test_requests(parties):
    ann, ben, _ = parties
    _race(ann, "/requests", {"payer_handle": "ben", "amount": 100})
    assert len(ben.get("/requests").json()["requests"]) == 1


def test_request_pay(parties):
    ann, ben, _ = parties
    rq = expect(ben.write("/requests", {"payer_handle": "ann", "amount": 300}), 201).json()
    payment = _race(ann, f"/requests/{rq['request_id']}/pay", {})
    assert payment["request_id"] == rq["request_id"]
    assert ann.balance() == 9700 and ben.balance() == 2800


def test_splits(parties):
    ann, ben, cat = parties
    _race(ann, "/splits", {"amount": 90, "participant_handles": ["ann", "ben", "cat"]})
    assert len(ann.get("/requests").json()["requests"]) == 2


def test_settlements(parties):
    ann, ben, cat = parties
    _race(ann, "/settlements", {"transfers": [{"from_handle": "ben", "to_handle": "cat",
                                               "amount": 250}]})
    assert ben.balance() == 2250 and cat.balance() == 750
