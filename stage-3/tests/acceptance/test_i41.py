"""Item 41: an export imported into a fresh container on another port restores everything.

The second instance is read from POCKETFUL_URL_B (see RUN.md). Without it the test fails.
"""
import os

import pytest

import seed
from client import BASE_URL, expect, login, new_key, request

SECOND = os.environ.get("POCKETFUL_URL_B")


@pytest.fixture
def second():
    assert SECOND, "set POCKETFUL_URL_B to a second container on a different port (RUN.md)"
    assert SECOND.rstrip("/") != BASE_URL.rstrip("/"), "the second instance must be distinct"
    expect(request("GET", "/health", base=SECOND), 200)
    return SECOND


def test_export_moves_to_a_fresh_container(reset, second):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann = login("ann@pocket.test", seed.PASSWORD)
    ben = login("ben@pocket.test", seed.PASSWORD)
    key = new_key()
    payment = expect(ann.post("/payments", {"to_handle": "ben", "amount": 250, "note": "rent"},
                              key=key), 201).json()
    rq = expect(ben.write("/requests", {"payer_handle": "ann", "amount": 40}), 201).json()
    settle_key = new_key()
    settle_body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 5}]}
    settlement = expect(ann.post("/settlements", settle_body, key=settle_key), 201).json()
    document = expect(request("GET", "/_test/export"), 200).json()
    views = {c.token: (c.get("/me").json(), c.get("/activity").json(),
                       c.get("/requests").json()) for c in (ann, ben)}

    expect(request("POST", "/_test/reset", seed.fixture(users=[seed.user("zed", 1)]),
                   base=second), 204)
    expect(request("POST", "/_test/import", document, base=second, timeout=15), 204)

    for token, (me, activity, requests) in views.items():
        assert expect(request("GET", "/me", token=token, base=second), 200).json() == me
        assert request("GET", "/activity", token=token, base=second).json() == activity
        assert request("GET", "/requests", token=token, base=second).json() == requests
    expect(request("POST", "/auth/login", {"email": "ben@pocket.test",
                                           "password": seed.PASSWORD}, base=second), 200)
    replay = request("POST", "/payments", {"to_handle": "ben", "amount": 250, "note": "rent"},
                     token=ann.token, key=key, base=second)
    assert expect(replay, 200).json() == payment
    replay = request("POST", "/settlements", settle_body, token=ann.token, key=settle_key,
                     base=second)
    assert expect(replay, 200).json() == settlement
    paid = request("POST", f"/requests/{rq['request_id']}/pay", {}, token=ann.token,
                   key=new_key(), base=second)
    assert expect(paid, 201).json()["request_id"] == rq["request_id"]
    assert ann.balance() == views[ann.token][0]["balance"], "the source is untouched"
