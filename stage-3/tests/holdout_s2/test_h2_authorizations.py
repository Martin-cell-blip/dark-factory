"""Holdout: stage-2 holds, authorizations, captures, void, expiry, listing."""
import time

import pytest

from holdout2_client import (assert_error, authorize, call, capture, fixture, iso,
                            make_world, new_key, pay, reset, settle, user, void, ask,
                            burst, no_5xx)

AUTH_FIELDS = {"authorization_id", "from_user_id", "from_handle", "to_user_id", "to_handle",
               "amount", "captured_amount", "remaining_amount", "currency", "note",
               "visibility", "status", "expires_at", "payment_id", "payment_ids", "created_at"}
PAY_FIELDS = {"payment_id", "from_user_id", "from_handle", "to_user_id", "to_handle", "amount",
              "currency", "note", "visibility", "request_id", "settlement_id",
              "authorization_id", "created_at"}


def _dt(s):
    from datetime import datetime
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_me_fields_and_no_hold_agreement(world):
    me = world.ada.me()
    assert {"user_id", "display_name", "handle", "balance", "total", "available", "held",
            "currency", "minor_units"} <= set(me)
    assert me["balance"] == me["total"] == me["available"] == 10000 and me["held"] == 0


def test_authorization_shape_and_hold(world):
    r = authorize(world.ada, "bob", 2000, note="deposit", visibility="private")
    assert r.status == 201, r
    a = r.json()
    assert AUTH_FIELDS <= set(a), AUTH_FIELDS - set(a)
    assert (a["from_handle"], a["to_handle"], a["amount"], a["captured_amount"],
            a["remaining_amount"], a["status"], a["payment_id"], a["payment_ids"],
            a["currency"], a["note"], a["visibility"]) == \
        ("ada", "bob", 2000, 0, 2000, "open", None, [], "EUR", "deposit", "private")
    assert (_dt(a["expires_at"]) - _dt(a["created_at"])).total_seconds() == pytest.approx(600, abs=1)
    me = world.ada.me()
    assert (me["total"], me["available"], me["held"], me["balance"]) == (10000, 8000, 2000, 10000)
    assert world.bob.me()["available"] == 2500
    assert world.ada.get("/activity").json()["payments"] == []
    assert world.bob.get("/activity").json()["payments"] == []
    world.conserved()


def test_authorization_defaults(world):
    a = authorize(world.ada, "bob", 1).json()
    assert a["note"] == "" and a["visibility"] == "public"


@pytest.mark.parametrize("body,status,code", [
    ({"to_handle": "bob", "amount": 0}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": 1000000001}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": 1.5}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": "5"}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": True}, 422, "validation_failed"),
    ({"to_handle": "bob"}, 422, "validation_failed"),
    ({"to_handle": "ada", "amount": 1}, 422, "self_payment"),
    ({"to_handle": "bob", "amount": 1, "note": "x" * 201}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": 1, "note": None}, 422, "validation_failed"),
    ({"to_handle": "bob", "amount": 1, "visibility": "friends"}, 422, "validation_failed"),
    ({"to_handle": "nobody", "amount": 1}, 404, "not_found"),
    ({"to_handle": "bob", "amount": 10001}, 409, "insufficient_funds"),
])
def test_authorization_errors(world, body, status, code):
    assert_error(world.ada.post("/authorizations", body, key=new_key()), status, code)
    assert world.ada.me()["held"] == 0


def test_held_funds_cannot_fund_anything(opworld):
    w = opworld
    assert authorize(w.cy, "ada", 400).status == 201  # cy: total 500, available 100
    assert_error(pay(w.cy, "bob", 101), 409, "insufficient_funds")
    assert pay(w.cy, "bob", 100).status == 201
    rq = ask(w.bob, "cy", 1).json()
    assert_error(w.cy.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key()),
                 409, "insufficient_funds")
    assert_error(authorize(w.cy, "bob", 1), 409, "insufficient_funds")
    assert_error(settle(w.op, [{"from_handle": "cy", "to_handle": "bob", "amount": 1}]),
                 409, "insufficient_funds")
    # netting: an incoming transfer in the same batch can fund it
    assert settle(w.op, [{"from_handle": "cy", "to_handle": "bob", "amount": 5},
                         {"from_handle": "ada", "to_handle": "cy", "amount": 5}]).status == 201
    assert w.cy.me()["available"] == 0 and w.cy.me()["held"] == 400
    w.conserved()


