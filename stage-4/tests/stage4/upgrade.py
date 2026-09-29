"""A lived-in state on this team's released stage-3 service (POCKETFUL_STAGE3_URL): a
settlement, a correction and a statement snapshot. Stage-1 and stage-2 sources come from
tests/stage3/sources.py. Without the variable a check fails; it never skips."""
import os

import seed
from client import expect, request


def stage3_export() -> dict:
    base = os.environ.get("POCKETFUL_STAGE3_URL")
    assert base, "set POCKETFUL_STAGE3_URL to a service built from the frozen stage-3/ (RUN.md)"

    def call(method, path, body=None, token=None, key=None):
        kwargs = {} if body is None else {"json_body": body}
        return request(method, path, token=token, key=key, base=base, **kwargs)

    expect(call("POST", "/_test/reset", seed.fixture(settlement_operator_ids=["u_ann"])), 204)
    tokens = {h: expect(call("POST", "/auth/login", {"email": f"{h}@pocket.test",
                                                     "password": seed.PASSWORD}),
                        200).json()["token"] for h in ("ann", "ben", "cat")}
    paid = expect(call("POST", "/payments", {"to_handle": "ben", "amount": 1000},
                       tokens["ann"], "s3-pay"), 201).json()
    fix_body = {"expected_revision": 1, "amount": 800, "effective_at": paid["created_at"],
                "reason": "stage 3 fix"}
    fix = expect(call("POST", f"/payments/{paid['payment_id']}/corrections", fix_body,
                      tokens["ann"], "s3-fix"), 201).json()
    settled = expect(call("POST", "/settlements", {"transfers": [
        {"from_handle": "ben", "to_handle": "cat", "amount": 100},
        {"from_handle": "cat", "to_handle": "ben", "amount": 30}]}, tokens["ann"], "s3-set"),
        201).json()
    snapshot = expect(call("GET", "/statement?limit=1", token=tokens["ben"]), 200).json()
    return {"export": expect(call("GET", "/_test/export"), 200).json(), "tokens": tokens,
            "payment": paid, "fix": fix, "fix_body": fix_body, "settlement": settled,
            "snapshot": snapshot}
