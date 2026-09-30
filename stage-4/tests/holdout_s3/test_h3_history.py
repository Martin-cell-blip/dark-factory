"""Holdout: stage-3 timestamps, GET /me as_of, GET /statement, revisions and corrections."""
import pytest

from holdout3_client import (assert_error, burst, call, correct, fixture, iso, make_world,
                             new_key, no_5xx, pay, q, reset, settle, shift, statement, user)

T1, T2, T3 = iso(-3 * 3600), iso(-2 * 3600), iso(-3600)
CORR_FIELDS = {"payment_id", "revision", "amount", "effective_at", "recorded_at", "reason"}


def seeded(payments, users=None, **kw):
    return make_world(fixture(users=users or [user("ada", 900), user("bob", 100), user("cy", 0)],
                              payments=payments, **kw))


def p(pid, frm, to, amount, at, vis="public", note=""):
    return {"id": pid, "from_user_id": f"u_{frm}", "to_user_id": f"u_{to}", "amount": amount,
            "note": note, "visibility": vis, "created_at": at}


# A history where bob's balance dips to 0 between two receipts:
#   t1 ada->bob 100, t2 bob->cy 100, t3 cy->bob 100.  Openings: ada 1000, bob 0, cy 0.
HISTORY = [p("p_1", "ada", "bob", 100, T1), p("p_2", "bob", "cy", 100, T2), p("p_3", "cy", "bob", 100, T3)]
# One payment only: ada->bob 100 at t1.  Openings: ada 1000, bob 0, cy 0.
SIMPLE = [p("p_1", "ada", "bob", 100, T1)]
# A correction moves the whole payment to its new effective time with its new amount.


def body(rev=1, amount=0, at=None, reason="fix"):
    return {"expected_revision": rev, "amount": amount, "effective_at": at or iso(-1), "reason": reason}


# ---- timestamps and seeding ------------------------------------------------------------------

def test_seeded_created_at_kept_and_future_rejected():
    w = seeded(HISTORY)
    feed = w.bob.get("/activity").json()["payments"]
    assert [x["payment_id"] for x in feed] == ["p_3", "p_2", "p_1"]
    assert {x["payment_id"]: x["created_at"] for x in feed}["p_1"].startswith(T1[:19])
    assert (w.ada.me()["balance"], w.bob.me()["balance"], w.cy.me()["balance"]) == (900, 100, 0)
    bad = fixture(users=[user("ada", 900), user("bob", 100)],
                  payments=[p("p_x", "ada", "bob", 100, iso(3600))])
    assert_error(call("POST", "/_test/reset", bad), 422, "validation_failed")
    assert w.bob.me()["balance"] == 100  # unchanged


def test_omitted_created_at_is_reset_time_before_api_payments():
    w = make_world(fixture(users=[user("ada", 900), user("bob", 100)],
                           payments=[{"id": "p_s", "from_user_id": "u_ada", "to_user_id": "u_bob",
                                      "amount": 100}]))
    api = pay(w.ada, "bob", 1).json()
    feed = w.ada.get("/activity").json()["payments"]
    assert [x["payment_id"] for x in feed] == [api["payment_id"], "p_s"]
    seed_at = feed[1]["created_at"]
    assert seed_at <= api["created_at"] or shift(seed_at, 0) <= shift(api["created_at"], 0)


# ---- GET /me as_of ----------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["2026-09-24", "2026-09-24T13:20:00", "", "yesterday",
                                 "2026-13-40T00:00:00+00:00"])
def test_as_of_invalid(world, bad):
    assert_error(world.ada.get(f"/me?as_of={q(bad)}"), 422, "validation_failed")


def test_as_of_values_and_echo():
    w = seeded(HISTORY)
    me = lambda at: w.bob.get(f"/me?as_of={q(at)}").json()
    assert me(shift(T1, -1))["balance"] == 0            # opening
    assert me(T1)["balance"] == 100                     # inclusive at exactly created_at
    assert me(shift(T2, 1))["balance"] == 0
    assert me(iso(0))["balance"] == 100                 # current
    off = "2026-01-01T09:00:00+09:00"
    r = w.bob.get(f"/me?as_of={q(off)}").json()
    assert r["as_of"] == off
    for f in ("balance", "total", "available", "held"):
        assert f in r
    assert "as_of" not in w.bob.get("/me").json()


