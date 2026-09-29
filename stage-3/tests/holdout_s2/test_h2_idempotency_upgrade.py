"""Holdout: §7 on the two new write paths; export/import incl. the stage-1 -> stage-2 upgrade."""
import time

import pytest

from holdout2_client import (BASE_S1, Client, assert_error, ask, authorize, burst, call,
                            capture, fixture, login, make_world, new_key, no_5xx, pay,
                            reset, settle, user, void)


@pytest.fixture
def paths(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    return {
        "auth": (world.ada, "/authorizations", {"to_handle": "bob", "amount": 100}),
        "capture": (world.bob, f"/authorizations/{aid}/capture", {"amount": 100, "final": False}),
    }


@pytest.mark.parametrize("name", ["auth", "capture"])
def test_key_rules(world, paths, name):
    c, path, body = paths[name]
    assert_error(c.post(path, body), 400, "missing_idempotency_key")
    assert_error(c.post(path, body, key=""), 400, "missing_idempotency_key")
    assert_error(c.post(path, body, key="k" * 256), 422, "validation_failed")
    k = new_key()
    r1 = c.post(path, body, key=k)
    assert r1.status == 201, r1
    r2 = c.post(path, dict(reversed(list(body.items()))), key=k)
    assert r2.status == 200 and r2.json() == r1.json()
    assert_error(c.post(path, {**body, "amount": 101}, key=k), 409, "idempotency_key_reuse")
    assert_error(c.post(path, {**body, "amount": -1}, key=k), 409, "idempotency_key_reuse")
    world.conserved()


@pytest.mark.parametrize("name", ["auth", "capture"])
def test_concurrent_identical_one_201(world, paths, name):
    c, path, body = paths[name]
    k = new_key()
    rs = burst(lambda i: c.post(path, body, key=k), 30)
    no_5xx(rs)
    assert sorted(r.status for r in rs) == [200] * 29 + [201], [r.status for r in rs]
    first = [r for r in rs if r.status == 201][0].json()
    assert all(r.json() == first for r in rs)
    me = world.ada.me()
    if name == "auth":
        assert me["held"] == 1100
    else:
        assert me["held"] == 900 and world.bob.me()["total"] == 2600
    world.conserved()


def test_key_after_4xx_is_first_use_and_per_user(world):
    k = new_key()
    assert_error(authorize(world.cy, "bob", 501, key=k), 409, "insufficient_funds")
    assert authorize(world.cy, "bob", 500, key=k).status == 201
    assert authorize(world.ada, "bob", 500, key=k).status == 201  # other user, same key
    assert world.ada.me()["held"] == 500 and world.cy.me()["held"] == 500


def test_final_false_changes_body_equality(world):
    aid = authorize(world.ada, "bob", 2000).json()["authorization_id"]
    k = new_key()
    assert capture(world.bob, aid, {"amount": 700, "final": False}, key=k).status == 201
    assert_error(capture(world.bob, aid, {"amount": 700}, key=k), 409, "idempotency_key_reuse")


def test_capture_empty_vs_explicit_amount_is_reuse(world):
    aid = authorize(world.ada, "bob", 2000).json()["authorization_id"]
    k = new_key()
    assert capture(world.bob, aid, {}, key=k).status == 201
    assert_error(capture(world.bob, aid, {"amount": 2000}, key=k), 409, "idempotency_key_reuse")


def test_final_field_changes_body_equality(world):
    aid = authorize(world.ada, "bob", 2000).json()["authorization_id"]
    k = new_key()
    assert capture(world.bob, aid, {"amount": 700}, key=k).status == 201
    assert_error(capture(world.bob, aid, {"amount": 700, "final": True}, key=k),
                 409, "idempotency_key_reuse")


def test_capture_replay_after_close_is_200_original(world):
    aid = authorize(world.ada, "bob", 2000).json()["authorization_id"]
    k = new_key()
    r1 = capture(world.bob, aid, {"amount": 300, "final": False}, key=k)
    void(world.ada, aid)
    r2 = capture(world.bob, aid, {"amount": 300, "final": False}, key=k)
    assert r2.status == 200 and r2.json() == r1.json()
    assert world.bob.me()["total"] == 2800


def test_capture_replay_after_expiry_is_200_original():
    w = make_world(fixture(ttl=1))
    aid = authorize(w.ada, "bob", 2000).json()["authorization_id"]
    k = new_key()
    r1 = capture(w.bob, aid, {"amount": 300, "final": False}, key=k)
    time.sleep(1.5)
    r2 = capture(w.bob, aid, {"amount": 300, "final": False}, key=k)
    assert r2.status == 200 and r2.json() == r1.json()
    w.conserved()


def test_authorization_replay_after_void_returns_original(world):
    k = new_key()
    r1 = authorize(world.ada, "bob", 100, key=k)
    void(world.ada, r1.json()["authorization_id"])
    r2 = authorize(world.ada, "bob", 100, key=k)
    assert r2.status == 200 and r2.json() == r1.json() and r2.json()["status"] == "open"
    assert world.ada.me()["held"] == 0


def test_stage2_export_import_roundtrip(world):
    a = authorize(world.ada, "bob", 1000).json()
    kc = new_key()
    p = capture(world.bob, a["authorization_id"], {"amount": 250, "final": False}, key=kc).json()
    b = authorize(world.cy, "ada", 200).json()
    void(world.cy, b["authorization_id"])
    snap = call("GET", "/_test/export").json()
    before = {h: c.me() for h, c in world.c.items()}
    lists = {h: c.get("/authorizations").json() for h, c in world.c.items()}
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    assert {h: c.me() for h, c in world.c.items()} == before
    assert {h: c.get("/authorizations").json() for h, c in world.c.items()} == lists
    r = capture(world.bob, a["authorization_id"], {"amount": 250, "final": False}, key=kc)
    assert r.status == 200 and r.json() == p
    assert capture(world.bob, a["authorization_id"]).json()["amount"] == 750
    world.conserved()


def test_expiry_survives_import():
    w = make_world(fixture(ttl=2))
    aid = authorize(w.ada, "bob", 1000).json()["authorization_id"]
    snap = call("GET", "/_test/export").json()
    time.sleep(2.5)
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    assert w.ada.me()["held"] == 0
    assert w.ada.get("/authorizations").json()["authorizations"][0]["status"] == "expired"
    assert_error(capture(w.bob, aid), 409, "authorization_expired")


@pytest.fixture
def stage1():
    assert BASE_S1, "set POCKETFUL_STAGE1_URL to a running stage-1 service of this team"
    return BASE_S1


def test_stage1_export_imports_into_stage2(stage1):
    fx = fixture(operators=["u_ada"])
    reset(fx, base=stage1)
    tok = {u["handle"]: login(u["email"], base=stage1) for u in fx["users"]}
    ada1 = Client(tok["ada"], stage1)
    k = new_key()
    p = pay(ada1, "bob", 123, key=k, note="pre-upgrade", visibility="private").json()
    rq = ask(Client(tok["bob"], stage1), "ada", 40).json()
    s = settle(ada1, [{"from_handle": "bob", "to_handle": "cy", "amount": 5}]).json()
    k_fail = new_key()
    assert_error(pay(Client(tok["cy"], stage1), "ada", 99999, key=k_fail), 409, "insufficient_funds")
    snap = call("GET", "/_test/export", base=stage1).json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    ada, bob, cy = Client(tok["ada"]), Client(tok["bob"]), Client(tok["cy"])
    me = ada.me()
    assert (me["total"], me["available"], me["held"], me["balance"]) == (9877, 9877, 0, 9877)
    r = pay(ada, "bob", 123, key=k, note="pre-upgrade", visibility="private")
    assert r.status == 200, r
    assert r.json() == p, "S2-D8: a stage-1 stored response replays exactly, no added fields"
    assert pay(cy, "ada", 1, key=k_fail).status == 201
    paid = ada.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key())
    assert paid.status == 201, paid
    feed = {x["payment_id"]: x for x in cy.get("/activity").json()["payments"]}
    assert feed[s["payments"][0]["payment_id"]]["settlement_id"] == s["settlement_id"]
    assert login("bob@example.com")
    assert authorize(ada, "bob", 100).status == 201
    assert settle(ada, [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]).status == 201
    tot = sum(c.me()["total"] for c in (ada, bob, cy))
    assert tot == 13000
