"""Item 6: holds reserve money without moving it; held funds pay for nothing else."""
import seed
from client import balances_sum, expect, login
from holdfx import authorize, me


def test_a_hold_moves_no_money(world):
    authorize(world.ann, "ben", 4000)
    assert balances_sum(world.everyone) == world.total
    assert me(world.ann)["total"] == 10000 and me(world.ben)["total"] == 2500


def test_held_funds_cannot_fund_payments_requests_or_holds(world):
    authorize(world.cat, "ann", 400)
    expect(world.cat.write("/payments", {"to_handle": "ben", "amount": 101}),
           409, "insufficient_funds")
    expect(world.cat.write("/payments", {"to_handle": "ben", "amount": 100}), 201)
    rq = expect(world.ann.write("/requests", {"payer_handle": "cat", "amount": 1}), 201).json()
    expect(world.cat.write(f"/requests/{rq['request_id']}/pay", {}), 409, "insufficient_funds")
    expect(world.cat.write("/authorizations", {"to_handle": "ben", "amount": 1}),
           409, "insufficient_funds")
    body = me(world.cat)
    assert body == {**body, "total": 400, "held": 400, "available": 0}


def test_held_funds_cannot_fund_a_settlement_net_debit(reset):
    fx = seed.fixture(settlement_operator_ids=["u_ann"])
    reset(fx)
    ann = login("ann@pocket.test", seed.PASSWORD)
    cat = login("cat@pocket.test", seed.PASSWORD)
    authorize(cat, "ann", 450)
    refused = {"transfers": [{"from_handle": "cat", "to_handle": "ben", "amount": 60}]}
    expect(ann.write("/settlements", refused), 409, "insufficient_funds")
    netted = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 100},
                            {"from_handle": "cat", "to_handle": "ben", "amount": 150}]}
    expect(ann.write("/settlements", netted), 201)
    assert me(cat) == {**me(cat), "total": 450, "held": 450, "available": 0}


def test_without_holds_stage_one_is_unchanged(world):
    payment = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 10000}),
                     201).json()
    assert payment["authorization_id"] is None
    assert me(world.ann) == {**me(world.ann), "total": 0, "available": 0, "held": 0}
    assert expect(world.ben.get("/authorizations"), 200).json()["authorizations"] == []


def test_payments_requests_and_splits_stay_immediate(world):
    authorize(world.ann, "ben", 1000)
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 500}), 201)
    assert me(world.ann)["total"] == 9500 and me(world.ann)["held"] == 1000
    assert me(world.ben)["total"] == 3000 and me(world.ben)["available"] == 3000
    rq = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 200}),
                201).json()
    expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201)
    assert me(world.ann)["total"] == 9300
    split = expect(world.cat.write("/splits", {"amount": 30000,
                                               "participant_handles": ["ann", "cat"]}),
                   201).json()
    assert split["requests"][0]["amount"] == 15000 and split["requests"][0]["status"] == "pending"
    assert me(world.ann)["held"] == 1000
