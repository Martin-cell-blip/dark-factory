"""Item 16: settlement history."""
import seed
from client import expect, new_key
from timefx import ago, signed_in


def test_settlement_members_keep_receipts_and_are_immutable(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann, ben, cat = signed_in("ann", "ben", "cat")
    key = new_key()
    body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 100},
                          {"from_handle": "cat", "to_handle": "ben", "amount": 30,
                           "visibility": "private"}]}
    settled = expect(ann.post("/settlements", body, key=key), 201).json()
    public, private = settled["payments"]
    for member in (public, private):
        [revision] = expect(ben.get(f"/payments/{member['payment_id']}/revisions"),
                            200).json()["revisions"]
        assert revision["effective_at"] == revision["recorded_at"] == settled["committed_at"]
        assert revision["amount"] == member["amount"]
    correction = {"expected_revision": 1, "amount": 50, "effective_at": ago(seconds=1),
                  "reason": "change"}
    expect(ben.write(f"/payments/{public['payment_id']}/corrections", correction),
           422, "linked_payment_immutable")
    expect(cat.write(f"/payments/{private['payment_id']}/corrections", correction),
           422, "linked_payment_immutable")
    assert expect(ann.post("/settlements", body, key=key), 200).json() == settled
    ann_feed = [p["payment_id"] for p in expect(ann.get("/activity"), 200).json()["payments"]]
    assert public["payment_id"] in ann_feed and private["payment_id"] not in ann_feed
    expect(ann.get(f"/payments/{public['payment_id']}/revisions"), 404, "not_found")
    assert ben.balance() == 2430 and cat.balance() == 570
