"""Holdout: §10 export and import."""
import json

import pytest

from holdout_client import (BASE_B, Client, assert_error, ask, call, fixture,
                            login, make_world, new_key, pay, reset, settle, user)


def export(base=None):
    r = call("GET", "/_test/export", base=base)
    assert r.status == 200, r
    body = r.json()
    assert body["track"] == "pocketful" and body["format_version"] == 1
    assert isinstance(body["state"], dict)
    return body


def do_import(body, base=None):
    return call("POST", "/_test/import", body, base=base, timeout=15)


def _populate(w):
    k_pay = new_key()
    p = pay(w.ada, "bob", 123, key=k_pay, note="ünï 🎉", visibility="private")
    assert p.status == 201
    k_fail = new_key()
    assert_error(pay(w.cy, "ada", 99999, key=k_fail), 409, "insufficient_funds")
    rq = ask(w.bob, "cy", 40)
    return p, k_pay, k_fail, rq.json()


def test_import_restores_tokens_replays_and_failed_keys(opworld):
    w = opworld
    p, k_pay, k_fail, rq = _populate(w)
    s = settle(w.op, [{"from_handle": "bob", "to_handle": "cy", "amount": 5}])
    assert s.status == 201
    snap = export()
    bals = w.conserved()
    feed_ada = w.ada.get("/activity").json()
    # diverge, then import
    assert pay(w.ada, "cy", 1000).status == 201
    reset(fixture(users=[user("zed", 1)]))
    assert do_import(snap).status == 204
    assert w.conserved() == bals  # old tokens still valid
    assert w.ada.get("/activity").json() == feed_ada
    r = pay(w.ada, "bob", 123, key=k_pay, note="ünï 🎉", visibility="private")
    assert r.status == 200 and r.json() == p.json()
    assert pay(w.cy, "ada", 1, key=k_fail).status == 201
    assert w.cy.get("/requests").json()["requests"][0]["request_id"] == rq["request_id"]
    assert login("ada@example.com")
    # operator permission preserved
    assert settle(w.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 1}]).status == 201
    assert_error(call("POST", "/auth/login", {"email": "zed@example.com", "password": "correct horse"}),
                 401, "unauthenticated")
    members = [x for x in w.cy.get("/activity").json()["payments"]
               if x["settlement_id"] == s.json()["settlement_id"]]
    assert [m["payment_id"] for m in members] == [m["payment_id"] for m in s.json()["payments"]]


def test_import_is_replacement_and_repeatable(world):
    pay(world.ada, "bob", 10)
    snap = export()
    for _ in range(3):
        assert do_import(snap).status == 204
    assert len(world.ada.get("/activity").json()["payments"]) == 1
    world.conserved()


def test_import_removes_destination_credentials(world):
    snap = export()
    other = make_world(fixture(users=[user("zed", 5)]))
    zed = other.zed
    assert do_import(snap).status == 204
    assert_error(zed.get("/me"), 401, "unauthenticated")


def test_export_is_snapshot_unchanged_by_later_writes(world):
    snap = export()
    text = json.dumps(snap, sort_keys=True)
    pay(world.ada, "bob", 10)
    assert json.dumps(snap, sort_keys=True) == text
    assert do_import(snap).status == 204
    assert world.bob.balance() == 2500


def test_export_holds_no_plaintext_password(world):
    raw = call("GET", "/_test/export").text
    assert "correct horse" not in raw


@pytest.mark.parametrize("mut", ["track", "version", "nostate", "state_str", "empty", "array"])
def test_invalid_import_is_422_and_changes_nothing(world, mut):
    snap = export()
    pay(world.ada, "bob", 10)
    bad = dict(snap)
    if mut == "track":
        bad["track"] = "other"
    elif mut == "version":
        bad["format_version"] = 2
    elif mut == "nostate":
        bad.pop("state")
    elif mut == "state_str":
        bad["state"] = "x"
    elif mut == "empty":
        bad = {}
    elif mut == "array":
        bad = {**snap, "state": {"garbage": True}}
    r = do_import(bad)
    assert_error(r, 422, "validation_failed")
    assert world.bob.balance() == 2510


def test_import_unparseable_is_400(world):
    r = call("POST", "/_test/import", raw="{not json")
    assert_error(r, 400, "malformed_request")
    assert world.ada.balance() == 10000


def test_reset_clears_imported_state(world):
    tok = world.ada.token
    snap = export()
    reset(fixture(users=[user("zed", 1)]))
    assert do_import(snap).status == 204
    reset(fixture(users=[user("zed", 1)]))
    assert_error(Client(tok).get("/me"), 401, "unauthenticated")


@pytest.mark.skipif(not BASE_B, reason="POCKETFUL_URL_B not set (second instance)")
def test_cross_instance_import(world):
    p, k_pay, k_fail, rq = _populate(world)
    snap = export()
    bals = world.conserved()
    assert do_import(snap, base=BASE_B).status == 204
    ada_b = Client(world.ada.token, BASE_B)
    assert ada_b.balance() == bals["ada"]
    r = pay(ada_b, "bob", 123, key=k_pay, note="ünï 🎉", visibility="private")
    assert r.status == 200 and r.json() == p.json()
    assert login("bob@example.com", base=BASE_B)
