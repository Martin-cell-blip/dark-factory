"""Item 4: refund effects."""
from client import balances_sum, expect
from refundfx import refund, settle
from timefx import me_at, pay, statement


def test_money_moves_back_atomically(world):
    original = pay(world.ann, "ben", 1000)
    refund(world.ben, original, 250)
    assert (world.ann.balance(), world.ben.balance()) == (9250, 3250)
    assert balances_sum(world.everyone) == world.total


def test_requests_and_authorizations_stay_closed(world):
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 500}), 201).json()
    paid = expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    refund(world.ben, paid, 500)
    [listed] = expect(world.ben.get("/requests"), 200).json()["requests"]
    assert listed["status"] == "paid" and listed["payment_id"] == paid["payment_id"]
    held = expect(world.ann.write("/authorizations", {"to_handle": "cat", "amount": 900}),
                  201).json()
    capture = expect(world.cat.write(f"/authorizations/{held['authorization_id']}/capture",
                                     {"amount": 400}), 201).json()
    refund(world.cat, capture, 400)
    [hold] = expect(world.ann.get("/authorizations"), 200).json()["authorizations"]
    assert hold["status"] == "captured" and hold["captured_amount"] == 400
    assert hold["remaining_amount"] == 0
    me = me_at(world.ann, as_of="2999-01-01T00:00:00+00:00")
    assert me["held"] == 0
    assert expect(world.ann.get("/me"), 200).json()["held"] == 0


def test_settlement_membership_never_changes(world):
    settled = settle(world.ann, ("ben", "cat", 100), ("cat", "ben", 40))
    first = settled["payments"][0]
    back = refund(world.cat, first, 60).json()
    assert back["settlement_id"] is None
    feed = {p["payment_id"]: p for p in expect(world.ben.get("/activity"), 200).json()["payments"]}
    assert [feed[p["payment_id"]]["settlement_id"] for p in settled["payments"]] == \
        [settled["settlement_id"]] * 2
    assert feed[back["payment_id"]]["settlement_id"] is None


def test_feed_and_statements(world):
    public = pay(world.ann, "ben", 100)
    private = pay(world.ann, "ben", 200, visibility="private")
    back_public = refund(world.ben, public, 10).json()
    back_private = refund(world.ben, private, 20).json()
    cat_feed = [p["payment_id"] for p in expect(world.cat.get("/activity"), 200).json()["payments"]]
    assert back_public["payment_id"] in cat_feed and back_private["payment_id"] not in cat_feed
    for client, sign in ((world.ann, 1), (world.ben, -1)):
        entries = {e["payment"]["payment_id"]: e for e in statement(client)["entries"]}
        assert entries[back_public["payment_id"]]["delta"] == 10 * sign
        assert entries[back_private["payment_id"]]["delta"] == 20 * sign
        assert entries[back_public["payment_id"]]["payment"]["refund_of"] == public["payment_id"]
