"""Holdout: stage-3 historical holds, corrections against holds, captures, and upgrades."""
import time

import pytest

from holdout3_client import (BASE_S1, BASE_S2, Client, ask, assert_error, authorize, call,
                             capture, correct, fixture, iso, login, make_world, new_key, pay, q,
                             reset, settle, shift, statement, user, void)


def me_at(c, **kv):
    return c.get("/me?" + "&".join(f"{k}={q(v)}" for k, v in kv.items())).json()


def body(rev=1, amount=0, at=None, reason="fix"):
    return {"expected_revision": rev, "amount": amount, "effective_at": at or iso(-1), "reason": reason}


def test_hold_lifecycle_history_and_closed_at(world):
    a = authorize(world.ada, "bob", 1000).json()
    assert "closed_at" in a and a["closed_at"] is None
    time.sleep(0.05)
    p = capture(world.bob, a["authorization_id"], {"amount": 300, "final": False}).json()
    time.sleep(0.05)
    v = world.ada.post(f"/authorizations/{a['authorization_id']}/void", {}).json()
    assert v["closed_at"] is not None
    before = shift(a["created_at"], -0.01)
    during = shift(p["created_at"], -0.01)
    after_cap = shift(p["created_at"], 0.001)
    after_void = shift(v["closed_at"], 0.001)
    m = me_at(world.ada, as_of=before)
    assert (m["total"], m["held"], m["available"], m["balance"]) == (10000, 0, 10000, 10000)
    m = me_at(world.ada, as_of=during)
    assert (m["total"], m["held"], m["available"]) == (10000, 1000, 9000)
    m = me_at(world.ada, as_of=after_cap)
    assert (m["total"], m["held"], m["available"]) == (9700, 700, 9000)
    m = me_at(world.ada, as_of=after_void)
    assert (m["total"], m["held"], m["available"]) == (9700, 0, 9700)
    # void not yet known: the hold is still held at a later as_of
    m = me_at(world.ada, as_of=after_void, known_at=shift(v["closed_at"], -0.001))
    assert m["held"] == 700 and m["known_at"] == shift(v["closed_at"], -0.001)
    for view in (me_at(world.ada, as_of=x) for x in (before, during, after_cap, after_void)):
        assert view["balance"] == view["total"] and view["available"] == view["total"] - view["held"]
    lst = world.ada.get("/authorizations").json()["authorizations"][0]
    assert lst["closed_at"] == v["closed_at"]


def test_future_as_of_expires_open_hold():
    w = make_world(fixture(ttl=600))
    a = authorize(w.ada, "bob", 1000).json()
    assert me_at(w.ada, as_of=shift(a["expires_at"], -1))["held"] == 1000
    m = me_at(w.ada, as_of=a["expires_at"])
    assert (m["held"], m["available"]) == (0, 10000)


def test_seeded_open_hold_counts_from_reset_or_created_at():
    w = make_world(fixture(authorizations=[
        {"id": "a_1", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 2000,
         "status": "open", "expires_at": iso(7200)},
        {"id": "a_2", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 500,
         "status": "open", "expires_at": iso(7200), "created_at": iso(-3600)}]))
    assert me_at(w.ada, as_of=iso(-1800))["held"] == 500       # a_1 created at reset (now)
    assert me_at(w.ada, as_of=iso(-7200))["held"] == 0
    assert w.ada.me()["held"] == 2500


def test_correction_rejected_when_available_goes_negative_in_the_past(world):
    p1 = pay(world.bob, "cy", 100).json()                      # cy: 500 -> 600
    time.sleep(0.02)
    authorize(world.cy, "ada", 600)                            # cy available 0
    time.sleep(0.02)
    pay(world.ada, "cy", 100)                                  # cy available 100 now
    # reversing p1 (bob->cy 100) debits cy 100 now: affordable now (available 100) ...
    # ... but at the hold boundary cy's available would have been -100.
    assert_error(correct(world.bob, p1["payment_id"], body(amount=0, at=p1["created_at"])),
                 409, "historical_overdraft")
    assert len(world.bob.get(f"/payments/{p1['payment_id']}/revisions").json()["revisions"]) == 1
    world.conserved()


def test_current_unaffordable_takes_precedence(world):
    p1 = pay(world.bob, "cy", 100).json()
    authorize(world.cy, "ada", 600)                            # cy available 0
    assert_error(correct(world.bob, p1["payment_id"], body(amount=0, at=p1["created_at"])),
                 409, "insufficient_funds")


def test_statement_money_only_and_capture_once(world):
    a = authorize(world.ada, "bob", 1000).json()
    p = capture(world.bob, a["authorization_id"], {"amount": 400}).json()
    authorize(world.ada, "bob", 50)
    s = statement(world.ada).json()
    assert [(e["payment"]["payment_id"], e["payment"]["authorization_id"], e["delta"]) for e in s["entries"]] == \
        [(p["payment_id"], a["authorization_id"], -400)]
    assert_error(correct(world.ada, p["payment_id"], body(amount=1)), 422, "linked_payment_immutable")


