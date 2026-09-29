"""Item 17: exports from stages 1 and 2 import unchanged; stage-3 exports round-trip."""
import seed
from client import Client, expect, new_key, request
from sources import stage1_export, stage2_export
from timefx import ago, ahead, correct, me_at, pay, signed_in, statement


def _import(document):
    expect(request("POST", "/_test/import", document, timeout=15), 204)


def _revisions(client, payment_id):
    return expect(client.get(f"/payments/{payment_id}/revisions"), 200).json()["revisions"]


def test_a_stage_one_export(reset):
    source = stage1_export()
    reset(seed.fixture(users=[seed.user("zed", 1)]))
    _import(source["export"])
    ann, ben = Client(source["tokens"]["ann"]), Client(source["tokens"]["ben"])
    paid = source["payment"]
    assert _revisions(ann, paid["payment_id"])[0]["effective_at"] == paid["created_at"]
    body = statement(ann)
    assert body["opening_balance"] == 10000 and body["closing_balance"] == 8750
    assert expect(ann.post("/payments", {"to_handle": "ben", "amount": 1250}, key="s1-pay"),
                  200).json() == paid
    member = source["settlement"]["payments"][0]
    assert _revisions(ben, member["payment_id"])[0]["recorded_at"] == \
        source["settlement"]["committed_at"]
    correct(ben, member["payment_id"], 1, ago(seconds=1), status=422,
            code="linked_payment_immutable")
    correct(ann, paid["payment_id"], 1000, paid["created_at"])
    assert ann.balance() == 9000 and me_at(ann, as_of=ago(days=1))["balance"] == 10000


def test_a_stage_two_export(reset):
    source = stage2_export()
    reset(seed.fixture(users=[seed.user("zed", 1)]))
    _import(source["export"])
    ann, ben = Client(source["tokens"]["ann"]), Client(source["tokens"]["ben"])
    holds = {a["authorization_id"]: a for a in
             expect(ann.get("/authorizations"), 200).json()["authorizations"]}
    assert holds[source["open_hold"]["authorization_id"]]["closed_at"] is None
    assert holds[source["captured"]["authorization_id"]]["closed_at"] == \
        source["capture"]["created_at"]
    voided = holds[source["voided"]["authorization_id"]]
    assert voided["status"] == "voided" and voided["closed_at"] is not None, (
        "a stage-2 void time was not kept: it closes at import time (S3-D8)")
    assert me_at(ann, as_of=source["voided"]["created_at"])["held"] == 2000, (
        "an imported void without its time holds nothing historically")
    # A minute ahead: after every imported event whatever the clocks, before the hold expires.
    now = me_at(ann, as_of=ahead(minutes=1))
    assert (now["total"], now["held"], now["available"]) == (9300, 2000, 7300)
    before_capture = me_at(ann, as_of=source["captured"]["created_at"])
    assert (before_capture["total"], before_capture["held"]) == (10000, 2900)
    capture = source["capture"]
    correct(ann, capture["payment_id"], 1, ago(seconds=1), status=422,
            code="linked_payment_immutable")
    entries = statement(ann)["entries"]
    assert [e["payment"]["payment_id"] for e in entries] == [capture["payment_id"],
                                                            source["payment"]["payment_id"]]
    assert entries[0]["payment"]["authorization_id"] == source["captured"]["authorization_id"]
    correct(ann, source["payment"]["payment_id"], 50, source["payment"]["created_at"])
    assert ben.balance() == 3150


def test_a_stage_three_round_trip(reset):
    reset(seed.fixture())
    ann, ben = signed_in("ann", "ben")
    payment = pay(ann, "ben", 300)
    key = new_key()
    body = {"expected_revision": 1, "amount": 120, "effective_at": ago(hours=1), "reason": "fix"}
    fix = expect(ann.post(f"/payments/{payment['payment_id']}/corrections", body, key=key),
                 201).json()
    frozen = statement(ann, limit=1)
    document = expect(request("GET", "/_test/export"), 200).json()
    reset(seed.fixture(users=[seed.user("zed", 1)]))
    _import(document)
    assert _revisions(ben, payment["payment_id"])[1] == fix
    assert expect(ann.post(f"/payments/{payment['payment_id']}/corrections", body, key=key),
                  200).json() == fix
    again = statement(ann, snapshot=frozen["snapshot"], limit=1)
    assert again["entries"] == frozen["entries"]
    assert ann.balance() == 9880 and me_at(ann, as_of=ago(days=1))["balance"] == 10000
    correct(ann, payment["payment_id"], 100, ago(minutes=1), expected_revision=2)
