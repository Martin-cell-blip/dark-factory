"""Item 13: statements with corrections."""
import seed
from timefx import ago, at, correct, pay, seeded_payment, signed_in, statement


def test_entries_carry_the_selected_revision(world):
    payment = pay(world.ann, "ben", 300, note="lunch")
    fix = correct(world.ann, payment["payment_id"], 120, ago(seconds=1)).json()
    [entry] = statement(world.ben)["entries"]
    assert entry["revision"] == 2 and entry["delta"] == 120
    assert entry["effective_at"] == fix["effective_at"] and entry["recorded_at"] == fix["recorded_at"]
    assert entry["payment"] == {**payment, "amount": 120}


def test_zero_amount_revision_stays_an_entry(world):
    payment = pay(world.ann, "ben", 300)
    correct(world.ann, payment["payment_id"], 0, ago(seconds=1))
    body = statement(world.ann)
    [entry] = body["entries"]
    assert entry["delta"] == 0 and entry["payment"]["amount"] == 0
    assert body["opening_balance"] == body["closing_balance"] == 10000


def test_no_correction_is_counted_beside_what_it_replaces(world):
    payment = pay(world.ann, "ben", 300)
    for revision, amount in ((1, 200), (2, 500), (3, 50)):
        correct(world.ann, payment["payment_id"], amount, ago(seconds=1),
                expected_revision=revision)
    body = statement(world.ann)
    assert len(body["entries"]) == 1 and body["entries"][0]["delta"] == -50
    assert body["closing_balance"] == 9950 == world.ann.balance()


def test_a_correction_moves_a_payment_between_windows(reset):
    old = ago(days=3)
    reset(seed.fixture(payments=[seeded_payment("p_1", "ann", "ben", 400, old)]))
    [ann] = signed_in("ann")
    first_day = {"from_": at(old, hours=-1), "to": at(old, hours=1)}
    assert [e["payment"]["payment_id"] for e in statement(ann, **first_day)["entries"]] == ["p_1"]
    correct(ann, "p_1", 400, ago(hours=1))
    moved = statement(ann, **first_day)
    assert moved["entries"] == [] and moved["opening_balance"] == moved["closing_balance"] == 10400
    later = statement(ann, from_=ago(hours=2))
    assert [e["payment"]["payment_id"] for e in later["entries"]] == ["p_1"]


def test_without_corrections_the_statement_is_the_original(world):
    first = pay(world.ann, "ben", 300)
    second = pay(world.ben, "ann", 50)
    body = statement(world.ann)
    assert [e["payment"] for e in body["entries"]] == [first, second]
    assert [e["revision"] for e in body["entries"]] == [1, 1]
    assert [e["effective_at"] for e in body["entries"]] == [first["created_at"], second["created_at"]]
