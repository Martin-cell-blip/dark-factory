"""Holdout: §11 atomic net settlements."""
import pytest

from holdout_client import (assert_error, burst, call, fixture, make_world,
                            new_key, no_5xx, pay, settle, user)


def test_operator_settles_between_wallets_it_is_not_party_to(opworld):
    w = opworld
    r = settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                      {"from_handle": "bob", "to_handle": "cy", "amount": 50}])
    assert r.status == 201, r
    body = r.json()
    assert isinstance(body["settlement_id"], str) and len(body["settlement_id"]) <= 64
    ps = body["payments"]
    assert [(p["from_handle"], p["to_handle"], p["amount"]) for p in ps] == \
        [("ada", "bob", 100), ("bob", "cy", 50)]
    for p in ps:
        assert p["settlement_id"] == body["settlement_id"]
        assert p["request_id"] is None
        assert p["created_at"] == body["committed_at"]
        assert p["note"] == "" and p["visibility"] == "public"
        assert p["currency"] == "EUR"
    bals = w.conserved()
    assert bals == {"ada": 9900, "bob": 2550, "cy": 550, "op": 0}


def test_netting_chain_funded_inside_the_batch(opworld):
    w = opworld
    # op has 0: receives 500 from cy and forwards 500 to ada in the same batch
    r = settle(w.op, [{"from_handle": "op", "to_handle": "ada", "amount": 500},
                      {"from_handle": "cy", "to_handle": "op", "amount": 500}])
    assert r.status == 201, r
    assert w.conserved() == {"ada": 10500, "bob": 2500, "cy": 0, "op": 0}


def test_collective_shortfall_is_409_and_moves_nothing(opworld):
    w = opworld
    before = w.conserved()
    r = settle(w.op, [{"from_handle": "ada", "to_handle": "cy", "amount": 100},
                      {"from_handle": "cy", "to_handle": "bob", "amount": 601}])
    assert_error(r, 409, "insufficient_funds")
    assert w.conserved() == before
    feed = w.ada.get("/activity").json()["payments"]
    assert feed == []


def test_non_operator_403_and_no_token_401(opworld):
    w = opworld
    body = {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]}
    assert_error(w.ada.post("/settlements", body, key=new_key()), 403, "forbidden")
    assert_error(call("POST", "/settlements", body, key=new_key()), 401, "unauthenticated")


def test_operators_default_to_empty():
    w = make_world(fixture())
    r = settle(w.ada, [{"from_handle": "ada", "to_handle": "bob", "amount": 1}])
    assert_error(r, 403, "forbidden")


def test_settlement_requires_idempotency_key(opworld):
    r = opworld.op.post("/settlements", {"transfers": [
        {"from_handle": "ada", "to_handle": "bob", "amount": 1}]})
    assert_error(r, 400, "missing_idempotency_key")


@pytest.mark.parametrize("transfers", [[], None, "x", {"a": 1}, [1], ["x"],
                                       [{"from_handle": "ada", "to_handle": "bob", "amount": 1}] * 33])
def test_malformed_batch_shape_is_422(opworld, transfers):
    r = opworld.op.post("/settlements", {"transfers": transfers}, key=new_key())
    assert_error(r, 422, "validation_failed")


def test_thirty_two_transfers_is_allowed(opworld):
    r = settle(opworld.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 1}] * 32)
    assert r.status == 201, r
    assert len(r.json()["payments"]) == 32
    assert opworld.conserved()["bob"] == 2532


def test_missing_transfers_is_422(opworld):
    assert_error(opworld.op.post("/settlements", {}, key=new_key()), 422, "validation_failed")


@pytest.mark.parametrize("entry", [
    {"from_handle": "ada", "to_handle": "bob", "amount": 0},
    {"from_handle": "ada", "to_handle": "bob", "amount": 1000000001},
    {"from_handle": "ada", "to_handle": "bob", "amount": "5"},
    {"from_handle": "ada", "to_handle": "bob", "amount": True},
    {"from_handle": "ada", "to_handle": "bob", "amount": 1.5},
    {"from_handle": "ada", "to_handle": "bob"},
    {"from_handle": "ada", "to_handle": "bob", "amount": 1, "note": None},
    {"from_handle": "ada", "to_handle": "bob", "amount": 1, "note": "x" * 201},
    {"from_handle": "ada", "to_handle": "bob", "amount": 1, "visibility": "friends"},
])
def test_entry_payment_rules(opworld, entry):
    assert_error(settle(opworld.op, [entry]), 422, "validation_failed")


