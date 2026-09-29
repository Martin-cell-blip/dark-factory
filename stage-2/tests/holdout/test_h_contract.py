"""Holdout: conventions, errors, auth, model edges, splits, feed, boundary."""
import re

import pytest

from holdout_client import (Client, assert_error, ask, call, fixture, make_world,
                            new_key, pay, reset, user)

RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def test_health_and_content_type():
    r = call("GET", "/health")
    assert r.status == 200 and r.json() == {"status": "ok"}
    ct = r.headers.get("content-type", "").lower().replace(" ", "")
    assert ct.startswith("application/json") and "charset=utf-8" in ct


def test_error_responses_are_json_utf8(world):
    r = call("GET", "/me")
    assert_error(r, 401, "unauthenticated")
    assert "charset=utf-8" in r.headers.get("content-type", "").lower().replace(" ", "")


def test_seeded_ids_and_records_verbatim():
    fx = fixture(users=[user("ada", 10000, "u_ada"), user("bob", 2500, "u_bob"), user("cy", 0, "cy-77")],
                 payments=[{"id": "p_1", "from_user_id": "u_ada", "to_user_id": "u_bob",
                            "amount": 500, "note": "coffee", "visibility": "private"}],
                 requests=[{"id": "rq_1", "requester_id": "u_bob", "payer_id": "u_ada",
                            "amount": 1200, "note": "taxi", "status": "pending"},
                           {"id": "rq_2", "requester_id": "u_bob", "payer_id": "u_ada",
                            "amount": 5, "note": "", "status": "declined"}])
    w = make_world(fx)
    assert w.cy.me()["user_id"] == "cy-77"
    feed = w.bob.get("/activity").json()["payments"]
    assert [(p["payment_id"], p["from_handle"], p["to_handle"], p["amount"], p["visibility"],
             p["request_id"], p["settlement_id"]) for p in feed] == \
        [("p_1", "ada", "bob", 500, "private", None, None)]
    assert RFC3339.match(feed[0]["created_at"])
    assert w.cy.get("/activity").json()["payments"] == []
    reqs = {q["request_id"]: q for q in w.ada.get("/requests").json()["requests"]}
    assert reqs["rq_1"]["status"] == "pending" and reqs["rq_2"]["status"] == "declined"
    assert reqs["rq_1"]["requester_handle"] == "bob" and reqs["rq_1"]["payer_handle"] == "ada"
    assert w.ada.balance() == 10000 and w.bob.balance() == 2500
    assert_error(w.ada.post("/requests/rq_2/pay", {}, key=new_key()), 409, "request_not_pending")


def test_largest_balances_are_exact():
    big = 2 ** 53 - 1 - 1000000000
    w = make_world(fixture(users=[user("ada", big), user("bob", 1000000000)]))
    assert w.ada.balance() == big
    assert pay(w.bob, "ada", 1000000000).status == 201
    assert w.ada.balance() == 2 ** 53 - 1
    assert w.bob.balance() == 0
    r = call("GET", "/me", token=w.ada.token)
    assert b"9007199254740991" in r.raw
    snap = call("GET", "/_test/export").json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=15).status == 204
    assert w.ada.balance() == 2 ** 53 - 1 and w.bob.balance() == 0


@pytest.mark.parametrize("raw", ["[]", "\"x\"", "42", "null", "{", ""])
def test_non_object_or_unparseable_body_is_400(world, raw):
    assert_error(world.ada.post("/payments", raw=raw, key=new_key()), 400, "malformed_request")


@pytest.mark.parametrize("body", [{"to_handle": 5, "amount": 1}, {"to_handle": ["bob"], "amount": 1},
                                  {"to_handle": None, "amount": 1}])
def test_wrong_typed_handle_is_400(world, body):
    assert_error(world.ada.post("/payments", body, key=new_key()), 400, "malformed_request")


@pytest.mark.parametrize("body", [{"amount": 1}, {"to_handle": "bob"}])
def test_missing_required_field_is_422(world, body):
    assert_error(world.ada.post("/payments", body, key=new_key()), 422, "validation_failed")


