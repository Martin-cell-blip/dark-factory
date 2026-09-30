"""Holdout: stage-4 refunds and correction batches."""
import pytest

from holdout4_client import (BASE_S3, Client, ask, assert_error, authorize, batch, burst, call,
                             capture, correct, fixture, iso, item, login, make_world, new_key,
                             no_5xx, pay, q, refund, reset, settle, shift, statement, user)


def cbody(amount, rev=1, at=None, reason="fix"):
    return {"expected_revision": rev, "amount": amount, "effective_at": at or iso(-1), "reason": reason}


@pytest.fixture
def ow():
    """ada 10000, bob 2500, cy 500, op 0 (settlement operator)."""
    return make_world(fixture(users=[user("ada", 10000), user("bob", 2500), user("cy", 500),
                                     user("op", 0)], operators=["u_op"]))


# ---- refunds ---------------------------------------------------------------------------------

def test_refund_shape_direction_and_replay(world):
    p = pay(world.ada, "bob", 1000, note="dinner 🍝", visibility="private").json()
    assert p["refund_of"] is None
    k = new_key()
    r1 = refund(world.bob, p["payment_id"], 300, key=k)
    assert r1.status == 201, r1
    rf = r1.json()
    assert (rf["from_handle"], rf["to_handle"], rf["amount"], rf["refund_of"], rf["request_id"],
            rf["authorization_id"], rf["settlement_id"], rf["note"], rf["visibility"]) == \
        ("bob", "ada", 300, p["payment_id"], None, None, None, "dinner 🍝", "private")
    assert rf["payment_id"] != p["payment_id"]
    r2 = refund(world.bob, p["payment_id"], 300, key=k)
    assert r2.status == 200 and r2.json() == rf
    assert_error(refund(world.bob, p["payment_id"], 301, key=k), 409, "idempotency_key_reuse")
    assert (world.ada.balance(), world.bob.balance()) == (9300, 3200)
    feed_cy = world.cy.get("/activity").json()["payments"]
    assert feed_cy == []                                  # private stays private
    ids = [x["payment_id"] for x in world.ada.get("/activity").json()["payments"]]
    assert ids == [rf["payment_id"], p["payment_id"]]
    for c in (world.ada, world.bob):
        s = statement(c).json()
        assert rf["payment_id"] in [e["payment"]["payment_id"] for e in s["entries"]]
    world.conserved()


def test_refund_key_rules(world):
    pid = pay(world.ada, "bob", 100).json()["payment_id"]
    assert_error(world.bob.post(f"/payments/{pid}/refunds", {"amount": 1}), 400, "missing_idempotency_key")
    assert_error(world.bob.post(f"/payments/{pid}/refunds", {"amount": 1}, key="k" * 256), 422,
                 "validation_failed")
    assert_error(call("POST", f"/payments/{pid}/refunds", {"amount": 1}, key=new_key()), 401,
                 "unauthenticated")


@pytest.mark.parametrize("amount", [0, -1, 1.5, "5", True, None, 1000000001])
def test_refund_invalid_amount(world, amount):
    pid = pay(world.ada, "bob", 100).json()["payment_id"]
    assert_error(refund(world.bob, pid, amount), 422, "validation_failed")


def test_refund_rules_and_order(world):
    pid = pay(world.ada, "bob", 100).json()["payment_id"]
    assert_error(refund(world.ada, pid, 10), 403, "forbidden")        # sender
    assert_error(refund(world.cy, pid, 10), 403, "forbidden")         # third party
    assert_error(refund(world.bob, "p_nope", 10), 404, "not_found")
    assert_error(refund(world.bob, "p_nope", 0), 422, "validation_failed")   # amount before 404
    rf = refund(world.bob, pid, 60).json()
    assert_error(refund(world.ada, rf["payment_id"], 10), 422, "invalid_refund_target")
    assert_error(refund(world.bob, pid, 41), 422, "refund_exceeds_payment")
    assert refund(world.bob, pid, 40).status == 201
    assert_error(refund(world.bob, pid, 1), 422, "refund_exceeds_payment")
    world.conserved()