# ---- GET /statement ---------------------------------------------------------------------------

def test_statement_window_balances_and_signs():
    w = seeded(HISTORY + [p("p_4", "ada", "cy", 7, T2)])  # public, not bob's
    s = statement(w.bob).json()
    assert {"opening_balance", "entries", "closing_balance", "has_more", "snapshot"} <= set(s)
    assert s["opening_balance"] == 0 and s["closing_balance"] == 100
    assert [(e["payment"]["payment_id"], e["delta"], e["balance_after"]) for e in s["entries"]] == \
        [("p_1", 100, 100), ("p_2", -100, 0), ("p_3", 100, 100)]
    for e in s["entries"]:
        assert {"revision", "effective_at", "recorded_at"} <= set(e)
    half = statement(w.bob, **{"from": T2, "to": T3}).json()
    assert [e["payment"]["payment_id"] for e in half["entries"]] == ["p_2"]  # [from, to)
    assert half["opening_balance"] == 100 and half["closing_balance"] == 0
    assert half["opening_balance"] + sum(e["delta"] for e in half["entries"]) == half["closing_balance"]


def test_statement_ties_by_payment_id_and_paging():
    same = T2
    w = seeded([p("p_b", "ada", "bob", 10, same), p("p_a", "ada", "bob", 20, same),
                p("p_c", "bob", "cy", 5, T3)], users=[user("ada", 970), user("bob", 25), user("cy", 5)])
    full = statement(w.bob).json()
    assert [e["payment"]["payment_id"] for e in full["entries"]] == ["p_a", "p_b", "p_c"]
    pages = [statement(w.bob, limit=1, offset=i).json() for i in range(4)]
    assert [pg["entries"][0]["balance_after"] if pg["entries"] else None for pg in pages] == [20, 30, 25, None]
    assert [pg["has_more"] for pg in pages] == [True, True, False, False]
    for pg in pages:
        assert pg["opening_balance"] == 0 and pg["closing_balance"] == 25
    for bad in ("from=2026-09-24", "to=", "limit=0", "limit=201", "offset=-1", "limit=1e1"):
        assert_error(w.bob.get(f"/statement?{bad}"), 422, "validation_failed")


def test_statement_requires_token():
    make_world()
    assert_error(call("GET", "/statement"), 401, "unauthenticated")


# ---- revisions and corrections -------------------------------------------------------------------

def test_revision_one_and_permissions():
    w = seeded(HISTORY)
    r = w.ada.get("/payments/p_1/revisions")
    assert r.status == 200, r
    revs = r.json()["revisions"]
    assert len(revs) == 1 and CORR_FIELDS <= set(revs[0])
    assert (revs[0]["revision"], revs[0]["amount"], revs[0]["reason"]) == (1, 100, "")
    assert revs[0]["effective_at"] == revs[0]["recorded_at"]
    assert w.bob.get("/payments/p_1/revisions").status == 200
    assert_error(w.cy.get("/payments/p_1/revisions"), 404, "not_found")  # public, third party
    assert_error(call("GET", "/payments/p_1/revisions"), 401, "unauthenticated")


