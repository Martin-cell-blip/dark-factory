"""Lived-in states on this team's released stage-1 and stage-2 services, read from
POCKETFUL_STAGE1_URL and POCKETFUL_STAGE2_URL. Item 17 exports them from the real services
and imports them here unchanged. Without the variable a check fails; it never skips."""
import os

import seed
from client import expect, request


def _base(name: str) -> str:
    base = os.environ.get(name)
    assert base, (f"set {name} to a running service built from the frozen "
                  f"{'stage-1' if '1' in name else 'stage-2'}/ folder (RUN.md)")
    return base


def _call(base, method, path, body=None, token=None, key=None):
    kwargs = {} if body is None else {"json_body": body}
    return request(method, path, token=token, key=key, base=base, **kwargs)


def _tokens(base, *handles):
    return {h: expect(_call(base, "POST", "/auth/login", {"email": f"{h}@pocket.test",
                                                          "password": seed.PASSWORD}),
                      200).json()["token"] for h in handles}


def stage1_export() -> dict:
    base = _base("POCKETFUL_STAGE1_URL")
    expect(_call(base, "POST", "/_test/reset", seed.fixture(settlement_operator_ids=["u_ann"])), 204)
    tokens = _tokens(base, "ann", "ben")
    paid = expect(_call(base, "POST", "/payments", {"to_handle": "ben", "amount": 1250},
                        tokens["ann"], "s1-pay"), 201).json()
    settled = expect(_call(base, "POST", "/settlements", {"transfers": [
        {"from_handle": "ben", "to_handle": "cat", "amount": 40}]}, tokens["ann"], "s1-set"),
        201).json()
    return {"export": expect(_call(base, "GET", "/_test/export"), 200).json(), "tokens": tokens,
            "payment": paid, "settlement": settled}


def stage2_export() -> dict:
    base = _base("POCKETFUL_STAGE2_URL")
    expect(_call(base, "POST", "/_test/reset", seed.fixture()), 204)
    tokens = _tokens(base, "ann", "ben")
    open_hold = expect(_call(base, "POST", "/authorizations", {"to_handle": "ben", "amount": 2000},
                             tokens["ann"], "s2-open"), 201).json()
    captured = expect(_call(base, "POST", "/authorizations", {"to_handle": "ben", "amount": 900},
                            tokens["ann"], "s2-cap"), 201).json()
    capture = expect(_call(base, "POST", f"/authorizations/{captured['authorization_id']}/capture",
                           {"amount": 600}, tokens["ben"], "s2-capture"), 201).json()
    paid = expect(_call(base, "POST", "/payments", {"to_handle": "ben", "amount": 100},
                        tokens["ann"], "s2-pay"), 201).json()
    return {"export": expect(_call(base, "GET", "/_test/export"), 200).json(), "tokens": tokens,
            "open_hold": open_hold, "captured": captured, "capture": capture, "payment": paid}
