"""Item 12: exports from stages 1-3 import unchanged; stage-4 exports round-trip."""
import seed
from client import Client, expect, new_key, request
from refundfx import batch, item, refund, revisions
from sources import stage1_export, stage2_export
from timefx import correct, pay, signed_in, statement
from upgrade import stage3_export


def _import(document):
    expect(request("POST", "/_test/import", document, timeout=15), 204)


def _fresh(reset):
    reset(seed.fixture(users=[seed.user("zed", 1)]))


def test_a_stage_one_export(reset):
    source = stage1_export()
    _fresh(reset)
    _import(source["export"])
    ann, ben = Client(source["tokens"]["ann"]), Client(source["tokens"]["ben"])
    members = source["settlement"]["payments"]
    for member in members:
        assert revisions(ben, member["payment_id"])[0]["correction_batch_id"] is None
    batch(ann, [item(m, m["amount"], m["created_at"]) for m in members])
    back = refund(ben, source["payment"], 250).json()
    assert back["refund_of"] == source["payment"]["payment_id"] and ann.balance() == 9000


def test_a_stage_two_export(reset):
    source = stage2_export()
    _fresh(reset)
    _import(source["export"])
    ann, ben = Client(source["tokens"]["ann"]), Client(source["tokens"]["ben"])
    refund(ben, source["capture"], 100)
    correct(ann, source["capture"]["payment_id"], 1, source["capture"]["created_at"],
            status=422, code="linked_payment_immutable")
    [open_hold] = [a for a in expect(ann.get("/authorizations"), 200).json()["authorizations"]
                   if a["status"] == "open"]
    assert open_hold["closed_at"] is None and ann.balance() == 9400


def test_a_stage_three_export(reset):
    source = stage3_export()
    _fresh(reset)
    _import(source["export"])
    ann, ben = Client(source["tokens"]["ann"]), Client(source["tokens"]["ben"])
    frozen = source["snapshot"]
    again = statement(ben, snapshot=frozen["snapshot"], limit=1)
    assert again["entries"] == frozen["entries"], "snapshot tokens keep paging"
    history = revisions(ann, source["payment"]["payment_id"])
    assert history[1]["reason"] == "stage 3 fix" and history[1]["correction_batch_id"] is None
    replay = expect(ann.post(f"/payments/{source['payment']['payment_id']}/corrections",
                             source["fix_body"], key="s3-fix"), 200).json()
    assert replay == source["fix"], "stored responses replay exactly as stored"
    members = source["settlement"]["payments"]
    assert {p["settlement_id"] for p in members} == {source["settlement"]["settlement_id"]}
    batch(ann, [item(m, m["amount"], m["created_at"]) for m in members])
    refund(ben, source["payment"], 800)
    refund(ben, source["payment"], 1, status=422, code="refund_exceeds_payment")


def test_a_stage_four_round_trip(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann, ben = signed_in("ann", "ben")
    paid = pay(ann, "ben", 1000)
    refund_key, batch_key = new_key(), new_key()
    back = refund(ben, paid, 200, key=refund_key).json()
    fix = [item(paid, 900)]
    batched = batch(ann, fix, key=batch_key).json()
    document = expect(request("GET", "/_test/export"), 200).json()
    _fresh(reset)
    _import(document)
    assert refund(ben, paid, 200, status=200, key=refund_key).json() == back
    assert batch(ann, fix, status=200, key=batch_key).json() == batched
    assert revisions(ben, paid["payment_id"])[1] == batched["revisions"][0]
    refund(ben, paid, 701, status=422, code="refund_exceeds_payment")
    refund(ben, paid, 700)