@pytest.mark.parametrize("b", [
    {"amount": 50, "effective_at": T3, "reason": "x"},                                   # missing rev
    {"expected_revision": 1, "effective_at": T3, "reason": "x"},                          # missing amount
    {"expected_revision": 1, "amount": 50, "reason": "x"},                                # missing at
    {"expected_revision": 1, "amount": 50, "effective_at": T3},                           # missing reason
    {"expected_revision": 0, "amount": 50, "effective_at": T3, "reason": "x"},
    {"expected_revision": 1, "amount": -1, "effective_at": T3, "reason": "x"},
    {"expected_revision": 1, "amount": 1000000001, "effective_at": T3, "reason": "x"},
    {"expected_revision": 1, "amount": 1.5, "effective_at": T3, "reason": "x"},
    {"expected_revision": 1, "amount": 50, "effective_at": T3, "reason": ""},
    {"expected_revision": 1, "amount": 50, "effective_at": T3, "reason": "r" * 201},
    {"expected_revision": 1, "amount": 50, "effective_at": "2026-09-20", "reason": "x"},
    {"expected_revision": 1, "amount": 50, "effective_at": iso(3600), "reason": "x"},
])
def test_correction_validation(b):
    w = seeded(HISTORY)
    assert_error(correct(w.ada, "p_1", b), 422, "validation_failed")
    assert len(w.ada.get("/payments/p_1/revisions").json()["revisions"]) == 1


def test_correction_permissions_and_keys():
    w = seeded(HISTORY)
    assert_error(correct(w.bob, "p_1", body(amount=50)), 403, "forbidden")      # receiver
    assert_error(correct(w.cy, "p_1", body(amount=50)), 403, "forbidden")
    assert_error(correct(w.ada, "p_nope", body(amount=50)), 404, "not_found")
    assert_error(call("POST", "/payments/p_1/corrections", body(amount=50), key=new_key()), 401,
                 "unauthenticated")
    assert_error(w.ada.post("/payments/p_1/corrections", body(amount=50)), 400, "missing_idempotency_key")
    assert_error(w.ada.post("/payments/p_1/corrections", body(amount=50), key="k" * 256), 422,
                 "validation_failed")


def test_correction_decrease_moves_back_and_replay():
    w = seeded(SIMPLE)
    k = new_key()
    b = body(amount=40, at=T3, reason="partial refund")
    r1 = correct(w.ada, "p_1", b, key=k)
    assert r1.status == 201, r1
    c1 = r1.json()
    assert CORR_FIELDS <= set(c1) and (c1["revision"], c1["amount"], c1["reason"]) == (2, 40, "partial refund")
    assert c1["effective_at"].startswith(T3[:19])
    assert (w.ada.me()["balance"], w.bob.me()["balance"]) == (960, 40)
    w.conserved()
    r2 = correct(w.ada, "p_1", body(rev=2, amount=70, at=iso(-1), reason="again"))
    assert r2.status == 201 and r2.json()["revision"] == 3
    assert (w.ada.me()["balance"], w.bob.me()["balance"]) == (930, 70)   # increase debits sender
    again = correct(w.ada, "p_1", b, key=k)
    assert again.status == 200 and again.json() == c1
    assert_error(correct(w.ada, "p_1", body(amount=41, at=T3, reason="partial refund"), key=k),
                 409, "idempotency_key_reuse")
    assert_error(correct(w.ada, "p_1", body(rev=2, amount=10, at=T3)), 409, "stale_revision")
    revs = w.bob.get("/payments/p_1/revisions").json()["revisions"]
    assert [x["revision"] for x in revs] == [1, 2, 3] and revs[1] == c1
    rec = [x["recorded_at"] for x in revs]
    assert shift(rec[0], 0) < shift(rec[1], 0) < shift(rec[2], 0)
    # originals: activity and original replay unchanged
    feed = {x["payment_id"]: x for x in w.ada.get("/activity").json()["payments"]}
    assert feed["p_1"]["amount"] == 100 and len(feed) == 1
    assert w.conserved() == {"ada": 930, "bob": 70, "cy": 0}


def test_correction_keeps_parties_and_visibility_and_original_replay(world):
    k = new_key()
    orig = pay(world.ada, "bob", 300, key=k, note="rent", visibility="private").json()
    assert correct(world.ada, orig["payment_id"], body(amount=200)).status == 201
    r = pay(world.ada, "bob", 300, key=k, note="rent", visibility="private")
    assert r.status == 200 and r.json() == orig
    assert world.cy.get("/activity").json()["payments"] == []
    feed = world.bob.get("/activity").json()["payments"]
    assert [(x["payment_id"], x["amount"], x["visibility"]) for x in feed] == [(orig["payment_id"], 300, "private")]


