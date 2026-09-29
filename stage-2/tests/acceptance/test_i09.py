"""Item 9: every other endpoint needs a bearer token."""
import pytest

from client import expect, request

PROTECTED = [
    ("GET", "/me", None),
    ("POST", "/payments", {"to_handle": "ben", "amount": 1}),
    ("POST", "/requests", {"payer_handle": "ben", "amount": 1}),
    ("GET", "/requests", None),
    ("POST", "/requests/rq_x/pay", {}),
    ("POST", "/requests/rq_x/decline", {}),
    ("POST", "/requests/rq_x/cancel", {}),
    ("POST", "/splits", {"amount": 1, "participant_handles": ["ben"]}),
    ("GET", "/activity", None),
    ("POST", "/settlements", {"transfers": []}),
]


@pytest.mark.parametrize("method,path,body", PROTECTED)
@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc",
                                    "Bearer unknown-token", "bearer", "Token abc"])
def test_missing_malformed_or_unknown_token_is_401(world, method, path, body, header):
    headers = {} if header is None else {"Authorization": header}
    kwargs = {} if body is None else {"json_body": body}
    resp = request(method, path, headers=headers, key="k", **kwargs)
    expect(resp, 401, "unauthenticated")


def test_open_endpoints_need_no_token(world):
    expect(request("GET", "/health"), 200)
    expect(request("GET", "/_test/export"), 200)
    expect(request("POST", "/auth/login", {"email": "ann@pocket.test",
                                           "password": "wrong one"}), 401)