def test_refund_against_available_and_corrected_amount(world):
    pid = pay(world.cy, "bob", 500).json()["payment_id"]     # cy 0, bob 3000
    assert correct(world.cy, pid, cbody(200)).status == 201   # bob 2700, cy 300
    assert_error(refund(world.bob, pid, 201), 422, "refund_exceeds_payment")
    authorize(world.bob, "ada", 2600)                         # bob available 100
    assert_error(refund(world.bob, pid, 150), 409, "insufficient_funds")
    assert refund(world.bob, pid, 100).status == 201
    world.conserved()


def test_refund_of_request_payment_and_capture(world):
    rq = ask(world.bob, "ada", 400).json()
    p = world.ada.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key()).json()
    assert refund(world.bob, p["payment_id"], 400).status == 201
    got = [x for x in world.bob.get("/requests").json()["requests"] if x["request_id"] == rq["request_id"]][0]
    assert got["status"] == "paid"
    a = authorize(world.ada, "bob", 1000).json()
    cp = capture(world.bob, a["authorization_id"], {"amount": 600}).json()
    assert world.ada.me()["held"] == 0
    r = refund(world.bob, cp["payment_id"], 600)
    assert r.status == 201 and r.json()["authorization_id"] is None
    auth = world.ada.get("/authorizations").json()["authorizations"][0]
    assert auth["status"] == "captured" and auth["remaining_amount"] == 0
    assert world.ada.me()["held"] == 0                         # hold not restored
    world.conserved()


def test_refund_and_capture_are_immutable_and_correction_floor(world):
    pid = pay(world.ada, "bob", 500).json()["payment_id"]
    rf = refund(world.bob, pid, 200).json()
    assert_error(correct(world.bob, rf["payment_id"], cbody(100)), 422, "linked_payment_immutable")
    assert_error(correct(world.ada, pid, cbody(199)), 422, "refund_exceeds_payment")
    assert correct(world.ada, pid, cbody(200)).status == 201
    a = authorize(world.ada, "bob", 100).json()
    cp = capture(world.bob, a["authorization_id"]).json()
    assert_error(correct(world.ada, cp["payment_id"], cbody(50)), 422, "linked_payment_immutable")
    world.conserved()


def test_correction_debit_checked_against_available(world):
    pid = pay(world.ada, "cy", 500).json()["payment_id"]     # cy 1000
    authorize(world.cy, "bob", 900)                           # cy available 100
    assert_error(correct(world.ada, pid, cbody(300)), 409, "insufficient_funds")   # debits cy 200
    assert correct(world.ada, pid, cbody(400)).status == 201
    world.conserved()


def test_refund_of_settlement_member_keeps_membership(ow):
    s = settle(ow.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                       {"from_handle": "bob", "to_handle": "cy", "amount": 50}]).json()
    m = s["payments"][0]
    rf = refund(ow.bob, m["payment_id"], 30).json()
    assert rf["settlement_id"] is None and rf["refund_of"] == m["payment_id"]
    feed = {x["payment_id"]: x for x in ow.ada.get("/activity").json()["payments"]}
    assert feed[m["payment_id"]]["settlement_id"] == s["settlement_id"]
    ow.conserved()


def test_concurrent_refunds_never_exceed(world):
    for _ in range(10):
        w = make_world()
        pid = pay(w.ada, "bob", 1000).json()["payment_id"]
        rs = burst(lambda i: refund(w.bob, pid, 100), 30)
        no_5xx(rs)
        assert sum(r.status == 201 for r in rs) == 10, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert_error(r, 422, "refund_exceeds_payment")
        w.conserved()


# ---- correction batches -------------------------------------------------------------------------

