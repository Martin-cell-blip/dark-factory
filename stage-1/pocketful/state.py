"""The whole service state, and the only code that moves money.

A State is built off to the side (from a reset fixture or an export) and swapped in whole,
so reset and import are atomic replacements. Callers hold the service lock while they use it.
"""
import copy
import secrets
from concurrent.futures import ThreadPoolExecutor

from . import fields
from .clock import Clock, parse_time
from .errors import ApiError, insufficient_funds, validation
from .passwords import hash_password, is_hash

MAX_BALANCE = 2 ** 53
REQUEST_STATUSES = ("pending", "paid", "declined", "cancelled")
TRACK = "pocketful"
FORMAT_VERSION = 1


def _require(condition, message: str) -> None:
    if not condition:
        raise validation(message)


def _balance(value) -> int:
    _require(not isinstance(value, bool) and isinstance(value, (int, float)),
             "balance must be a number")
    _require(float(value).is_integer() if isinstance(value, float) else True,
             "balance must be an integer")
    value = int(value)
    _require(value >= 0, "balance must not be negative")
    _require(value <= MAX_BALANCE, "balance is out of range")
    return value


def _note(value) -> str:
    _require(isinstance(value, str) and len(value) <= fields.MAX_NOTE, "invalid note")
    return value


def _optional_id(record: dict, name: str):
    value = record.get(name)
    _require(value is None or fields.is_id(value), f"invalid {name}")
    return value


def _list(container: dict, name: str, required: bool) -> list:
    if name not in container and not required:
        return []
    value = container.get(name)
    _require(isinstance(value, list), f"{name} must be an array")
    _require(all(isinstance(item, dict) for item in value), f"{name} must hold objects")
    return value