def test_zero_reverses_and_insufficient_funds_precedes():
    w = seeded(HISTORY)
    assert pay(w.bob, "cy", 100).status == 201            # bob now 0
    assert_error(correct(w.ada, "p_1", body(amount=0, at=iso(-1))), 409, "insufficient_funds")
    assert len(w.ada.get("/payments/p_1/revisions").json()["revisions"]) == 1
    w.conserved()


def test_historical_overdraft_by_effective_time():
    w = seeded(HISTORY)
    before = statement(w.bob).json()
    # bob only stays nonnegative at t2 while p_1 (100) takes effect before t2
    assert_error(correct(w.ada, "p_1", body(amount=0, at=T1)), 409, "historical_overdraft")
    k = new_key()
    assert_error(correct(w.ada, "p_1", body(amount=100, at=shift(T2, 60)), key=k), 409,
                 "historical_overdraft")
    assert statement(w.bob).json()["entries"] == before["entries"]
    assert len(w.ada.get("/payments/p_1/revisions").json()["revisions"]) == 1
    r = correct(w.ada, "p_1", body(amount=100, at=shift(T2, -60)), key=k)  # 4xx key is a first use
    assert r.status == 201, r
    s = statement(w.bob).json()
    assert [(e["payment"]["payment_id"], e["balance_after"]) for e in s["entries"]] ==         [("p_1", 100), ("p_2", 0), ("p_3", 100)]
    assert w.conserved() == {"ada": 900, "bob": 100, "cy": 0}


def test_boundary_combines_movements_at_one_instant():
    # bob receives 100 (p_z) and sends 100 (p_a) at the same instant; a debit-first id order must
    # not be read as a transient overdraft.
    w = seeded([p("p_z", "ada", "bob", 100, T2), p("p_a", "bob", "cy", 100, T2)],
               users=[user("ada", 900), user("bob", 0), user("cy", 100)])
    r = correct(w.ada, "p_z", body(amount=150, at=T2))
    assert r.status == 201, r
    assert w.conserved() == {"ada": 850, "bob": 50, "cy": 100}


def test_known_at_and_effective_as_of():
    w = seeded(SIMPLE)
    c = correct(w.ada, "p_1", body(amount=40, at=T3)).json()
    before, after = shift(c["recorded_at"], -0.5), shift(c["recorded_at"], 0.001)
    me = lambda **kv: w.bob.get("/me?" + "&".join(f"{k}={q(v)}" for k, v in kv.items())).json()
    assert me(as_of=shift(T1, 1), known_at=before)["balance"] == 100   # rev 1: 100 at t1
    assert me(as_of=shift(T3, 1), known_at=before)["balance"] == 100
    assert me(as_of=shift(T1, 1), known_at=after)["balance"] == 0      # rev 2: 40 at t3
    assert me(as_of=T3, known_at=after)["balance"] == 40               # inclusive
    assert me(as_of=shift(T3, 1), known_at=after)["balance"] == 40
    r = me(known_at=before)
    assert r["known_at"] == before and r["balance"] == 100
    assert me(known_at=iso(86400))["balance"] == 40            # future known_at allowed
    assert me(known_at=shift(T1, -60))["balance"] == 0         # nothing recorded yet
    assert me()["balance"] == 40
    for bad in ("", "2026-09-24", "2026-09-24T10:00:00"):
        assert_error(w.bob.get(f"/me?known_at={q(bad)}"), 422, "validation_failed")
        assert_error(w.bob.get(f"/statement?known_at={q(bad)}"), 422, "validation_failed")


