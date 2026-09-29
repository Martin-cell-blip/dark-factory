"""Item 23 (boundary): stage 4's refund capability is absent."""
from client import expect
from timefx import pay


def test_refunds_are_absent(world):
    payment = pay(world.ann, "ben", 300)
    resp = world.ben.write(f"/payments/{payment['payment_id']}/refunds",
                           {"amount": 100, "reason": "returned"})
    assert resp.status != 201
    expect(resp, 404, "not_found")
    assert world.ben.balance() == 2800
