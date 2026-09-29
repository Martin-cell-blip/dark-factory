"""Item 7: capture creates a payment and, by default, closes the authorisation."""
from client import balances_sum, expect
from holdfx import authorize, capture, me

PAYMENT = {"payment_id", "from_user_id", "from_handle", "to_user_id", "to_handle", "amount",
           "currency", "note", "visibility", "request_id", "settlement_id",
           "authorization_id", "created_at"}


def test_default_capture_takes_the_remaining_amount(world):
    held = authorize(world.ann, "ben", 2000, note="deposit", visibility="private")
    payment = capture(world.ben, held["authorization_id"]).json()
    assert set(payment) == PAYMENT
    assert payment["authorization_id"] == held["authorization_id"]
    assert payment["request_id"] is None and payment["settlement_id"] is None
    assert payment["amount"] == 2000 and payment["from_handle"] == "ann"
    assert payment["to_handle"] == "ben" and payment["note"] == "deposit"
    assert payment["visibility"] == "private" and payment["currency"] == "EUR"
    assert me(world.ann) == {**me(world.ann), "total": 8000, "held": 0, "available": 8000}
    assert me(world.ben)["total"] == 4500
    assert balances_sum(world.everyone) == world.total


def test_partial_final_capture_releases_the_remainder_at_once(world):
    held = authorize(world.ann, "ben", 2000)
    payment = capture(world.ben, held["authorization_id"], {"amount": 1500}).json()
    assert payment["amount"] == 1500
    assert me(world.ann) == {**me(world.ann), "total": 8500, "held": 0, "available": 8500}
    [item] = expect(world.ann.get("/authorizations"), 200).json()["authorizations"]
    assert item["status"] == "captured" and item["captured_amount"] == 1500
    assert item["payment_id"] == payment["payment_id"]
    assert item["remaining_amount"] == 0 and item["payment_ids"] == [payment["payment_id"]]


def test_capture_is_a_feed_item_by_the_ordinary_rule(world):
    public = authorize(world.ann, "ben", 100)
    private = authorize(world.ann, "ben", 200, visibility="private")
    p1 = capture(world.ben, public["authorization_id"]).json()["payment_id"]
    p2 = capture(world.ben, private["authorization_id"]).json()["payment_id"]
    feed = lambda c: [p["payment_id"] for p in expect(c.get("/activity"), 200).json()["payments"]]
    assert feed(world.ann) == [p2, p1] and feed(world.ben) == [p2, p1]
    assert feed(world.cat) == [p1]


def test_other_payments_carry_null_authorization_id(world):
    direct = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1}), 201).json()
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 2}), 201).json()
    paid = expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    assert direct["authorization_id"] is None and paid["authorization_id"] is None
    for item in expect(world.cat.get("/activity"), 200).json()["payments"]:
        assert item["authorization_id"] is None