@pytest.mark.parametrize("amount", [1000.0, 1e3])
def test_integral_float_amounts_are_valid(world, amount):
    r = world.ada.post("/payments", raw='{"to_handle":"bob","amount":%s}' % ("1000.0" if amount == 1000.0 else "1e3"),
                       key=new_key())
    assert r.status == 201, r
    assert r.json()["amount"] == 1000 and isinstance(r.json()["amount"], int)


@pytest.mark.parametrize("header", ["Bearer", "Bearer ", "Basic abc", "bearer-nope", "Bearer nope"])
def test_bad_auth_is_401(world, header):
    assert_error(call("GET", "/me", headers={"Authorization": header}), 401, "unauthenticated")
    assert_error(call("GET", "/activity", headers={"Authorization": header}), 401, "unauthenticated")


def test_every_protected_route_needs_a_token(world):
    for m, p in [("GET", "/me"), ("GET", "/requests"), ("GET", "/activity"),
                 ("POST", "/payments"), ("POST", "/requests"), ("POST", "/splits"),
                 ("POST", "/requests/x/pay"), ("POST", "/requests/x/decline"),
                 ("POST", "/requests/x/cancel"), ("POST", "/settlements")]:
        assert_error(call(m, p, {} if m == "POST" else None, key=new_key()) if m == "POST"
                     else call(m, p), 401, "unauthenticated")


@pytest.mark.parametrize("email,handle", [("Jane.Doe+x@example.com", "jane_doe_x"),
                                          ("ABCDEFGHIJKLMNOPQRSTUVWXYZ@x.io", "abcdefghijklmnopqrst"),
                                          ("é_1@x.io", "__1")])
def test_signup_derives_handle(world, email, handle):
    r = call("POST", "/auth/signup", {"email": email, "password": "longenough", "display_name": "N"})
    assert r.status == 201, r
    body = r.json()
    assert set(body) >= {"user_id", "display_name", "token"} and body["display_name"] == "N"
    me = Client(body["token"]).me()
    assert me["handle"] == handle and me["balance"] == 0 and me["user_id"] == body["user_id"]
    assert pay(world.ada, handle, 5).status == 201
    assert ask(world.ada, handle, 99999).status == 201
    assert Client(body["token"]).balance() == 5


def test_signup_errors(world):
    def su(email, pw="longenough"):
        return call("POST", "/auth/signup", {"email": email, "password": pw, "display_name": "X"})
    assert_error(su("ada@example.com"), 409, "email_taken")
    assert_error(su("ADA@other.org"), 409, "handle_taken")
    assert_error(call("POST", "/auth/login", {"email": "ADA@other.org", "password": "longenough"}),
                 401, "unauthenticated")
    assert_error(su("new@example.com", "short77"), 422, "validation_failed")
    for bad in ["noatsign", "@example.com", "local@", ""]:
        assert_error(su(bad), 422, "validation_failed")
    assert su("new@example.com", "12345678").status == 201


def test_login_errors_and_multiple_tokens(world):
    assert_error(call("POST", "/auth/login", {"email": "ada@example.com", "password": "wrong pass"}),
                 401, "unauthenticated")
    assert_error(call("POST", "/auth/login", {"email": "nobody@example.com", "password": "correct horse"}),
                 401, "unauthenticated")
    t2 = call("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"}).json()["token"]
    assert t2 != world.ada.token
    assert Client(t2).me()["handle"] == "ada" and world.ada.me()["handle"] == "ada"


def test_note_length_counts_code_points(world):
    assert pay(world.ada, "bob", 1, note="🎉" * 200).status == 201
    assert_error(pay(world.ada, "bob", 1, note="🎉" * 201), 422, "validation_failed")
    raw = "á \t line\r\n <b>&amp;</b> \\ \"q\" \u0000end "
    r = pay(world.ada, "bob", 1, note=raw)
    assert r.status == 201 and r.json()["note"] == raw
    assert world.bob.get("/activity?limit=1").json()["payments"][0]["note"] == raw


