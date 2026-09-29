"""Holdout: §7 idempotency and §1 invariants under concurrency."""
import pytest

from holdout_client import (assert_error, ask, burst, fixture, make_world,
                            new_key, no_5xx, pay, user)


def _paths(w):
    rq = ask(w.bob, "ada", 10).json()["request_id"]
    return [
        (w.ada, "/payments", {"to_handle": "bob", "amount": 10}),
        (w.bob, "/requests", {"payer_handle": "ada", "amount": 10}),
        (w.ada, f"/requests/{rq}/pay", {"visibility": "private"}),
        (w.ada, "/splits", {"amount": 30, "participant_handles": ["ada", "bob", "cy"]}),
    ]


@pytest.mark.parametrize("idx", range(4))
def test_concurrent_identical_requests_one_201(world, idx):
    c, path, body = _paths(world)[idx]
    k = new_key()
    rs = burst(lambda i: c.post(path, body, key=k), 30)
    no_5xx(rs)
    assert sorted(r.status for r in rs) == [200] * 29 + [201], [r.status for r in rs]
    first = [r for r in rs if r.status == 201][0].json()
    assert all(r.json() == first for r in rs)
    world.conserved()
    if path == "/requests":
        out = world.bob.get("/requests?direction=outgoing&limit=200").json()["requests"]
        assert len(out) == 2  # the one from _paths plus exactly one here
    if path == "/splits":
        assert len(world.cy.get("/requests").json()["requests"]) == 1
    if path == "/payments":
        assert world.bob.balance() == 2510


@pytest.mark.parametrize("idx", range(4))
def test_key_resolved_before_validation(world, idx):
    c, path, body = _paths(world)[idx]
    k = new_key()
    assert c.post(path, body, key=k).status == 201
    bad = {**body, "amount": -5} if "amount" in body else {"visibility": "nope"}
    assert_error(c.post(path, bad, key=k), 409, "idempotency_key_reuse")


@pytest.mark.parametrize("idx", range(4))
def test_empty_and_oversize_keys(world, idx):
    c, path, body = _paths(world)[idx]
    assert_error(c.post(path, body, key=""), 400, "missing_idempotency_key")
    assert_error(c.post(path, body), 400, "missing_idempotency_key")
    assert_error(c.post(path, body, key="k" * 256), 422, "validation_failed")
    assert c.post(path, body, key="k" * 255).status == 201


def test_replay_ignores_key_order_and_whitespace(world):
    k = new_key()
    r1 = world.ada.post("/payments", raw='{"to_handle":"bob","amount":10,"note":"x"}', key=k)
    assert r1.status == 201, r1
    r2 = world.ada.post("/payments", raw='{ "note" : "x",\n "amount": 1e1, "to_handle":"bob" }', key=k)
    assert r2.status == 200, r2
    assert r2.json() == r1.json()
    assert world.bob.balance() == 2510


def test_replay_after_request_cancelled_returns_original(world):
    k = new_key()
    r1 = ask(world.bob, "ada", 50, key=k)
    rid = r1.json()["request_id"]
    assert world.bob.post(f"/requests/{rid}/cancel", {}).status == 200
    r2 = ask(world.bob, "ada", 50, key=k)
    assert r2.status == 200 and r2.json() == r1.json()
    assert r2.json()["status"] == "pending"


def test_pay_replay_after_funds_gone_is_still_200(world):
    rid = ask(world.bob, "ada", 9000).json()["request_id"]
    k = new_key()
    r1 = world.ada.post(f"/requests/{rid}/pay", {}, key=k)
    assert r1.status == 201, r1
    r2 = world.ada.post(f"/requests/{rid}/pay", {}, key=k)
    assert r2.status == 200 and r2.json() == r1.json()
    assert world.ada.balance() == 1000
    req = [q for q in world.bob.get("/requests").json()["requests"] if q["request_id"] == rid][0]
    assert req["status"] == "paid" and req["payment_id"] == r1.json()["payment_id"]
    assert r1.json()["request_id"] == rid and r1.json()["settlement_id"] is None


def test_same_key_other_user_is_independent(world):
    k = new_key()
    assert pay(world.ada, "cy", 1, key=k).status == 201
    assert pay(world.bob, "cy", 1, key=k).status == 201
    assert world.cy.balance() == 502


def test_concurrent_pays_with_different_keys_move_money_once(world):
    rid = ask(world.bob, "ada", 100).json()["request_id"]
    rs = burst(lambda i: world.ada.post(f"/requests/{rid}/pay", {}, key=new_key()), 50)
    no_5xx(rs)
    assert sum(r.status == 201 for r in rs) == 1, [r.status for r in rs]
    for r in rs:
        if r.status != 201:
            assert_error(r, 409, "request_not_pending")
    assert world.conserved()["bob"] == 2600


def test_pay_versus_cancel_race_leaves_one_outcome(world):
    for _ in range(10):
        w = make_world()
        rid = ask(w.bob, "ada", 100).json()["request_id"]

        def act(i):
            if i % 2:
                return w.ada.post(f"/requests/{rid}/pay", {}, key=new_key())
            return w.bob.post(f"/requests/{rid}/cancel", {})
        rs = burst(act, 20)
        no_5xx(rs)
        req = w.bob.get("/requests").json()["requests"][0]
        paid = sum(r.status == 201 for r in rs)
        bals = w.conserved()
        if req["status"] == "paid":
            assert paid == 1 and bals["bob"] == 2600
        else:
            assert req["status"] == "cancelled" and paid == 0 and bals["bob"] == 2500


def test_many_spenders_one_wallet_never_overdraws():
    for _ in range(10):
        w = make_world(fixture(users=[user("ada", 1000), user("bob", 0), user("cy", 0)]))
        rs = burst(lambda i: pay(w.ada, "bob" if i % 2 else "cy", 70), 50)
        no_5xx(rs)
        ok = sum(r.status == 201 for r in rs)
        assert ok == 14, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert_error(r, 409, "insufficient_funds")
        bals = w.conserved()
        assert bals["ada"] == 1000 - 14 * 70


def test_crossing_payments_conserve(world):
    def act(i):
        a, b = [(world.ada, "bob"), (world.bob, "cy"), (world.cy, "ada")][i % 3]
        return pay(a, b, 37)
    rs = burst(act, 50)
    no_5xx(rs)
    world.conserved()