def test_batch_auth_and_shape_errors(ow):
    pid = pay(ow.ada, "bob", 100).json()["payment_id"]
    assert_error(call("POST", "/correction-batches", {"corrections": [item(pid, 50)]}, key=new_key()),
                 401, "unauthenticated")
    assert_error(batch(ow.ada, [item(pid, 50)]), 403, "forbidden")
    assert_error(ow.op.post("/correction-batches", {"corrections": [item(pid, 50)]}), 400,
                 "missing_idempotency_key")
    for bad in ([], [item(pid, 50), item(pid, 40)], [item(pid, 1)] * 33):
        assert_error(batch(ow.op, bad), 422, "validation_failed")
    assert_error(ow.op.post("/correction-batches", {}, key=new_key()), 422, "validation_failed")
    for bad_item in ({**item(pid, 50), "reason": ""}, {**item(pid, 50), "expected_revision": 0},
                     {**item(pid, 50), "effective_at": iso(3600)}, {k: v for k, v in item(pid, 50).items() if k != "amount"}):
        assert_error(batch(ow.op, [bad_item]), 422, "validation_failed")
    assert_error(batch(ow.op, [item("p_nope", 1)]), 404, "not_found")
    assert_error(batch(ow.op, [item(pid, 50, rev=2)]), 409, "stale_revision")
    assert len(ow.ada.get(f"/payments/{pid}/revisions").json()["revisions"]) == 1


def test_batch_success_shape_replay_and_revisions(ow):
    p1 = pay(ow.ada, "bob", 300).json()
    rq = ask(ow.cy, "bob", 200).json()
    p2 = ow.bob.post(f"/requests/{rq['request_id']}/pay", {}, key=new_key()).json()
    c = correct(ow.ada, p1["payment_id"], cbody(250)).json()        # p1 now rev 2
    k = new_key()
    items = [item(p1["payment_id"], 100, rev=2, reason="lower"), {**item(p2["payment_id"], 150), "extra": 1}]
    r = batch(ow.op, items, key=k)
    assert r.status == 201, r
    b = r.json()
    assert set(b) >= {"correction_batch_id", "recorded_at", "revisions"}
    assert [(x["payment_id"], x["revision"], x["amount"]) for x in b["revisions"]] == \
        [(p1["payment_id"], 3, 100), (p2["payment_id"], 2, 150)]
    for x in b["revisions"]:
        assert x["recorded_at"] == b["recorded_at"] and x["correction_batch_id"] == b["correction_batch_id"]
    assert shift(b["recorded_at"], 0) > shift(c["recorded_at"], 0)
    revs = ow.ada.get(f"/payments/{p1['payment_id']}/revisions").json()["revisions"]
    assert [x.get("correction_batch_id") for x in revs] == [None, None, b["correction_batch_id"]]
    assert revs[2] == b["revisions"][0]
    again = batch(ow.op, items, key=k)
    assert again.status == 200 and again.json() == b
    assert_error(batch(ow.op, [item(p1["payment_id"], 99, rev=3)], key=k), 409, "idempotency_key_reuse")
    assert (ow.ada.balance(), ow.bob.balance(), ow.cy.balance()) == (9900, 2450, 650)
    # originals unchanged
    feed = {x["payment_id"]: x for x in ow.ada.get("/activity").json()["payments"]}
    assert feed[p1["payment_id"]]["amount"] == 300
    ow.conserved()


def test_batch_rejects_linked_and_refund_floor(ow):
    p = pay(ow.ada, "bob", 300).json()
    rf = refund(ow.bob, p["payment_id"], 100).json()
    a = authorize(ow.ada, "bob", 100).json()
    cp = capture(ow.bob, a["authorization_id"]).json()
    assert_error(batch(ow.op, [item(rf["payment_id"], 0)]), 422, "linked_payment_immutable")
    assert_error(batch(ow.op, [item(cp["payment_id"], 0)]), 422, "linked_payment_immutable")
    assert_error(batch(ow.op, [item(p["payment_id"], 99)]), 422, "refund_exceeds_payment")
    # input order: first failing item decides
    assert_error(batch(ow.op, [item(p["payment_id"], 99), item("p_nope", 1)]), 422, "refund_exceeds_payment")
    assert_error(batch(ow.op, [item("p_nope", 1), item(p["payment_id"], 99)]), 404, "not_found")


