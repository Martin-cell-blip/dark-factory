"""A lived-in state on this team's released stage-1 service, read from POCKETFUL_STAGE1_URL.

Items 14 and 27 upgrade from it: they export it from the real stage-1 service and import
it here unchanged. Without POCKETFUL_STAGE1_URL they fail; they never skip (RUN.md).
"""
import os

import seed
from client import expect, request

STAGE1_URL = os.environ.get("POCKETFUL_STAGE1_URL")


def _call(method, path, body=None, token=None, key=None):
    kwargs = {} if body is None else {"json_body": body}
    return request(method, path, token=token, key=key, base=STAGE1_URL, **kwargs)


def lived_in_export() -> dict:
    """Build a stage-1 state (payments, a pending request, a settlement, a failed key) and
    return its unchanged export with what the checks need to probe it."""
    assert STAGE1_URL, ("set POCKETFUL_STAGE1_URL to a running stage-1 service built from "
                        "stage-1/ at the release commit (RUN.md)")
    expect(_call("POST", "/_test/reset", seed.fixture(settlement_operator_ids=["u_ann"])), 204)
    tokens = {}
    for handle in ("ann", "ben"):
        body = {"email": f"{handle}@pocket.test", "password": seed.PASSWORD}
        tokens[handle] = expect(_call("POST", "/auth/login", body), 200).json()["token"]
    pay_body = {"to_handle": "ben", "amount": 1250, "note": "lunch", "visibility": "private"}
    payment = expect(_call("POST", "/payments", pay_body, tokens["ann"], "stage1-pay"), 201).json()
    pending = expect(_call("POST", "/requests", {"payer_handle": "ann", "amount": 300,
                                                 "note": "tickets"}, tokens["ben"], "stage1-rq"),
                     201).json()
    settle = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 40}]}
    expect(_call("POST", "/settlements", settle, tokens["ann"], "stage1-settle"), 201)
    failed_body = {"to_handle": "cat", "amount": 999999}
    expect(_call("POST", "/payments", failed_body, tokens["ben"], "stage1-failed"), 409)
    return {
        "export": expect(_call("GET", "/_test/export"), 200).json(),
        "tokens": tokens,
        "payment": {"key": "stage1-pay", "body": pay_body, "response": payment},
        "failed": {"key": "stage1-failed", "body": failed_body},
        "pending_request_id": pending["request_id"],
        "balances": {"ann": 10000 - 1250, "ben": 2500 + 1250 - 40, "cat": 540},
    }