def test_split_requests_visible_and_payable(world):
    r = world.ada.post("/splits", {"amount": 1000, "participant_handles": ["cy", "bob"], "note": "pz"},
                       key=new_key())
    assert r.status == 201, r
    s = r.json()
    assert s["shares"] == [{"handle": "cy", "amount": 500}, {"handle": "bob", "amount": 500}]
    assert [q["payer_handle"] for q in s["requests"]] == ["cy", "bob"]
    assert RFC3339.match(s["created_at"]) and s["currency"] == "EUR"
    bob_req = world.bob.get("/requests?direction=incoming").json()["requests"]
    assert [q["request_id"] for q in bob_req] == [s["requests"][1]["request_id"]]
    assert len(world.ada.get("/requests?direction=outgoing").json()["requests"]) == 2
    assert world.cy.get("/requests").json()["requests"][0]["request_id"] == s["requests"][0]["request_id"]
    assert world.ada.get("/activity").json()["payments"] == []
    p = world.bob.post(f"/requests/{s['requests'][1]['request_id']}/pay", {}, key=new_key())
    assert p.status == 201 and p.json()["amount"] == 500
    assert_error(world.cy.post(f"/requests/{s['requests'][1]['request_id']}/pay", {}, key=new_key()),
                 403, "forbidden")
    world.conserved()


def test_split_wrong_types(world):
    assert_error(world.ada.post("/splits", {"amount": 10, "participant_handles": "bob"}, key=new_key()),
                 400, "malformed_request")
    assert_error(world.ada.post("/splits", {"amount": 10, "participant_handles": ["bob", "BOB"]},
                                key=new_key()), 404, "not_found")
    assert_error(world.ada.post("/splits", {"amount": 10, "participant_handles": ["bob", "bob"]},
                                key=new_key()), 422, "validation_failed")


def test_decline_idempotent_and_state_machine(world):
    rid = ask(world.bob, "ada", 10).json()["request_id"]
    assert_error(world.bob.post(f"/requests/{rid}/decline", {}), 403, "forbidden")
    assert_error(world.ada.post(f"/requests/{rid}/cancel", {}), 403, "forbidden")
    d1 = world.ada.post(f"/requests/{rid}/decline", {})
    assert d1.status == 200 and d1.json()["status"] == "declined"
    d2 = world.ada.post(f"/requests/{rid}/decline", {})
    assert d2.status == 200 and d2.json() == d1.json()
    assert_error(world.bob.post(f"/requests/{rid}/cancel", {}), 409, "request_not_pending")
    assert_error(world.ada.post("/requests/nope/decline", {}), 404, "not_found")
    assert_error(world.bob.post("/requests/nope/cancel", {}), 404, "not_found")


def test_paging_limits_and_unknown_params(world):
    for i in range(5):
        pay(world.ada, "bob", i + 1)
    r = world.cy.get("/activity?limit=2&offset=4&foo=bar").json()
    assert len(r["payments"]) == 1 and r["has_more"] is False
    r = world.cy.get("/activity?limit=2&offset=2").json()
    assert len(r["payments"]) == 2 and r["has_more"] is True
    assert world.cy.get("/activity?limit=200").status == 200
    assert world.cy.get("/activity?offset=99").json() == {"payments": [], "has_more": False}
    for q in ["limit=0", "limit=201", "offset=-1", "limit=1.0", "limit=%2B4", "limit=", "offset=abc"]:
        assert_error(world.cy.get(f"/activity?{q}"), 422, "validation_failed")


def test_ids_are_short_strings(world):
    p = pay(world.ada, "bob", 1).json()
    q = ask(world.ada, "bob", 1).json()
    for v in [p["payment_id"], p["from_user_id"], q["request_id"], q["payer_id"]]:
        assert isinstance(v, str) and 0 < len(v) <= 64
    assert RFC3339.match(p["created_at"]) and RFC3339.match(q["created_at"])


def test_reset_rejects_negative_balance_and_keeps_state(world):
    pay(world.ada, "bob", 10)
    r = call("POST", "/_test/reset", fixture(users=[user("ada", 5), user("zz", -1)]))
    assert_error(r, 422, "validation_failed")
    assert world.bob.balance() == 2510


