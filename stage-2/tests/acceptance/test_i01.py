"""Item 1: listens on PORT; GET /health -> 200 {"status": "ok"}."""
from client import expect, request


def test_health_is_ok():
    resp = expect(request("GET", "/health"), 200)
    assert resp.json() == {"status": "ok"}


def test_health_needs_no_token():
    expect(request("GET", "/health", token="not-a-token"), 200)
