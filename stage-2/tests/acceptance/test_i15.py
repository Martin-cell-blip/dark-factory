"""Item 15: idempotency (section 7) on each of the five write paths."""
import json

import pytest

import seed
from client import expect, login, new_key


@pytest.fixture
def op(reset):
    """Ann is a settlement operator; Ben has an open request from Ann."""
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann = login("ann@pocket.test", seed.PASSWORD)
    ben = login("ben@pocket.test", seed.PASSWORD)
    cat = login("cat@pocket.test", seed.PASSWORD)
    return ann, ben, cat


def _paths(ann, ben):
    """(client, path, body, other valid body) for each idempotent path."""
    rq1 = expect(ben.write("/requests", {"payer_handle": "ann", "amount": 10}), 201).json()
    return [
        (ann, "/payments", {"to_handle": "ben", "amount": 10}, {"to_handle": "ben", "amount": 11}),
        (ann, "/requests", {"payer_handle": "ben", "amount": 10},
         {"payer_handle": "ben", "amount": 12}),
        (ann, f"/requests/{rq1['request_id']}/pay", {"visibility": "public"},
         {"visibility": "private"}),
        (ann, "/splits", {"amount": 10, "participant_handles": ["ben"]},
         {"amount": 10, "participant_handles": ["cat"]}),
        (ann, "/settlements", {"transfers": [{"from_handle": "ben", "to_handle": "cat",
                                              "amount": 10}]},
         {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 13}]}),
    ]


def test_missing_or_empty_key_is_400(op):
    ann, ben, _ = op
    for client, path, body, _other in _paths(ann, ben):
        expect(client.post(path, body), 400, "missing_idempotency_key")
        expect(client.post(path, body, key=""), 400, "missing_idempotency_key")
    assert ann.balance() == 10000


def test_key_longer_than_255_is_422(op):
    ann, ben, _ = op
    for client, path, body, _other in _paths(ann, ben):
        expect(client.post(path, body, key="k" * 256), 422, "validation_failed")
    expect(ann.post("/payments", {"to_handle": "ben", "amount": 1}, key="k" * 255), 201)


def test_first_use_201_replay_200_identical_and_no_second_effect(op):
    ann, ben, cat = op
    for client, path, body, other in _paths(ann, ben):
        key = new_key()
        first = expect(client.post(path, body, key=key), 201).json()
        before = [c.balance() for c in (ann, ben, cat)]
        again = expect(client.post(path, body, key=key), 200).json()
        assert again == first
        assert [c.balance() for c in (ann, ben, cat)] == before
        expect(client.post(path, other, key=key), 409, "idempotency_key_reuse")
    assert len(ann.get("/requests?direction=outgoing").json()["requests"]) == 2


def test_body_compared_as_parsed_json(op):
    ann, _, _ = op
    key = new_key()
    first = expect(ann.post("/payments", raw=b'{"to_handle":"ben","amount":10,"note":"n"}',
                            key=key), 201).json()
    spaced = b'{ "note" : "n",\n  "amount" : 10 , "to_handle" : "ben" }'
    assert expect(ann.post("/payments", raw=spaced, key=key), 200).json() == first
    assert ann.balance() == 9990


def test_reuse_after_4xx_is_a_first_use(op):
    ann, _, cat = op
    key = new_key()
    expect(cat.post("/payments", {"to_handle": "ben", "amount": 600}, key=key),
           409, "insufficient_funds")
    expect(ann.write("/payments", {"to_handle": "cat", "amount": 100}), 201)
    expect(cat.post("/payments", {"to_handle": "ben", "amount": 600}, key=key), 201)
    expect(cat.post("/payments", {"to_handle": "ben", "amount": 1}, key=new_key()), 409)
    bad_then_good = new_key()
    expect(ann.post("/payments", {"to_handle": "ben", "amount": 0}, key=bad_then_good), 422)
    expect(ann.post("/payments", {"to_handle": "ben", "amount": 5}, key=bad_then_good), 201)


def test_keys_are_scoped_per_user(op):
    ann, ben, _ = op
    key = new_key()
    a = expect(ann.post("/payments", {"to_handle": "cat", "amount": 7}, key=key), 201).json()
    b = expect(ben.post("/payments", {"to_handle": "cat", "amount": 7}, key=key), 201).json()
    assert a["payment_id"] != b["payment_id"] and b["from_handle"] == "ben"


def test_same_key_and_body_on_another_path_is_new(op):
    ann, _, _ = op
    key = new_key()
    body = {"payer_handle": "ben", "to_handle": "ben", "amount": 5}
    expect(ann.post("/payments", body, key=key), 201)
    expect(ann.post("/requests", body, key=key), 201)
    assert ann.balance() == 9995


def test_claimed_key_resolved_before_validation_and_resource_checks(op):
    ann, ben, _ = op
    key = new_key()
    first = expect(ann.post("/payments", {"to_handle": "ben", "amount": 10}, key=key),
                   201).json()
    expect(ann.post("/payments", {"to_handle": "ben", "amount": "bad"}, key=key),
           409, "idempotency_key_reuse")
    expect(ann.post("/payments", {"to_handle": 5}, key=key), 409, "idempotency_key_reuse")
    expect(ann.post("/payments", {"to_handle": "nobody", "amount": 10}, key=key),
           409, "idempotency_key_reuse")
    assert expect(ann.post("/payments", {"to_handle": "ben", "amount": 10}, key=key),
                  200).json() == first


def test_replay_returns_original_after_resource_changed(op):
    ann, ben, _ = op
    key = new_key()
    created = expect(ann.post("/requests", {"payer_handle": "ben", "amount": 30}, key=key),
                     201).json()
    expect(ann.post(f"/requests/{created['request_id']}/cancel"), 200)
    replay = expect(ann.post("/requests", {"payer_handle": "ben", "amount": 30}, key=key),
                    200).json()
    assert replay == created and replay["status"] == "pending"
    [listed] = ann.get("/requests").json()["requests"][:1]
    assert listed["status"] == "cancelled"
    assert len(ann.get("/requests?direction=outgoing").json()["requests"]) == 1


def test_replay_of_a_settlement_and_a_split_changes_nothing(op):
    ann, ben, cat = op
    key = new_key()
    body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 100}]}
    first = expect(ann.post("/settlements", body, key=key), 201).json()
    expect(ann.post("/settlements", json.loads(json.dumps(body)), key=key), 200)
    assert ben.balance() == 2400 and cat.balance() == 600
    split_key = new_key()
    split = {"amount": 30, "participant_handles": ["ann", "ben", "cat"]}
    expect(ann.post("/splits", split, key=split_key), 201)
    expect(ann.post("/splits", split, key=split_key), 200)
    assert len(ann.get("/requests").json()["requests"]) == 2
    assert first["payments"][0]["amount"] == 100
