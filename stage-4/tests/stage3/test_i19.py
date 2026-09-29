"""Item 19: corrections against holds; statements show money movements only."""
from client import expect
from timefx import correct, pay, statement


def test_a_past_hold_makes_the_correction_an_overdraft(world):
    top_up = pay(world.ann, "ben", 1000)
    hold = expect(world.ben.write("/authorizations", {"to_handle": "cat", "amount": 3200}),
                  201).json()
    expect(world.ben.post(f"/authorizations/{hold['authorization_id']}/void"), 200)
    assert world.ben.balance() == 3500
    correct(world.ann, top_up["payment_id"], 0, top_up["created_at"], status=409,
            code="historical_overdraft")
    correct(world.ann, top_up["payment_id"], 700, top_up["created_at"], status=201)
    assert world.ben.balance() == 3200


def test_insufficient_funds_takes_precedence(world):
    top_up = pay(world.ann, "ben", 1000)
    expect(world.ben.write("/authorizations", {"to_handle": "cat", "amount": 3200}), 201)
    correct(world.ann, top_up["payment_id"], 0, top_up["created_at"], status=409,
            code="insufficient_funds")


def test_statements_show_money_movements_once(world):
    hold = expect(world.ann.write("/authorizations", {"to_handle": "ben", "amount": 900}),
                  201).json()
    released = expect(world.ann.write("/authorizations", {"to_handle": "cat", "amount": 50}),
                      201).json()
    frozen = statement(world.ann)
    assert frozen["entries"] == []
    capture = expect(world.ben.write(f"/authorizations/{hold['authorization_id']}/capture",
                                     {"amount": 400, "final": False}), 201).json()
    expect(world.ann.post(f"/authorizations/{released['authorization_id']}/void"), 200)
    body = statement(world.ann)
    [entry] = body["entries"]
    assert entry["payment"]["payment_id"] == capture["payment_id"]
    assert entry["payment"]["authorization_id"] == hold["authorization_id"]
    assert entry["delta"] == -400 and body["closing_balance"] == 9600
    assert statement(world.ann, snapshot=frozen["snapshot"])["entries"] == []
    expect(world.ben.write(f"/payments/{capture['payment_id']}/corrections", {
        "expected_revision": 1, "amount": 1, "effective_at": capture["created_at"],
        "reason": "no"}), 403, "forbidden")
    expect(world.ann.write(f"/payments/{capture['payment_id']}/corrections", {
        "expected_revision": 1, "amount": 1, "effective_at": capture["created_at"],
        "reason": "no"}), 422, "linked_payment_immutable")