def test_snapshot_unchanged_after_lifecycle(world):
    pay(world.ada, "bob", 10)
    s1 = statement(world.ada).json()
    a = authorize(world.ada, "bob", 100).json()
    capture(world.bob, a["authorization_id"], {"amount": 60})
    pay(world.ada, "bob", 1)
    again = world.ada.get(f"/statement?snapshot={q(s1['snapshot'])}").json()
    assert again["entries"] == s1["entries"] and again["closing_balance"] == s1["closing_balance"]


def test_stage3_export_roundtrip(world):
    p = pay(world.ada, "bob", 100).json()
    k = new_key()
    b = body(amount=60)
    c = correct(world.ada, p["payment_id"], b, key=k).json()
    s = statement(world.ada).json()
    snap = call("GET", "/_test/export").json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    assert world.ada.get(f"/statement?snapshot={q(s['snapshot'])}").json()["entries"] == s["entries"]
    r = correct(world.ada, p["payment_id"], b, key=k)
    assert r.status == 200 and r.json() == c
    revs = world.ada.get(f"/payments/{p['payment_id']}/revisions").json()["revisions"]
    assert [x["revision"] for x in revs] == [1, 2] and revs[1] == c
    world.conserved()


@pytest.fixture
def stage1():
    assert BASE_S1, "set POCKETFUL_STAGE1_URL to a running stage-1 service of this team"
    return BASE_S1


@pytest.fixture
def stage2():
    assert BASE_S2, "set POCKETFUL_STAGE2_URL to a running stage-2 service of this team"
    return BASE_S2


def test_stage1_export_upgrades(stage1):
    fx = fixture(operators=["u_ada"])
    reset(fx, base=stage1)
    ada1 = Client(login("ada@example.com", base=stage1), stage1)
    k = new_key()
    p = pay(ada1, "bob", 123, key=k).json()
    s = settle(ada1, [{"from_handle": "bob", "to_handle": "cy", "amount": 5}]).json()
    snap = call("GET", "/_test/export", base=stage1).json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    ada, bob = Client(ada1.token), Client(login("bob@example.com"))
    r = pay(ada, "bob", 123, key=k)
    assert r.status == 200 and r.json() == p
    revs = ada.get(f"/payments/{p['payment_id']}/revisions").json()["revisions"]
    assert revs[0]["effective_at"] == revs[0]["recorded_at"] == p["created_at"]
    mid = s["payments"][0]["payment_id"]
    assert_error(correct(bob, mid, body(amount=1)), 422, "linked_payment_immutable")
    st = statement(ada).json()
    assert st["opening_balance"] == 10000 and st["closing_balance"] == 9877
    assert correct(ada, p["payment_id"], body(amount=100)).status == 201
    assert ada.me()["balance"] == 9900


def test_stage2_export_upgrades(stage2):
    reset(fixture(), base=stage2)
    ada2 = Client(login("ada@example.com", base=stage2), stage2)
    bob2 = Client(login("bob@example.com", base=stage2), stage2)
    a = authorize(ada2, "bob", 1000).json()
    k = new_key()
    cap = capture(bob2, a["authorization_id"], {"amount": 250, "final": False}, key=k).json()
    b = authorize(ada2, "cy", 300).json()
    snap = call("GET", "/_test/export", base=stage2).json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    ada, bob = Client(ada2.token), Client(bob2.token)
    m = ada.me()
    assert (m["total"], m["held"], m["available"]) == (9750, 1050, 8700)
    r = capture(bob, a["authorization_id"], {"amount": 250, "final": False}, key=k)
    assert r.status == 200 and r.json() == cap
    assert_error(correct(ada, cap["payment_id"], body(amount=1)), 422, "linked_payment_immutable")
    lst = {x["authorization_id"]: x for x in ada.get("/authorizations").json()["authorizations"]}
    assert lst[a["authorization_id"]]["closed_at"] is None and lst[b["authorization_id"]]["status"] == "open"
    st = statement(ada).json()
    assert [e["payment"]["payment_id"] for e in st["entries"]] == [cap["payment_id"]]
    assert capture(bob, a["authorization_id"]).json()["amount"] == 750


def test_seeded_closed_authorizations_closed_at_s3d8():
    w = make_world(fixture(authorizations=[
        {"id": "a_exp", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 300,
         "status": "expired", "expires_at": iso(-7200)},
        {"id": "a_void", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 200,
         "status": "voided", "expires_at": iso(7200)},
        {"id": "a_open_past", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 100,
         "status": "open", "expires_at": iso(-3600)}]))
    lst = {x["authorization_id"]: x for x in w.ada.get("/authorizations").json()["authorizations"]}
    assert lst["a_exp"]["closed_at"] is not None
    from datetime import datetime
    same = lambda a, b: datetime.fromisoformat(a) == datetime.fromisoformat(b)
    assert same(lst["a_exp"]["closed_at"], lst["a_exp"]["expires_at"])
    assert lst["a_void"]["closed_at"] is not None
    assert lst["a_open_past"]["status"] == "expired" and lst["a_open_past"]["closed_at"] is not None
    for at in (iso(-5000), iso(-10)):
        assert me_at(w.ada, as_of=at)["held"] == 0     # seeded closed holds hold nothing