class State:
    def __init__(self, currency: str, minor_units: int) -> None:
        self.currency = currency
        self.minor_units = minor_units
        self.users: dict[str, dict] = {}
        self.user_ids_by_handle: dict[str, str] = {}
        self.user_ids_by_email: dict[str, str] = {}
        self.tokens: dict[str, str] = {}
        self.payments: list[dict] = []
        self.payments_by_id: dict[str, dict] = {}
        self.requests: dict[str, dict] = {}
        self.splits: dict[str, dict] = {}
        self.settlements: dict[str, dict] = {}
        self.operator_ids: list[str] = []
        self.idempotency: dict[tuple, tuple[str, dict]] = {}
        self.clock = Clock()

    # ---- identities -------------------------------------------------------------------

    def new_id(self, prefix: str, taken) -> str:
        while True:
            candidate = f"{prefix}_{secrets.token_hex(8)}"
            if candidate not in taken:
                return candidate

    def issue_token(self, user_id: str) -> str:
        token = secrets.token_urlsafe(32)
        self.tokens[token] = user_id
        return token

    def add_user(self, user_id, email, password_hash, display_name, handle, balance) -> dict:
        _require(fields.is_id(user_id) and user_id not in self.users, "invalid or duplicate user id")
        _require(fields.is_email(email), "invalid email")
        _require(fields.email_key(email) not in self.user_ids_by_email, "duplicate email")
        _require(fields.is_handle(handle), "invalid handle")
        _require(handle not in self.user_ids_by_handle, "duplicate handle")
        _require(isinstance(display_name, str), "display_name must be a string")
        user = {"id": user_id, "email": email, "password_hash": password_hash,
                "display_name": display_name, "handle": handle, "balance": balance}
        self.users[user_id] = user
        self.user_ids_by_handle[handle] = user_id
        self.user_ids_by_email[fields.email_key(email)] = user_id
        return user

    def user_by_handle(self, handle):
        user_id = self.user_ids_by_handle.get(handle) if isinstance(handle, str) else None
        return self.users.get(user_id) if user_id else None

    def is_operator(self, user_id: str) -> bool:
        return user_id in self.operator_ids

    # ---- money --------------------------------------------------------------------------

    def commit_payments(self, transfers: list[dict], created_at: str,
                        settlement_id=None) -> list[dict]:
        """Move money for a batch of transfers as one step, or raise and change nothing.

        Each transfer is {from, to, amount, note, visibility, request_id}. The batch commits
        only when every wallet ends nonnegative; this is the one guard on every money path.
        """
        deltas: dict[str, int] = {}
        for t in transfers:
            _require(t["from"]["id"] != t["to"]["id"], "a wallet cannot pay itself")
            deltas[t["from"]["id"]] = deltas.get(t["from"]["id"], 0) - t["amount"]
            deltas[t["to"]["id"]] = deltas.get(t["to"]["id"], 0) + t["amount"]
        for user_id, delta in deltas.items():
            after = self.users[user_id]["balance"] + delta
            if after < 0:
                raise insufficient_funds()
            if after > MAX_BALANCE:
                raise validation("the payment would take a balance out of range")
        for user_id, delta in deltas.items():
            self.users[user_id]["balance"] += delta
        payments = []
        for t in transfers:
            payment = {
                "payment_id": self.new_id("p", self.payments_by_id),
                "from_user_id": t["from"]["id"], "from_handle": t["from"]["handle"],
                "to_user_id": t["to"]["id"], "to_handle": t["to"]["handle"],
                "amount": t["amount"], "currency": self.currency, "note": t["note"],
                "visibility": t["visibility"], "request_id": t.get("request_id"),
                "settlement_id": settlement_id, "created_at": created_at,
            }
            self._add_payment(payment)
            payments.append(payment)
        return payments

    def _add_payment(self, payment: dict) -> None:
        _require(payment["payment_id"] not in self.payments_by_id, "duplicate payment id")
        self.payments.append(payment)
        self.payments_by_id[payment["payment_id"]] = payment

    def new_request(self, requester: dict, payer: dict, amount: int, note: str,
                    created_at: str) -> dict:
        request = {
            "request_id": self.new_id("rq", self.requests),
            "requester_id": requester["id"], "requester_handle": requester["handle"],
            "payer_id": payer["id"], "payer_handle": payer["handle"],
            "amount": amount, "currency": self.currency, "note": note,
            "status": "pending", "payment_id": None, "created_at": created_at,
        }
        self.requests[request["request_id"]] = request
        return request

    # ---- building a state ---------------------------------------------------------------

    @classmethod
    def empty(cls) -> "State":
        return cls("EUR", 2)

    @classmethod
    def _with_currency(cls, source: dict) -> "State":
        currency = source.get("currency")
        minor_units = source.get("minor_units")
        _require(isinstance(currency, str) and currency != "", "currency is required")
        _require(not isinstance(minor_units, bool) and minor_units in (0, 2, 3),
                 "minor_units must be 0, 2 or 3")
        return cls(currency, int(minor_units))

    def _operators(self, source: dict) -> None:
        operators = source.get("settlement_operator_ids", [])
        _require(isinstance(operators, list) and all(fields.is_id(o) for o in operators),
                 "settlement_operator_ids must be an array of user ids")
        self.operator_ids = list(dict.fromkeys(operators))

    def _order_by_time(self) -> None:
        """Keep creation order equal to created_at order after loading records."""
        self.payments.sort(key=lambda p: parse_time(p["created_at"]))
        ordered = sorted(self.requests.values(), key=lambda r: parse_time(r["created_at"]))
        self.requests = {r["request_id"]: r for r in ordered}

    def _stamp(self, record: dict, name: str, stamps: list) -> None:
        if name in record:
            _require(parse_time(record[name]) is not None, f"{name} must be RFC 3339 with an offset")
            self.clock.observe(record[name])
        stamps.append(record.get(name))

    @classmethod
    def from_fixture(cls, fixture: dict) -> "State":
        """Section 4 fixture. Balances are already net of the seeded payments."""
        try:
            return cls._from_fixture(fixture)
        except ApiError as error:
            raise validation(f"invalid fixture: {error.message}") from None

    @classmethod
    def _from_fixture(cls, fixture: dict) -> "State":
        state = cls._with_currency(fixture)
        users = _list(fixture, "users", required=True)
        for u in users:
            _require(isinstance(u.get("password"), str), "password must be a string")
        with ThreadPoolExecutor(max_workers=4) as pool:
            hashes = list(pool.map(lambda u: hash_password(u["password"]), users))
        for u, password_hash in zip(users, hashes):
            state.add_user(u.get("id"), u.get("email"), password_hash, u.get("display_name"),
                           u.get("handle"), _balance(u.get("balance")))
        payments = _list(fixture, "payments", required=False)
        requests = _list(fixture, "requests", required=False)
        stamps: list = []
        for record in payments + requests:
            state._stamp(record, "created_at", stamps)
        stamps = [s if s is not None else state.clock.now() for s in stamps]
        for record, stamp in zip(payments, stamps):
            state._add_payment(state._seeded_payment(record, stamp))
        for record, stamp in zip(requests, stamps[len(payments):]):
            request = state._seeded_request(record, stamp)
            _require(request["request_id"] not in state.requests, "duplicate request id")
            state.requests[request["request_id"]] = request
        state._operators(fixture)
        state._order_by_time()
        return state

    def _party(self, user_id) -> dict:
        _require(isinstance(user_id, str) and user_id in self.users, "unknown user id")
        return self.users[user_id]

    def _seeded_payment(self, record: dict, created_at: str) -> dict:
        _require(fields.is_id(record.get("id")), "payment id is required")
        sender = self._party(record.get("from_user_id"))
        receiver = self._party(record.get("to_user_id"))
        _require(sender is not receiver, "a payment needs two different users")
        visibility = record.get("visibility", "public")
        _require(visibility in fields.VISIBILITIES, "invalid visibility")
        return {
            "payment_id": record["id"],
            "from_user_id": sender["id"], "from_handle": sender["handle"],
            "to_user_id": receiver["id"], "to_handle": receiver["handle"],
            "amount": fields.amount_value(record.get("amount")), "currency": self.currency,
            "note": _note(record.get("note", "")), "visibility": visibility,
            "request_id": _optional_id(record, "request_id"),
            "settlement_id": _optional_id(record, "settlement_id"),
            "created_at": created_at,
        }

    def _seeded_request(self, record: dict, created_at: str) -> dict:
        _require(fields.is_id(record.get("id")), "request id is required")
        requester = self._party(record.get("requester_id"))
        payer = self._party(record.get("payer_id"))
        _require(requester is not payer, "a request needs two different users")
        status = record.get("status", "pending")
        _require(status in REQUEST_STATUSES, "invalid request status")
        return {
            "request_id": record["id"],
            "requester_id": requester["id"], "requester_handle": requester["handle"],
            "payer_id": payer["id"], "payer_handle": payer["handle"],
            "amount": fields.amount_value(record.get("amount")), "currency": self.currency,
            "note": _note(record.get("note", "")), "status": status,
            "payment_id": _optional_id(record, "payment_id"), "created_at": created_at,
        }

    # ---- export and import (section 10) -------------------------------------------------

    def export(self) -> dict:
        """A deep, self-contained copy; later writes cannot reach it."""
        return copy.deepcopy({
            "track": TRACK,
            "format_version": FORMAT_VERSION,
            "state": {
                "currency": self.currency,
                "minor_units": self.minor_units,
                "clock": None if self.clock.last is None else self.clock.last.isoformat(),
                "users": list(self.users.values()),
                "tokens": [{"token": t, "user_id": u} for t, u in self.tokens.items()],
                "payments": self.payments,
                "requests": list(self.requests.values()),
                "splits": list(self.splits.values()),
                "settlements": list(self.settlements.values()),
                "settlement_operator_ids": self.operator_ids,
                "idempotency": [
                    {"user_id": slot[0], "method": slot[1], "path": slot[2], "key": slot[3],
                     "body": body, "response": response}
                    for slot, (body, response) in self.idempotency.items()],
            },
        })

    @classmethod
    def from_export(cls, document: dict) -> "State":
        """Rebuild exactly what was exported: ids, timestamps, hashes, tokens and receipts."""
        _require(document.get("track") == TRACK, "track must be pocketful")
        version = document.get("format_version")
        _require(not isinstance(version, bool) and version == FORMAT_VERSION,
                 "format_version must be 1")
        source = document.get("state")
        _require(isinstance(source, dict), "state must be an object")
        try:
            return cls._from_export(source)
        except (KeyError, TypeError, AttributeError):
            raise validation("invalid state") from None

    @classmethod
    def _from_export(cls, source: dict) -> "State":
        state = cls._with_currency(source)
        for u in _list(source, "users", required=True):
            _require(is_hash(u["password_hash"]), "invalid password hash")
            state.add_user(u["id"], u["email"], u["password_hash"], u["display_name"],
                           u["handle"], _balance(u["balance"]))
        for t in _list(source, "tokens", required=True):
            _require(isinstance(t["token"], str) and t["token"], "invalid token")
            state.tokens[t["token"]] = state._party(t["user_id"])["id"]
        for p in _list(source, "payments", required=True):
            payment = state._seeded_payment(
                {"id": p["payment_id"], **p}, state._exported_time(p["created_at"]))
            _require(payment["from_handle"] == p["from_handle"]
                     and payment["to_handle"] == p["to_handle"], "payment handles do not match")
            state._add_payment(payment)
        for r in _list(source, "requests", required=True):
            request = state._seeded_request(
                {"id": r["request_id"], **r}, state._exported_time(r["created_at"]))
            _require(request["request_id"] not in state.requests, "duplicate request id")
            state.requests[request["request_id"]] = request
        for s in _list(source, "splits", required=True):
            _require(fields.is_id(s["split_id"]), "invalid split id")
            state.splits[s["split_id"]] = s
        for s in _list(source, "settlements", required=True):
            _require(fields.is_id(s["settlement_id"]), "invalid settlement id")
            state.settlements[s["settlement_id"]] = s
        for entry in _list(source, "idempotency", required=True):
            slot = (entry["user_id"], entry["method"], entry["path"], entry["key"])
            _require(all(isinstance(part, str) for part in slot), "invalid idempotency slot")
            _require(isinstance(entry["body"], str) and isinstance(entry["response"], dict),
                     "invalid idempotency record")
            state.idempotency[slot] = (entry["body"], entry["response"])
        state._operators(source)
        clock = source.get("clock")
        if clock is not None:
            state._exported_time(clock)
        state._order_by_time()
        return state

    def _exported_time(self, stamp) -> str:
        _require(parse_time(stamp) is not None, "timestamps must be RFC 3339 with an offset")
        self.clock.observe(stamp)
        return stamp
