"""Item 9: correction money movement, insufficient funds and historical overdraft."""
import seed
from client import expect, new_key
from timefx import ago, correct, me_at, pay, seeded_payment, signed_in, statement


def test_increase_debits_sender_and_decrease_debits_receiver(world):
    payment = pay(world.ann, "ben", 300)
    correct(world.ann, payment["payment_id"], 500, payment["created_at"])
    assert (world.ann.balance(), world.ben.balance()) == (9500, 3000)
    correct(world.ann, payment["payment_id"], 100, payment["created_at"], expected_revision=2)
    assert (world.ann.balance(), world.ben.balance()) == (9900, 2600)
    assert world.cat.balance() == 500


def test_currently_unaffordable_debits(world):
    to_cat = pay(world.ann, "cat", 1000)
    pay(world.cat, "ben", 1400)
    correct(world.ann, to_cat["payment_id"], 100, to_cat["created_at"], status=409,
            code="insufficient_funds")
    from_cat = pay(world.cat, "ann", 50)
    correct(world.cat, from_cat["payment_id"], 200, from_cat["created_at"], status=409,
            code="insufficient_funds")
    to_ben = pay(world.ann, "ben", 500)
    expect(world.ben.write("/authorizations", {"to_handle": "cat", "amount": 4400}), 201)
    correct(world.ann, to_ben["payment_id"], 0, to_ben["created_at"], status=409,
            code="insufficient_funds")


def test_historical_overdraft(world):
    to_cat = pay(world.ann, "cat", 1000)
    pay(world.cat, "ben", 1200)
    pay(world.ben, "cat", 2000)
    before = [c.balance() for c in world.everyone]
    snapshot = statement(world.cat)
    key = new_key()
    body = {"expected_revision": 1, "amount": 100, "effective_at": to_cat["created_at"],
            "reason": "less"}
    path = f"/payments/{to_cat['payment_id']}/corrections"
    expect(world.ann.post(path, body, key=key), 409, "historical_overdraft")
    assert [c.balance() for c in world.everyone] == before
    revisions = expect(world.ann.get(f"/payments/{to_cat['payment_id']}/revisions"), 200).json()
    assert len(revisions["revisions"]) == 1
    assert statement(world.cat)["entries"] == snapshot["entries"]
    expect(world.ann.post(path, {**body, "amount": 900}, key=key), 201)


def test_moving_a_payment_earlier_can_overdraw_the_past(world):
    pay(world.ben, "cat", 2000)
    top_up = pay(world.ann, "ben", 3000)
    later = pay(world.ben, "ann", 100)
    correct(world.ben, later["payment_id"], 100, ago(days=2), status=201)
    early = pay(world.ben, "ann", 3000)
    correct(world.ben, early["payment_id"], 3000, ago(days=1), status=409,
            code="historical_overdraft")
    assert top_up["amount"] == 3000


def test_one_instant_counts_as_a_whole(reset):
    """Mid receives 100 and sends 100 at one instant; taken separately in the wrong order
    that would dip below zero, together it does not."""
    same = ago(hours=5)
    reset(seed.fixture(
        users=[seed.user("ann", 9900), seed.user("ben", 200), seed.user("mid", 50),
               seed.user("cat", 0)],
        payments=[seeded_payment("p_in", "ann", "mid", 100, same),
                  seeded_payment("p_out", "mid", "ben", 100, same),
                  seeded_payment("p_gift", "cat", "mid", 50, ago(hours=6))]))
    cat, mid = signed_in("cat", "mid")
    correct(cat, "p_gift", 0, ago(hours=6))
    assert mid.balance() == 0 and cat.balance() == 50


def test_balances_sum_to_the_seeded_total_in_every_view(world):
    first = pay(world.ann, "ben", 700)
    pay(world.ben, "cat", 300)
    correct(world.ann, first["payment_id"], 400, ago(days=1))
    for stamp in (ago(days=2), ago(hours=12), ago(seconds=1), None):
        views = [me_at(c, as_of=stamp) if stamp else me_at(c, known_at=ago(hours=1))
                 for c in world.everyone]
        assert sum(v["balance"] for v in views) == world.total
    known = first["created_at"]
    assert sum(me_at(c, known_at=known)["balance"] for c in world.everyone) == world.total