def test_settlement_completeness_and_instants(ow):
    s = settle(ow.op, [{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                       {"from_handle": "bob", "to_handle": "cy", "amount": 50}]).json()
    m1, m2 = [x["payment_id"] for x in s["payments"]]
    assert_error(batch(ow.op, [item(m1, 0)]), 422, "incomplete_settlement")
    at = iso(-60)
    from datetime import datetime, timedelta, timezone
    d = datetime.fromisoformat(at)
    same_elsewhere = d.astimezone(timezone(timedelta(hours=5, minutes=30))).isoformat()
    assert_error(batch(ow.op, [item(m1, 0, at=at), item(m2, 0, at=shift(at, 1))]), 422, "validation_failed")
    # item errors precede completeness
    assert_error(batch(ow.op, [item(m1, 0, at=at), item("p_nope", 1)]), 404, "not_found")
    r = batch(ow.op, [item(m1, 0, at=at), item(m2, 0, at=same_elsewhere)])
    assert r.status == 201, r
    assert (ow.ada.balance(), ow.bob.balance(), ow.cy.balance()) == (10000, 2500, 500)
    assert_error(correct(ow.ada, m1, cbody(10, rev=2)), 422, "linked_payment_immutable")
    ow.conserved()


def test_batch_combined_affordability_and_precedence(ow):
    # bob receives 500 from ada, then pays 500 to cy. Reversing only ada->bob debits bob 500 now:
    # bob has 2500, fine; reversing bob->cy alone debits cy 500 (cy has 1000), fine.
    p1 = pay(ow.ada, "bob", 500).json()["payment_id"]
    p2 = pay(ow.bob, "cy", 500).json()["payment_id"]
    pay(ow.cy, "ada", 1000)                                   # cy now 0
    # reversing p2 alone debits cy 500 now: cy has 0 -> insufficient
    assert_error(batch(ow.op, [item(p2, 0)]), 409, "insufficient_funds")
    # combined: reverse p2 (cy -500, bob +500) and give cy 500 back via raising p1? p1 is ada->bob.
    # instead combine with a new payment bob->cy raised: p3 bob->cy 1 raised to 501 gives cy +500
    p3 = pay(ow.bob, "cy", 1).json()["payment_id"]
    pay(ow.cy, "ada", 1)                                      # cy 0 again
    r = batch(ow.op, [item(p2, 0), item(p3, 501)])
    assert r.status == 201, r                                 # net for cy: -500 +500 = 0
    ow.conserved()
    assert ow.cy.balance() == 0


def test_batch_historical_overdraft_and_nothing_changes(ow):
    reset(fixture(users=[user("ada", 900), user("bob", 100), user("cy", 0), user("op", 0)], operators=["u_op"],
                  payments=[{"id": "p_1", "from_user_id": "u_ada", "to_user_id": "u_bob", "amount": 100,
                             "created_at": iso(-3 * 3600)},
                            {"id": "p_2", "from_user_id": "u_bob", "to_user_id": "u_cy", "amount": 100,
                             "created_at": iso(-2 * 3600)},
                            {"id": "p_3", "from_user_id": "u_cy", "to_user_id": "u_bob", "amount": 100,
                             "created_at": iso(-3600)}]))
    op = Client(login("op@example.com"))
    bob = Client(login("bob@example.com"))
    k = new_key()
    before = statement(bob).json()["entries"]
    r = op.post("/correction-batches", {"corrections": [item("p_1", 100, at=iso(-5400))]}, key=k)
    assert_error(r, 409, "historical_overdraft")            # p_1 moved after p_2: bob negative at t2
    assert statement(bob).json()["entries"] == before
    r2 = op.post("/correction-batches", {"corrections": [item("p_1", 100, at=iso(-9000))]}, key=k)
    assert r2.status == 201, r2                               # key after 4xx is a first use


def test_batch_concurrency_with_single_corrections(ow):
    for _ in range(10):
        w = make_world(fixture(users=[user("ada", 10000), user("bob", 2500), user("op", 0)], operators=["u_op"]))
        pid = pay(w.ada, "bob", 500).json()["payment_id"]

        def act(i):
            if i % 2:
                return batch(w.op, [item(pid, 100 + i)])
            return correct(w.ada, pid, cbody(200 + i))
        rs = burst(act, 20)
        no_5xx(rs)
        assert sum(r.status == 201 for r in rs) == 1, [r.status for r in rs]
        for r in rs:
            if r.status != 201:
                assert_error(r, 409, "stale_revision")
        w.conserved()


def test_snapshot_and_settlement_retry_survive_batch(ow):
    k = new_key()
    t = [{"from_handle": "ada", "to_handle": "bob", "amount": 100}]
    s = settle(ow.op, t, key=k).json()
    st = statement(ow.ada).json()
    batch(ow.op, [item(s["payments"][0]["payment_id"], 40)])
    again = settle(ow.op, t, key=k)
    assert again.status == 200 and again.json() == s
    frozen = ow.ada.get(f"/statement?snapshot={q(st['snapshot'])}").json()
    assert frozen["entries"] == st["entries"]
    new = statement(ow.ada).json()
    assert new["entries"][-1]["payment"]["amount"] == 40


def test_stage4_export_roundtrip(ow):
    p = pay(ow.ada, "bob", 300).json()
    kr = new_key()
    rf = refund(ow.bob, p["payment_id"], 100, key=kr).json()
    kb = new_key()
    items = [item(p["payment_id"], 200)]
    b = batch(ow.op, items, key=kb).json()
    snap = call("GET", "/_test/export").json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    assert refund(ow.bob, p["payment_id"], 100, key=kr).json() == rf
    r = batch(ow.op, items, key=kb)
    assert r.status == 200 and r.json() == b
    assert_error(refund(ow.bob, p["payment_id"], 101), 422, "refund_exceeds_payment")
    ow.conserved()


@pytest.fixture
def stage3():
    assert BASE_S3, "set POCKETFUL_STAGE3_URL to a running stage-3 service of this team"
    return BASE_S3


def test_stage3_export_upgrades(stage3):
    reset(fixture(operators=["u_ada"]), base=stage3)
    ada3 = Client(login("ada@example.com", base=stage3), stage3)
    p = pay(ada3, "bob", 300).json()
    c = correct(ada3, p["payment_id"], cbody(200)).json()
    s = settle(ada3, [{"from_handle": "bob", "to_handle": "cy", "amount": 5}]).json()
    st = statement(ada3).json()
    snap = call("GET", "/_test/export", base=stage3).json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    ada = Client(ada3.token)
    frozen = ada.get(f"/statement?snapshot={q(st['snapshot'])}").json()
    assert frozen["entries"] == st["entries"]
    revs = ada.get(f"/payments/{p['payment_id']}/revisions").json()["revisions"]
    assert [x["revision"] for x in revs] == [1, 2] and revs[1]["amount"] == 200
    bob = Client(login("bob@example.com"))
    feed = {x["payment_id"]: x for x in bob.get("/activity").json()["payments"]}
    assert feed[s["payments"][0]["payment_id"]]["settlement_id"] == s["settlement_id"]
    assert_error(refund(bob, p["payment_id"], 201), 422, "refund_exceeds_payment")
    assert refund(bob, p["payment_id"], 200).status == 201
    r = batch(ada, [item(s["payments"][0]["payment_id"], 1)])
    assert r.status == 201, r