def test_capture_spends_reserved_funds_even_at_zero_available(world):
    a = authorize(world.cy, "bob", 500).json()
    assert world.cy.me()["available"] == 0
    r = capture(world.bob, a["authorization_id"])
    assert r.status == 201, r
    p = r.json()
    assert PAY_FIELDS <= set(p), PAY_FIELDS - set(p)
    assert (p["amount"], p["authorization_id"], p["request_id"], p["settlement_id"],
            p["from_handle"], p["to_handle"]) == (500, a["authorization_id"], None, None, "cy", "bob")
    assert world.cy.me()["total"] == 0 and world.bob.me()["total"] == 3000
    world.conserved()


def test_partial_final_capture_releases_remainder(world):
    a = authorize(world.ada, "bob", 2000, note="dep", visibility="private").json()
    r = capture(world.bob, a["authorization_id"], {"amount": 1500})
    assert r.status == 201, r
    p = r.json()
    assert p["note"] == "dep" and p["visibility"] == "private" and p["amount"] == 1500
    me = world.ada.me()
    assert (me["total"], me["held"], me["available"]) == (8500, 0, 8500)
    lst = world.ada.get("/authorizations").json()["authorizations"]
    got = [x for x in lst if x["authorization_id"] == a["authorization_id"]][0]
    assert (got["status"], got["captured_amount"], got["remaining_amount"], got["payment_id"],
            got["payment_ids"]) == ("captured", 1500, 0, p["payment_id"], [p["payment_id"]])
    # private capture: visible to both parties, hidden from cy
    assert [x["payment_id"] for x in world.bob.get("/activity").json()["payments"]] == [p["payment_id"]]
    assert world.cy.get("/activity").json()["payments"] == []
    assert_error(capture(world.bob, a["authorization_id"], {"amount": 1}), 409, "authorization_not_open")
    world.conserved()