@pytest.mark.parametrize("cur,mu", [("JPY", 0), ("BHD", 3)])
def test_currency_reported(cur, mu):
    w = make_world(fixture(currency=cur, minor_units=mu))
    me = w.ada.me()
    assert me["currency"] == cur and me["minor_units"] == mu
    assert pay(w.ada, "bob", 7).json()["currency"] == cur


def test_boundary_authorizations_present_in_stage_2(world):
    """Stage 1's boundary is reversed in stage 2: authorizations exist."""
    r = world.ada.post("/authorizations", {"to_handle": "bob", "amount": 10}, key=new_key())
    assert r.status == 201, r


def test_huge_integer_amount_is_422_not_400(world):
    r = world.ada.post("/payments", raw='{"to_handle":"bob","amount":1' + "0" * 5000 + "}", key=new_key())
    assert_error(r, 422, "validation_failed")
    r = world.bob.post("/requests", raw='{"payer_handle":"ada","amount":-1' + "0" * 5000 + "}", key=new_key())
    assert_error(r, 422, "validation_failed")


def test_reset_of_1000_users_within_5s():
    import time
    fx = fixture(users=[user(f"u{i}", 100) for i in range(1000)])
    start = time.monotonic()
    r = call("POST", "/_test/reset", fx, timeout=15)
    elapsed = time.monotonic() - start
    assert r.status == 204, r
    assert elapsed < 5, f"reset of 1000 users took {elapsed:.2f}s (D7: < 5 s)"
    tok = call("POST", "/auth/login", {"email": "u999@example.com", "password": "correct horse"})
    assert tok.status == 200, tok
    assert "correct horse" not in call("GET", "/_test/export").text


def test_body_above_8_mib_is_refused_with_envelope(world):
    raw = '{"to_handle":"bob","amount":1,"pad":"' + "x" * (9 * 1024 * 1024) + '"}'
    r = world.ada.post("/payments", raw=raw, key=new_key(), timeout=30)
    assert r.status == 413, r
    body = r.json()
    assert isinstance(body["error"]["code"], str) and isinstance(body["error"]["message"], str)
    assert world.ada.balance() == 10000


def test_body_just_under_1_mib_with_unknown_field_is_accepted(world):
    head, tail = '{"to_handle":"bob","amount":1,"pad":"', '"}'
    raw = head + "x" * (1024 * 1024 - len(head) - len(tail) - 16) + tail
    r = world.ada.post("/payments", raw=raw, key=new_key(), timeout=30)
    assert r.status == 201, r


def test_fifty_concurrent_maximal_array_bodies_within_5s(world):
    import time
    from holdout_client import burst, no_5xx
    cap = 1024 * 1024
    head, tail = '{"to_handle":"bob","amount":1,"pad":[', ']}'
    k = (cap - len(head) - len(tail) + 1) // 2
    raw = (head + ",".join(["0"] * k) + tail).encode()
    while len(raw) > cap:
        k -= 1
        raw = (head + ",".join(["0"] * k) + tail).encode()
    lat = []

    def one(i):
        s = time.monotonic()
        r = world.ada.post("/payments", raw=raw, key=new_key(), timeout=30)
        lat.append(time.monotonic() - s)
        return r
    rs = burst(one, 50)
    no_5xx(rs)
    assert all(r.status == 201 for r in rs), sorted({r.status for r in rs})
    assert max(lat) < 5, f"slowest {max(lat):.2f}s"
    world.conserved()


def test_large_export_imports_without_413():
    users = [user("ada", 10 ** 9), user("bob", 0)]
    pays = [{"id": f"p_{i}", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 1,
             "note": "n" * 200, "visibility": "public"} for i in range(40000)]
    reset(fixture(users=users, payments=pays))
    r = call("GET", "/_test/export", timeout=30)
    assert r.status == 200, r
    assert len(r.raw) > 8 * 1024 * 1024, len(r.raw)
    snap = r.json()
    reset(fixture())
    imp = call("POST", "/_test/import", snap, timeout=30)
    assert imp.status == 204, imp
    ada = Client(call("POST", "/auth/login", {"email": "ada@example.com", "password": "correct horse"}).json()["token"])
    assert ada.balance() == 10 ** 9
