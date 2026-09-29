"""Shared client for the auditor holdout tests (Pocketful stage 1).

Black-box HTTP tests. Base URL from POCKETFUL_URL (default http://localhost:8080).
Optional second instance for cross-instance import: POCKETFUL_URL_B (skipped if unset).
Standard library only.
"""
from __future__ import annotations

import http.client
import json
import os
import urllib.parse
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest

BASE = os.environ.get("POCKETFUL_URL", "http://localhost:8080").rstrip("/")
BASE_B = os.environ.get("POCKETFUL_URL_B", "").rstrip("/")
_ABSENT = object()


class Resp:
    def __init__(self, status, headers, raw):
        self.status = status
        self.headers = headers
        self.raw = raw

    @property
    def text(self):
        return self.raw.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.raw.decode("utf-8"))

    def __repr__(self):
        return f"<{self.status} {self.text[:300]}>"


def call(method, path, body=_ABSENT, *, token=None, key=None, raw=None,
         headers=None, base=None, timeout=15):
    u = urllib.parse.urlsplit(base or BASE)
    conn = http.client.HTTPConnection(u.hostname, u.port or 80, timeout=timeout)
    h = {"Accept": "application/json"}
    data = None
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        h["Content-Type"] = "application/json"
    elif body is not _ABSENT:
        data = json.dumps(body).encode("utf-8")
        h["Content-Type"] = "application/json"
    if token is not None:
        h["Authorization"] = f"Bearer {token}"
    if key is not None:
        h["Idempotency-Key"] = key
    if headers:
        h.update(headers)
    try:
        conn.request(method, path, body=data, headers=h)
        r = conn.getresponse()
        return Resp(r.status, {k.lower(): v for k, v in r.getheaders()}, r.read())
    finally:
        conn.close()


def new_key():
    return "k-" + uuid.uuid4().hex


def assert_error(resp, status, code):
    assert resp.status == status, f"expected {status} {code}, got {resp!r}"
    body = resp.json()
    assert isinstance(body, dict) and isinstance(body.get("error"), dict), resp
    assert body["error"].get("code") == code, f"expected code {code}, got {resp!r}"
    assert isinstance(body["error"].get("message"), str), resp


def user(handle, balance, uid=None):
    return {"id": uid or f"u_{handle}", "email": f"{handle}@example.com",
            "password": "correct horse", "display_name": handle.title(),
            "handle": handle, "balance": balance}


def fixture(users=None, currency="EUR", minor_units=2, payments=None,
            requests=None, operators=None):
    fx = {"currency": currency, "minor_units": minor_units,
          "users": users if users is not None else
          [user("ada", 10000), user("bob", 2500), user("cy", 500)],
          "payments": payments or [], "requests": requests or []}
    if operators is not None:
        fx["settlement_operator_ids"] = operators
    return fx


def reset(fx, base=None):
    r = call("POST", "/_test/reset", fx, base=base, timeout=15)
    assert r.status == 204, r
    return fx


def login(email, password="correct horse", base=None):
    r = call("POST", "/auth/login", {"email": email, "password": password}, base=base)
    assert r.status == 200, r
    return r.json()["token"]


class Client:
    def __init__(self, token, base=None):
        self.token = token
        self.base = base

    def get(self, path, **kw):
        return call("GET", path, token=self.token, base=self.base, **kw)

    def post(self, path, body=_ABSENT, **kw):
        return call("POST", path, body, token=self.token, base=self.base, **kw)

    def me(self):
        r = self.get("/me")
        assert r.status == 200, r
        return r.json()

    def balance(self):
        return self.me()["balance"]


class World:
    def __init__(self, fx, base=None):
        self.fx = fx
        self.base = base
        self.total = sum(u["balance"] for u in fx["users"])
        self.c = {u["handle"]: Client(login(u["email"], base=base), base)
                  for u in fx["users"]}

    def __getattr__(self, name):
        c = self.__dict__.get("c", {})
        if name in c:
            return c[name]
        raise AttributeError(name)

    def conserved(self):
        """The conserved quantity: every wallet non-negative and the sum equals the seed."""
        bals = {h: c.balance() for h, c in self.c.items()}
        assert all(b >= 0 for b in bals.values()), f"negative balance: {bals}"
        assert sum(bals.values()) == self.total, f"sum {sum(bals.values())} != {self.total}: {bals}"
        return bals


def make_world(fx=None, base=None):
    fx = fx or fixture()
    reset(fx, base=base)
    return World(fx, base=base)


@pytest.fixture
def world():
    return make_world()


@pytest.fixture
def opworld():
    return make_world(fixture(users=[user("ada", 10000), user("bob", 2500),
                                     user("cy", 500), user("op", 0)],
                              operators=["u_op"]))


def pay(c, to_handle, amount, key=None, **extra):
    body = {"to_handle": to_handle, "amount": amount, **extra}
    return c.post("/payments", body, key=key or new_key())


def ask(c, payer_handle, amount, key=None, **extra):
    body = {"payer_handle": payer_handle, "amount": amount, **extra}
    return c.post("/requests", body, key=key or new_key())


def settle(c, transfers, key=None):
    return c.post("/settlements", {"transfers": transfers}, key=key or new_key())


def burst(fn, n=50):
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda i: fn(i), range(n)))


def no_5xx(resps):
    bad = [r for r in resps if r.status >= 500]
    assert not bad, f"5xx responses: {bad[:3]}"