def test_statement_with_corrections():
    w = seeded(SIMPLE + [p("p_9", "bob", "cy", 30, T2)],
               users=[user("ada", 900), user("bob", 70), user("cy", 30)])
    r = correct(w.ada, "p_1", body(amount=30, at=shift(T2, -60), reason="lower"))
    assert r.status == 201, r
    c = r.json()
    s = statement(w.bob).json()
    got = [(e["payment"]["payment_id"], e["revision"], e["delta"], e["payment"]["amount"],
            e["balance_after"]) for e in s["entries"]]
    assert got == [("p_1", 2, 30, 30, 30), ("p_9", 1, -30, 30, 0)]
    assert s["entries"][0]["recorded_at"] == c["recorded_at"]
    assert s["entries"][0]["effective_at"] == c["effective_at"]
    assert s["opening_balance"] + sum(e["delta"] for e in s["entries"]) == s["closing_balance"] == 0
    old = statement(w.bob, known_at=shift(c["recorded_at"], -0.5)).json()
    assert [(e["payment"]["payment_id"], e["revision"], e["payment"]["amount"]) for e in old["entries"]] ==         [("p_1", 1, 100), ("p_9", 1, 30)]
    win = statement(w.bob, **{"from": shift(T1, -1), "to": shift(T1, 1)}).json()
    assert win["entries"] == []                               # moved out of that window
    z = correct(w.bob, "p_9", body(amount=0, at=iso(-1), reason="void"))
    assert z.status == 201, z
    s2 = statement(w.bob).json()
    assert [(e["payment"]["payment_id"], e["delta"]) for e in s2["entries"]] == [("p_1", 30), ("p_9", 0)]
    w.conserved()


def test_snapshot_freezes_and_errors():
    w = seeded(HISTORY)
    first = statement(w.bob, limit=2).json()
    tok = first["snapshot"]
    assert pay(w.ada, "bob", 5).status == 201
    assert correct(w.cy, "p_3", body(amount=40, at=iso(-1))).status == 201
    p1 = w.bob.get(f"/statement?snapshot={q(tok)}&limit=2&offset=0").json()
    p2 = w.bob.get(f"/statement?snapshot={q(tok)}&limit=2&offset=2").json()
    assert p1["entries"] == first["entries"] and p1["has_more"] is True
    assert [e["payment"]["payment_id"] for e in p2["entries"]] == ["p_3"] and p2["has_more"] is False
    assert p1["closing_balance"] == first["closing_balance"] == 100
    assert w.bob.get(f"/statement?snapshot={q(tok)}&offset=9").json()["entries"] == []
    for extra in (f"from={q(T1)}", f"to={q(T3)}", f"known_at={q(T3)}"):
        assert_error(w.bob.get(f"/statement?snapshot={q(tok)}&{extra}"), 422, "validation_failed")
    assert w.bob.get(f"/statement?snapshot={q(tok)}&whatever=1").status == 200
    assert_error(w.ada.get(f"/statement?snapshot={q(tok)}"), 404, "not_found")
    assert_error(w.bob.get("/statement?snapshot=nope"), 404, "not_found")
    reset(fixture())
    from holdout3_client import login, Client
    bob = Client(login("bob@example.com"))
    assert_error(bob.get(f"/statement?snapshot={q(tok)}"), 404, "not_found")


def test_concurrent_corrections_same_revision():
    for _ in range(10):
        w = seeded(SIMPLE)
        rs = burst(lambda i: correct(w.ada, "p_1", body(amount=10 + i, at=iso(-1))), 20)
        no_5xx(rs)
        assert sum(r.status == 201 for r in rs) == 1, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert_error(r, 409, "stale_revision")
        w.conserved()
        k = new_key()
        b = body(rev=2, amount=5, at=iso(-1))
        rs = burst(lambda i: correct(w.ada, "p_1", b, key=k), 20)
        no_5xx(rs)
        assert sorted(r.status for r in rs) == [200] * 19 + [201]
        w.conserved()


def test_settlement_members():
    w = make_world(fixture(operators=["u_ada"]))
    s = settle(w.ada, [{"from_handle": "bob", "to_handle": "cy", "amount": 5}]).json()
    pid = s["payments"][0]["payment_id"]
    rev = w.bob.get(f"/payments/{pid}/revisions").json()["revisions"][0]
    assert rev["effective_at"] == rev["recorded_at"] == s["committed_at"]
    assert_error(correct(w.bob, pid, body(amount=1)), 422, "linked_payment_immutable")
    assert_error(w.ada.get(f"/payments/{pid}/revisions"), 404, "not_found")  # operator, not a party