def test_extended_capture_mode(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    p1 = capture(world.bob, aid, {"amount": 300, "final": False}).json()
    a = [x for x in world.bob.get("/authorizations").json()["authorizations"]][0]
    assert (a["status"], a["captured_amount"], a["remaining_amount"]) == ("open", 300, 700)
    assert world.ada.me()["held"] == 700
    assert_error(capture(world.bob, aid, {"amount": 701, "final": False}), 422,
                 "capture_exceeds_authorization")
    p2 = capture(world.bob, aid, {"amount": 200, "final": False}).json()
    p3 = capture(world.bob, aid, {"final": False})  # defaults to remainder -> closes
    assert p3.status == 201 and p3.json()["amount"] == 500
    a = world.bob.get("/authorizations").json()["authorizations"][0]
    assert (a["status"], a["captured_amount"], a["remaining_amount"], a["payment_id"],
            a["payment_ids"]) == ("captured", 1000, 0, p3.json()["payment_id"],
                                  [p1["payment_id"], p2["payment_id"], p3.json()["payment_id"]])
    assert world.ada.me()["held"] == 0 and world.ada.me()["total"] == 9000
    world.conserved()


def test_final_true_closes_and_releases(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    capture(world.bob, aid, {"amount": 100, "final": False})
    r = capture(world.bob, aid, {"amount": 100, "final": True})
    assert r.status == 201
    me = world.ada.me()
    assert (me["held"], me["total"]) == (0, 9800)


@pytest.mark.parametrize("final", ["false", 0, None, "yes"])
def test_final_wrong_type_is_400(world, final):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    assert_error(capture(world.bob, aid, {"amount": 1, "final": final}), 400, "malformed_request")
    assert world.ada.me()["held"] == 1000


@pytest.mark.parametrize("body", [{"amount": 0}, {"amount": -1}, {"amount": 1.5}, {"amount": "1"}])
def test_capture_amount_validation(world, body):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    assert_error(capture(world.bob, aid, body), 422, "validation_failed")


def test_capture_exceeds(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    assert_error(capture(world.bob, aid, {"amount": 1001}), 422, "capture_exceeds_authorization")


def test_capture_and_void_permissions(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    assert_error(capture(world.ada, aid), 403, "forbidden")
    assert_error(capture(world.cy, aid), 403, "forbidden")
    assert_error(void(world.bob, aid), 403, "forbidden")
    assert_error(void(world.cy, aid), 403, "forbidden")
    assert_error(capture(world.bob, "a_nope"), 404, "not_found")
    assert_error(void(world.ada, "a_nope"), 404, "not_found")
    assert world.cy.get("/authorizations").json()["authorizations"] == []


def test_void(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    r1 = void(world.ada, aid)
    assert r1.status == 200 and r1.json()["status"] == "voided" and r1.json()["remaining_amount"] == 0
    assert world.ada.me()["held"] == 0
    r2 = void(world.ada, aid)
    assert r2.status == 200 and r2.json()["status"] == "voided"
    assert_error(capture(world.bob, aid), 409, "authorization_not_open")
    aid2 = authorize(world.ada, "bob", 10).json()["authorization_id"]
    capture(world.bob, aid2)
    assert_error(void(world.ada, aid2), 409, "authorization_not_open")


def test_void_partial_keeps_capture_records(world):
    aid = authorize(world.ada, "bob", 1000).json()["authorization_id"]
    p = capture(world.bob, aid, {"amount": 400, "final": False}).json()
    v = void(world.ada, aid).json()
    assert (v["status"], v["captured_amount"], v["remaining_amount"], v["payment_ids"]) == \
        ("voided", 400, 0, [p["payment_id"]])
    me = world.ada.me()
    assert (me["total"], me["held"], me["available"]) == (9600, 0, 9600)
    world.conserved()


def test_expiry_by_clock():
    w = make_world(fixture(ttl=2))
    a = authorize(w.ada, "bob", 3000).json()
    b = authorize(w.ada, "bob", 1000).json()
    capture(w.bob, b["authorization_id"], {"amount": 100, "final": False})
    assert w.ada.me()["held"] == 3900
    time.sleep(2.6)
    me = w.ada.me()
    assert (me["held"], me["available"], me["total"]) == (0, 9900, 9900)
    lst = {x["authorization_id"]: x for x in w.ada.get("/authorizations").json()["authorizations"]}
    assert lst[a["authorization_id"]]["status"] == "expired"
    assert lst[b["authorization_id"]]["status"] == "expired"
    assert lst[b["authorization_id"]]["captured_amount"] == 100
    assert lst[b["authorization_id"]]["remaining_amount"] == 0
    assert w.ada.get("/authorizations?status=open").json()["authorizations"] == []
    assert len(w.ada.get("/authorizations?status=expired").json()["authorizations"]) == 2
    assert_error(capture(w.bob, a["authorization_id"]), 409, "authorization_expired")
    assert_error(void(w.ada, a["authorization_id"]), 409, "authorization_not_open")
    w.conserved()


def test_expiry_releases_funds_for_writes_without_a_read():
    w = make_world(fixture(users=[user("ada", 1000), user("bob", 0)], ttl=1))
    assert authorize(w.ada, "bob", 1000).status == 201
    time.sleep(1.5)
    assert pay(w.ada, "bob", 1000).status == 201  # first request after the deadline is a write
    w.conserved()


def test_invalid_ttl_is_422():
    for ttl in (0, -5, 1.5, "600", True):
        r = call("POST", "/_test/reset", fixture(ttl=ttl))
        assert_error(r, 422, "validation_failed")


def test_seeded_authorizations():
    fx = fixture(users=[user("ada", 10000), user("bob", 2500), user("cy", 500)], authorizations=[
        {"id": "a_1", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 2000,
         "note": "deposit", "visibility": "public", "status": "open", "expires_at": iso(7200)},
        {"id": "a_2", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 9000,
         "note": "", "visibility": "public", "status": "open", "expires_at": iso(-7200)},
        {"id": "a_3", "from_user_id": "u_cy", "to_user_id": "u_bob", "amount": 500,
         "note": "", "visibility": "public", "status": "voided", "expires_at": iso(7200)},
    ])
    w = make_world(fx)
    me = w.ada.me()
    assert (me["balance"], me["total"], me["held"], me["available"]) == (10000, 10000, 2000, 8000)
    lst = {x["authorization_id"]: x for x in w.bob.get("/authorizations").json()["authorizations"]}
    assert set(lst) == {"a_1", "a_2", "a_3"}
    assert lst["a_1"]["status"] == "open" and lst["a_2"]["status"] == "expired"
    assert lst["a_3"]["status"] == "voided"
    assert w.cy.me()["available"] == 500
    r = capture(w.bob, "a_1", {"amount": 500})
    assert r.status == 201 and r.json()["authorization_id"] == "a_1"
    w.conserved()


def test_seeded_holds_above_balance_is_reset_error(world):
    pay(world.ada, "bob", 1)
    bad = fixture(users=[user("ada", 100), user("bob", 0)], authorizations=[
        {"id": "a_1", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 60,
         "status": "open", "expires_at": iso(7200)},
        {"id": "a_2", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 41,
         "status": "open", "expires_at": iso(7200)}])
    assert_error(call("POST", "/_test/reset", bad), 422, "validation_failed")
    assert world.bob.me()["total"] == 2501
    ok = dict(bad)
    ok["authorizations"] = [dict(bad["authorizations"][0]), dict(bad["authorizations"][1],
                                                               expires_at=iso(-7200))]
    assert call("POST", "/_test/reset", ok).status == 204


def test_list_filters_and_paging(world):
    ids = [authorize(world.ada, "bob", 10).json()["authorization_id"] for _ in range(3)]
    inc = authorize(world.bob, "ada", 10).json()["authorization_id"]
    void(world.ada, ids[0])
    body = world.ada.get("/authorizations").json()
    assert set(body) >= {"authorizations", "has_more"}
    assert [x["authorization_id"] for x in body["authorizations"]] == [inc, ids[2], ids[1], ids[0]]
    assert [x["authorization_id"] for x in world.ada.get("/authorizations?direction=outgoing").json()["authorizations"]] == ids[::-1]
    assert [x["authorization_id"] for x in world.ada.get("/authorizations?direction=incoming").json()["authorizations"]] == [inc]
    assert [x["authorization_id"] for x in world.ada.get("/authorizations?status=voided").json()["authorizations"]] == [ids[0]]
    p = world.ada.get("/authorizations?limit=2&offset=1").json()
    assert [x["authorization_id"] for x in p["authorizations"]] == [ids[2], ids[1]] and p["has_more"] is True
    for q in ["direction=sideways", "status=pending", "status=OPEN", "limit=0", "limit=201",
              "offset=-1", "limit=1e1", "limit=+4", "limit=4.0"]:
        assert_error(world.ada.get(f"/authorizations?{q}"), 422, "validation_failed")


def test_payments_carry_authorization_id_null(world):
    p = pay(world.ada, "bob", 1).json()
    assert "authorization_id" in p and p["authorization_id"] is None
    rq = ask(world.bob, "ada", 1).json()
    pp = world.ada.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key()).json()
    assert pp["authorization_id"] is None
    for x in world.ada.get("/activity").json()["payments"]:
        assert x["authorization_id"] is None


def test_concurrent_authorizations_and_payments_never_overdraw():
    for _ in range(10):
        w = make_world(fixture(users=[user("ada", 1000), user("bob", 0)]))

        def act(i):
            return authorize(w.ada, "bob", 100) if i % 2 else pay(w.ada, "bob", 100)
        rs = burst(act, 30)
        no_5xx(rs)
        assert sum(r.status == 201 for r in rs) == 10, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert_error(r, 409, "insufficient_funds")
        me = w.ada.me()
        assert me["available"] == 0
        w.conserved()


def test_concurrent_captures_never_exceed():
    for _ in range(10):
        w = make_world()
        aid = authorize(w.ada, "bob", 1000).json()["authorization_id"]
        rs = burst(lambda i: capture(w.bob, aid, {"amount": 100, "final": False}), 30)
        no_5xx(rs)
        ok = sum(r.status == 201 for r in rs)
        assert ok == 10, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert r.status in (409, 422), r
        assert w.bob.me()["total"] == 3500 and w.ada.me()["held"] == 0
        w.conserved()


def test_concurrent_final_captures_one_wins():
    for _ in range(10):
        w = make_world()
        aid = authorize(w.ada, "bob", 1000).json()["authorization_id"]
        rs = burst(lambda i: capture(w.bob, aid, {"amount": 10}), 20)
        no_5xx(rs)
        assert sum(r.status == 201 for r in rs) == 1
        for r in rs:
            if r.status != 201:
                assert_error(r, 409, "authorization_not_open")
        assert w.bob.me()["total"] == 2510
        w.conserved()


def test_capture_versus_void_race():
    for _ in range(10):
        w = make_world()
        aid = authorize(w.ada, "bob", 1000).json()["authorization_id"]

        def act(i):
            return capture(w.bob, aid) if i % 2 else void(w.ada, aid)
        rs = burst(act, 20)
        no_5xx(rs)
        caps = sum(r.status == 201 for r in rs)
        st = w.ada.get("/authorizations").json()["authorizations"][0]["status"]
        bals = w.conserved()
        if st == "captured":
            assert caps == 1 and bals["bob"] == 3500
        else:
            assert st == "voided" and caps == 0 and bals["bob"] == 2500
        assert w.ada.me()["held"] == 0