def test_entry_errors_in_input_order_before_funds(opworld):
    w = opworld
    unknown = {"from_handle": "ada", "to_handle": "nobody", "amount": 1}
    selfp = {"from_handle": "bob", "to_handle": "bob", "amount": 1}
    broke = {"from_handle": "cy", "to_handle": "ada", "amount": 99999}
    assert_error(settle(w.op, [broke, unknown, selfp]), 404, "not_found")
    assert_error(settle(w.op, [broke, selfp, unknown]), 422, "self_payment")
    assert_error(settle(w.op, [unknown, {"from_handle": "ada", "to_handle": "bob", "amount": 0}]),
                 404, "not_found")
    assert_error(settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 0}, unknown]),
                 422, "validation_failed")
    assert_error(settle(w.op, [{"from_handle": "ghost", "to_handle": "bob", "amount": 1}]),
                 404, "not_found")


def test_failed_validation_claims_no_key(opworld):
    w = opworld
    k = new_key()
    assert_error(settle(w.op, [{"from_handle": "ada", "to_handle": "ada", "amount": 1}], key=k),
                 422, "self_payment")
    r = settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 7}], key=k)
    assert r.status == 201, r
    k2 = new_key()
    assert_error(settle(w.op, [{"from_handle": "cy", "to_handle": "bob", "amount": 501}], key=k2),
                 409, "insufficient_funds")
    assert settle(w.op, [{"from_handle": "cy", "to_handle": "bob", "amount": 500}], key=k2).status == 201


def test_replay_returns_original_and_moves_once(opworld):
    w = opworld
    k = new_key()
    t = [{"to_handle": "bob", "amount": 10, "from_handle": "ada", "note": "n", "visibility": "private"}]
    r1 = settle(w.op, t, key=k)
    assert r1.status == 201, r1
    r2 = w.op.post("/settlements", {"transfers": [{"amount": 10, "note": "n", "visibility": "private",
                                                   "from_handle": "ada", "to_handle": "bob"}]}, key=k)
    assert r2.status == 200, r2
    assert r2.json() == r1.json()
    assert w.conserved()["bob"] == 2510
    r3 = settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 11}], key=k)
    assert_error(r3, 409, "idempotency_key_reuse")


def test_members_follow_feed_visibility_and_nonmembers_are_null(opworld):
    w = opworld
    assert pay(w.cy, "ada", 5).json()["settlement_id"] is None
    r = settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 3, "visibility": "private"},
                      {"from_handle": "bob", "to_handle": "ada", "amount": 2}])
    assert r.status == 201, r
    sid = r.json()["settlement_id"]
    cy_feed = w.cy.get("/activity").json()["payments"]
    assert sorted(p["amount"] for p in cy_feed) == [2, 5]
    for p in cy_feed:
        assert "settlement_id" in p
        assert p["settlement_id"] == (sid if p["amount"] == 2 else None)
    ada_feed = w.ada.get("/activity").json()["payments"]
    assert sorted(p["amount"] for p in ada_feed) == [2, 3, 5]
    # operator is not party to the private member: hidden from it
    op_feed = w.op.get("/activity").json()["payments"]
    assert sorted(p["amount"] for p in op_feed) == [2, 5]


def test_operator_gets_no_access_to_others_requests(opworld):
    w = opworld
    rq = w.bob.post("/requests", {"payer_handle": "ada", "amount": 10}, key=new_key()).json()
    assert w.op.get("/requests").json()["requests"] == []
    r = w.op.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key())
    assert r.status in (403, 404), r
    assert w.op.post(f"/requests/{rq['request_id']}/decline", {}).status in (403, 404)
    assert w.op.post(f"/requests/{rq['request_id']}/cancel", {}).status in (403, 404)
    assert w.op.balance() == 0


def test_concurrent_settlements_never_overdraw():
    fx = fixture(users=[user("ada", 1000), user("bob", 0), user("op", 0)], operators=["u_op"])
    w = make_world(fx)
    rs = burst(lambda i: settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 100}]), 50)
    no_5xx(rs)
    ok = [r for r in rs if r.status == 201]
    assert len(ok) == 10, [r.status for r in rs]
    for r in rs:
        if r.status != 201:
            assert_error(r, 409, "insufficient_funds")
    assert w.conserved() == {"ada": 0, "bob": 1000, "op": 0}


def test_concurrent_identical_settlement_replays_once(opworld):
    w = opworld
    k = new_key()
    t = [{"from_handle": "ada", "to_handle": "bob", "amount": 100}]
    rs = burst(lambda i: settle(w.op, t, key=k), 30)
    no_5xx(rs)
    assert sorted(r.status for r in rs) == [200] * 29 + [201], [r.status for r in rs]
    assert len({r.raw for r in rs}) >= 1
    first = [r for r in rs if r.status == 201][0].json()
    assert all(r.json() == first for r in rs)
    assert w.conserved()["bob"] == 2600
