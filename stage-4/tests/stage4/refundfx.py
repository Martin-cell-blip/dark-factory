"""Helpers for stage-4 checks: refunds, correction batches and settlements."""
from client import expect
from timefx import ago


def refund(client, payment, amount, status=201, code=None, key=None):
    return expect(client.write(f"/payments/{payment['payment_id']}/refunds", {"amount": amount},
                               key=key), status, code)


def item(payment, amount, effective_at=None, expected_revision=1, reason="batch fix"):
    return {"payment_id": payment["payment_id"], "expected_revision": expected_revision,
            "amount": amount, "effective_at": effective_at or ago(seconds=2), "reason": reason}


def batch(client, items, status=201, code=None, key=None):
    return expect(client.write("/correction-batches", {"corrections": items}, key=key),
                  status, code)


def settle(operator, *transfers):
    """A settlement of (from, to, amount) transfers; returns its response."""
    body = {"transfers": [{"from_handle": f, "to_handle": t, "amount": a} for f, t, a in transfers]}
    return expect(operator.write("/settlements", body), 201).json()


def revisions(client, payment_id):
    return expect(client.get(f"/payments/{payment_id}/revisions"), 200).json()["revisions"]
