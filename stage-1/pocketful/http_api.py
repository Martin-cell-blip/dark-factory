"""HTTP transport: routing, bodies, headers and the JSON envelope. No business rules here."""
import re
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, unquote, urlsplit

from . import jsonio
from .errors import ApiError, malformed, not_found
from .service import Service, bearer_token

CONTENT_TYPE = "application/json; charset=utf-8"
MAX_BODY = 8 * 1024 * 1024  # decision D8
DRAIN_LIMIT = 64 * 1024 * 1024


class Request:
    def __init__(self, handler: "Handler", raw: bytes, path: str, query: dict, params: tuple):
        self._handler = handler
        self._raw = raw
        self.path = path
        self.query = query
        self.params = params

    def object(self) -> dict:
        return jsonio.parse_object(self._raw)

    def optional_object(self) -> dict:
        """Bodies that may be omitted entirely; an empty body means {}."""
        return jsonio.parse_object(self._raw) if self._raw.strip() else {}

    def token(self, service: Service) -> str:
        token = bearer_token(self._handler.headers.get("Authorization"))
        service.authenticate(token)
        return token

    @property
    def key(self):
        return self._handler.headers.get("Idempotency-Key")


def _routes(service: Service):
    def health(req):
        return 200, {"status": "ok"}

    def reset(req):
        service.reset(req.object())
        return 204, None

    def export(req):
        return 200, service.export()

    def import_(req):
        service.import_(req.object())
        return 204, None

    def signup(req):
        return 201, service.signup(req.object())

    def login(req):
        return 200, service.login(req.object())

    def me(req):
        return 200, service.me(req.token(service))

    def payments(req):
        token = req.token(service)
        return service.create_payment(token, req.key, req.path, req.object())

    def requests_create(req):
        token = req.token(service)
        return service.create_request(token, req.key, req.path, req.object())

    def requests_list(req):
        return 200, service.list_requests(req.token(service), req.query)

    def request_pay(req):
        token = req.token(service)
        return service.pay_request(token, req.key, req.path, req.params[0],
                                   req.optional_object())

    def request_decline(req):
        token = req.token(service)
        req.optional_object()
        return 200, service.decline_request(token, req.params[0])

    def request_cancel(req):
        token = req.token(service)
        req.optional_object()
        return 200, service.cancel_request(token, req.params[0])

    def splits(req):
        token = req.token(service)
        return service.create_split(token, req.key, req.path, req.object())

    def activity(req):
        return 200, service.activity(req.token(service), req.query)

    def settlements(req):
        token = req.token(service)
        return service.create_settlement(token, req.key, req.path, req.object())

    table = [
        ("GET", "/health", health),
        ("POST", "/_test/reset", reset),
        ("GET", "/_test/export", export),
        ("POST", "/_test/import", import_),
        ("POST", "/auth/signup", signup),
        ("POST", "/auth/login", login),
        ("GET", "/me", me),
        ("POST", "/payments", payments),
        ("POST", "/requests", requests_create),
        ("GET", "/requests", requests_list),
        ("POST", "/requests/([^/]+)/pay", request_pay),
        ("POST", "/requests/([^/]+)/decline", request_decline),
        ("POST", "/requests/([^/]+)/cancel", request_cancel),
        ("POST", "/splits", splits),
        ("GET", "/activity", activity),
        ("POST", "/settlements", settlements),
    ]
    return [(method, re.compile(pattern), fn) for method, pattern, fn in table]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pocketful"
    sys_version = ""
    routes: list = []

    def log_message(self, format, *args):  # noqa: A002 - the stdlib signature
        pass

    def read_body(self) -> bytes:
        if self.headers.get("Transfer-Encoding", "").lower() == "chunked":
            return self._read_chunked()
        length = self.headers.get("Content-Length")
        if not length:
            return b""
        if not length.isdigit():
            self.close_connection = True
            raise malformed("Content-Length must be a number")
        if int(length) > MAX_BODY:
            self._discard(int(length))
            raise ApiError(413, "payload_too_large", f"the body is larger than {MAX_BODY} bytes")
        return self.rfile.read(int(length))

    def _discard(self, length: int) -> None:
        """Drain a moderately oversized body so the client can read the 413; drop the rest."""
        self.close_connection = True
        if length > DRAIN_LIMIT:
            return
        while length > 0:
            chunk = self.rfile.read(min(length, 65536))
            if not chunk:
                return
            length -= len(chunk)

    def _read_chunked(self) -> bytes:
        chunks, total = [], 0
        while True:
            line = self.rfile.readline(1024).split(b";")[0].strip()
            try:
                size = int(line, 16)
            except ValueError:
                self.close_connection = True
                raise malformed("bad chunked encoding") from None
            if size == 0:
                while self.rfile.readline(1024).strip():
                    pass
                return b"".join(chunks)
            total += size
            if total > MAX_BODY:
                self.close_connection = True
                raise ApiError(413, "payload_too_large", "the body is too large")
            chunks.append(self.rfile.read(size))
            self.rfile.readline(1024)

    def _send(self, status: int, body) -> None:
        payload = b"" if body is None else jsonio.dumps(body)
        self.send_response(status)
        self.send_header("Content-Type", CONTENT_TYPE)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if payload:
            self.wfile.write(payload)

    def send_error(self, code, message=None, explain=None):
        """Errors raised by the stdlib parser still use the section 5 envelope."""
        self.close_connection = True
        codes = {400: "malformed_request", 404: "not_found"}
        error = ApiError(code, codes.get(code, "http_error"), message or "request rejected")
        try:
            self._send(code, error.body())
        except OSError:
            pass

    def _dispatch(self) -> None:
        url = urlsplit(self.path)
        path = url.path
        query = {}
        for name, value in parse_qsl(url.query, keep_blank_values=True):
            query.setdefault(name, value)
        try:
            raw = self.read_body()
            fn, params, allowed = None, (), False
            for method, pattern, candidate in self.routes:
                match = pattern.fullmatch(path)
                if match:
                    allowed = True
                    if method == self.command:
                        fn, params = candidate, tuple(unquote(g) for g in match.groups())
                        break
            if fn is None:
                if allowed:
                    raise ApiError(405, "method_not_allowed", "method not allowed here")
                raise not_found("no such endpoint")
            status, body = fn(Request(self, raw, path, query, params))
        except ApiError as error:
            status, body = error.status, error.body()
        except Exception:  # a defect: still answer in the envelope, never a bare crash
            traceback.print_exc(file=sys.stderr)
            status, body = 500, ApiError(500, "internal_error", "internal error").body()
        self._send(status, body)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _dispatch


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 512


def serve(port: int) -> None:
    Handler.routes = _routes(Service())
    server = Server(("0.0.0.0", port), Handler)
    print(f"pocketful listening on 0.0.0.0:{port}", flush=True)
    server.serve_forever()
