"""Item 6: revision 1 and opening balances."""
from client import Client, expect, request
import seed
from timefx import ago, correct, me_at, pay, seeded_payment, signed_in, statement

STAMP = ago(hours=6)


def _revisions(client, payment_id):
    return expect(client.get(f"/payments/{payment_id}/revisions"), 200).json()["revisions"]


def test_revision_one_for_seeded_and_new_payments(reset):
    reset(seed.fixture(payments=[seeded_payment("p_given", "ann", "ben", 500, STAMP),
                                 seeded_payment("p_reset", "ben", "ann", 50)]))
    ann, ben = signed_in("ann", "ben")
    [given] = _revisions(ann, "p_given")
    assert given == {"payment_id": "p_given", "revision": 1, "amount": 500, "effective_at": STAMP,
                     "recorded_at": STAMP, "reason": ""}
    feed = {p["payment_id"]: p for p in expect(ann.get("/activity"), 200).json()["payments"]}
    [at_reset] = _revisions(ben, "p_reset")
    assert at_reset["effective_at"] == at_reset["recorded_at"] == feed["p_reset"]["created_at"]
    live = pay(ann, "cat", 7)
    [first] = _revisions(ann, live["payment_id"])
    assert first["effective_at"] == first["recorded_at"] == live["created_at"]
    assert first["amount"] == 7 and first["reason"] == ""


def test_opening_balances_never_change(reset):
    reset(seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 500, STAMP)]))
    ann, ben = signed_in("ann", "ben")
    long_ago = ago(days=400)
    assert me_at(ann, as_of=long_ago)["balance"] == 10500
    assert me_at(ben, as_of=long_ago)["balance"] == 2000
    assert statement(ann)["opening_balance"] == 10500
    correct(ann, "p_1", 100, STAMP)
    assert me_at(ann, as_of=long_ago)["balance"] == 10500
    assert me_at(ben, as_of=long_ago)["balance"] == 2000
    assert statement(ann)["opening_balance"] == 10500
    assert ann.balance() == 10400 and ben.balance() == 2100


def test_new_accounts_open_at_zero(world):
    body = expect(request("POST", "/auth/signup", {"email": "neo@pocket.test",
                                                   "password": "long enough 1",
                                                   "display_name": "Neo"}), 201).json()
    neo = Client(body["token"])
    pay(world.ann, "neo", 400)
    assert me_at(neo, as_of=ago(days=1))["balance"] == 0
    assert statement(neo)["opening_balance"] == 0
