"""Item 11: GET /payments/{payment_id}/revisions."""
from client import expect, request
from timefx import ago, correct, pay


def test_revisions_in_order_for_both_parties(world):
    payment = pay(world.ann, "ben", 300, visibility="public")
    second = correct(world.ann, payment["payment_id"], 200, ago(minutes=5), reason="first fix").json()
    third = correct(world.ann, payment["payment_id"], 0, ago(minutes=1), expected_revision=2,
                    reason="reversed").json()
    for client in (world.ann, world.ben):
        body = expect(client.get(f"/payments/{payment['payment_id']}/revisions"), 200).json()
        assert list(body) == ["revisions"]
        revisions = body["revisions"]
        assert [r["revision"] for r in revisions] == [1, 2, 3]
        assert revisions[0]["reason"] == "" and revisions[0]["amount"] == 300
        assert revisions[1] == second and revisions[2] == third


def test_third_parties_and_unknown(world):
    payment = pay(world.ann, "ben", 300, visibility="public")
    path = f"/payments/{payment['payment_id']}/revisions"
    expect(world.cat.get(path), 404, "not_found")
    expect(world.ann.get("/payments/p_missing/revisions"), 404, "not_found")
    expect(request("GET", path), 401, "unauthenticated")
