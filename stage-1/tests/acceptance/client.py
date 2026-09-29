"""A small stdlib HTTP client for black-box checks against POCKETFUL_URL."""
import http.client
import json
import os
import uuid
from urllib.parse import urlsplit

BASE_URL = os.environ.get("POCKETFUL_URL", "http://localhost:8080")
_NO_BODY = object()


class Response:
    def __init__(self, status: int, headers: dict, body: bytes):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body.decode("utf-8"))

    def __repr__(self) -> str:
        return f"<{self.status} {self.body[:300]!r}>"


def new_key() -> str:
    return uuid.uuid4().hex


def request(method: str, path: str, json_body=_NO_BODY, *, raw: bytes | None = None,
            token: str | None = None, key: str | None = None, headers: dict | None = None,
            timeout: float = 30) -> Response:
    url = urlsplit(BASE_URL)
    conn = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=timeout)
    sent = dict(headers or {})
    body = raw
    if json_body is not _NO_BODY:
        body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    if body is not None:
        sent.setdefault("Content-Type", "application/json; charset=utf-8")
    if token is not None:
        sent["Authorization"] = f"Bearer {token}"
    if key is not None:
        sent["Idempotency-Key"] = key
    try:
        conn.request(method, path, body=body, headers=sent)
        resp = conn.getresponse()
        return Response(resp.status, {k.lower(): v for k, v in resp.getheaders()}, resp.read())
    finally:
        conn.close()


class Client:
    """One signed-in user."""

    def __init__(self, token: str, user_id: str = "", handle: str = ""):
        self.token = token
        self.user_id = user_id
        self.handle = handle

    def get(self, path: str, **kw) -> Response:
        return request("GET", path, token=self.token, **kw)

    def post(self, path: str, json_body=_NO_BODY, **kw) -> Response:
        return request("POST", path, json_body, token=self.token, **kw)

    def write(self, path: str, json_body=_NO_BODY, key: str | None = None, **kw) -> Response:
        """An idempotent write with a fresh key unless one is given."""
        return self.post(path, json_body, key=key or new_key(), **kw)

    def balance(self) -> int:
        resp = self.get("/me")
        assert resp.status == 200, resp
        return resp.json()["balance"]


def login(email: str, password: str) -> Client:
    resp = request("POST", "/auth/login", {"email": email, "password": password})
    assert resp.status == 200, resp
    body = resp.json()
    me = request("GET", "/me", token=body["token"]).json()
    return Client(body["token"], body["user_id"], me["handle"])


def expect(resp: Response, status: int, code: str | None = None) -> Response:
    assert resp.status == status, f"expected {status}, got {resp!r}"
    if code is not None:
        assert resp.json()["error"]["code"] == code, resp
    if status >= 400:
        error = resp.json()["error"]
        assert isinstance(error["code"], str) and isinstance(error["message"], str)
    return resp


def balances_sum(clients) -> int:
    return sum(c.balance() for c in clients)
