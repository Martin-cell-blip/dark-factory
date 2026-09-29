"""Item 2: reset replaces all state with the fixture."""
import seed
from client import expect, login, request


def test_reset_returns_204_without_auth():
    resp = request("POST", "/_test/reset", seed.fixture())
    expect(resp, 204)
    assert resp.body == b""


def test_later_requests_see_only_the_fixture(reset):
    reset(seed.fixture())
    ann = login("ann@pocket.test", seed.PASSWORD)
    expect(ann.write("/payments", {"to_handle": "ben", "amount": 100}), 201)
    reset(seed.fixture(users=[seed.user("dan", 70), seed.user("eve", 30)]))
    expect(request("POST", "/auth/login", {"email": "ann@pocket.test",
                                           "password": seed.PASSWORD}), 401, "unauthenticated")
    expect(ann.get("/me"), 401, "unauthenticated")
    dan = login("dan@pocket.test", seed.PASSWORD)
    assert dan.balance() == 70
    assert dan.get("/activity").json()["payments"] == []


def test_repeated_resets_work(reset):
    for _ in range(3):
        reset(seed.fixture())
        ann = login("ann@pocket.test", seed.PASSWORD)
        assert ann.balance() == 10000


def test_seeded_balance_is_post_payment_and_records_are_readable(reset):
    fx = seed.fixture(
        payments=[{"id": "p_seed", "from_user_id": "u_ann", "to_user_id": "u_ben",
                   "amount": 500, "note": "coffee", "visibility": "public"}],
        requests=[{"id": "rq_seed", "requester_id": "u_ben", "payer_id": "u_ann",
                   "amount": 1200, "note": "taxi", "status": "pending"}])
    reset(fx)
    ann = login("ann@pocket.test", seed.PASSWORD)
    ben = login("ben@pocket.test", seed.PASSWORD)
    assert ann.balance() == 10000 and ben.balance() == 2500
    [payment] = ann.get("/activity").json()["payments"]
    assert payment["payment_id"] == "p_seed" and payment["amount"] == 500
    assert payment["note"] == "coffee" and payment["from_handle"] == "ann"
    [req] = ann.get("/requests").json()["requests"]
    assert req["request_id"] == "rq_seed" and req["status"] == "pending"
    assert req["payer_handle"] == "ann" and req["requester_handle"] == "ben"
    paid = expect(ann.write("/requests/rq_seed/pay", {}), 201).json()
    assert paid["request_id"] == "rq_seed" and paid["amount"] == 1200


def test_settlement_operators_default_to_none(reset):
    reset(seed.fixture())
    ann = login("ann@pocket.test", seed.PASSWORD)
    body = {"transfers": [{"from_handle": "ann", "to_handle": "ben", "amount": 1}]}
    expect(ann.write("/settlements", body), 403, "forbidden")


def test_seeded_ids_verbatim_and_statuses_honoured(reset):
    fx = seed.fixture(
        payments=[{"id": "pay-Seed.1", "from_user_id": "u_ann", "to_user_id": "u_cat",
                   "amount": 5}],
        requests=[{"id": f"req-{status}", "requester_id": "u_ben", "payer_id": "u_ann",
                   "amount": 10, "status": status}
                  for status in ("pending", "paid", "declined", "cancelled")])
    reset(fx)
    ann = login("ann@pocket.test", seed.PASSWORD)
    assert ann.get("/me").json()["user_id"] == "u_ann"
    [payment] = ann.get("/activity").json()["payments"]
    assert payment["payment_id"] == "pay-Seed.1" and payment["settlement_id"] is None
    listed = {r["request_id"]: r["status"] for r in ann.get("/requests").json()["requests"]}
    assert listed == {f"req-{s}": s for s in ("pending", "paid", "declined", "cancelled")}
    for status in ("paid", "declined", "cancelled"):
        expect(ann.write(f"/requests/req-{status}/pay", {}), 409, "request_not_pending")
    expect(ann.post("/requests/req-paid/decline"), 409, "request_not_pending")
    expect(ann.post("/requests/req-declined/decline"), 200)
