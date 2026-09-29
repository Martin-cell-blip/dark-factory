"""Every operation of the API, each one check-and-act under the single service lock.

The lock makes a check and the change it guards one atomic step: two concurrent callers
never both pass the same balance, status or idempotency check.
"""
import threading

from . import fields
from .errors import (ApiError, forbidden, not_found, request_not_pending,
                     unauthenticated, validation)
from .jsonio import canonical
from .money import equal_split
from .passwords import hash_password, verify_password
from .state import State

MAX_KEY = 255
MAX_TRANSFERS = 32
DIRECTIONS = ("incoming", "outgoing")


def bearer_token(header) -> str:
    """The token from `Authorization: Bearer <token>`, or 401."""
    if not isinstance(header, str):
        raise unauthenticated()
    parts = header.split(" ")
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise unauthenticated()
    return parts[1]


def _paging(query: dict) -> tuple[int, int]:
    return (fields.query_int(query, "limit", 50, 1, 200),
            fields.query_int(query, "offset", 0, 0, None))


def _page(items: list, paging: tuple[int, int]) -> tuple[list, bool]:
    limit, offset = paging
    return items[offset:offset + limit], len(items) > offset + limit


def _public_user(user: dict, token: str) -> dict:
    return {"user_id": user["id"], "display_name": user["display_name"], "token": token}


class Service:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = State.empty()

    # ---- test control ------------------------------------------------------------------

    def reset(self, fixture: dict) -> None:
        state = State.from_fixture(fixture)
        with self._lock:
            self._state = state

    def export(self) -> dict:
        with self._lock:
            return self._state.export()

    def import_(self, document: dict) -> None:
        state = State.from_export(document)
        with self._lock:
            self._state = state

    # ---- authentication ----------------------------------------------------------------

    @staticmethod
    def _user(state: State, token: str) -> dict:
        user_id = state.tokens.get(token)
        if user_id is None:
            raise unauthenticated()
        return state.users[user_id]

    def authenticate(self, token: str) -> None:
        with self._lock:
            self._user(self._state, token)

    def signup(self, body: dict) -> dict:
        email = fields.required_string(body, "email")
        password = fields.required_string(body, "password")
        display_name = fields.required_string(body, "display_name")
        if not fields.is_email(email):
            raise validation("email must be of the form local@domain")
        if len(password) < 8:
            raise validation("password must be at least 8 characters")
        handle = fields.derive_handle(email)
        password_hash = hash_password(password)
        with self._lock:
            state = self._state
            if fields.email_key(email) in state.user_ids_by_email:
                raise ApiError(409, "email_taken", "email already registered")
            if handle in state.user_ids_by_handle:
                raise ApiError(409, "handle_taken", f"handle {handle} is already taken")
            user = state.add_user(state.new_id("u", state.users), email, password_hash,
                                  display_name, handle, 0)
            return _public_user(user, state.issue_token(user["id"]))

    def login(self, body: dict) -> dict:
        email = fields.required_string(body, "email")
        password = fields.required_string(body, "password")
        with self._lock:
            state = self._state
            user = state.users.get(state.user_ids_by_email.get(fields.email_key(email)))
        if user is None or not verify_password(password, user["password_hash"]):
            raise unauthenticated("wrong email or password")
        with self._lock:
            if self._state is not state:
                raise unauthenticated("wrong email or password")
            return _public_user(user, state.issue_token(user["id"]))

    def me(self, token: str) -> dict:
        with self._lock:
            state = self._state
            user = self._user(state, token)
            return {"user_id": user["id"], "display_name": user["display_name"],
                    "handle": user["handle"], "balance": user["balance"],
                    "currency": state.currency, "minor_units": state.minor_units}

    # ---- idempotent writes (section 7) -------------------------------------------------

    def _idempotent(self, token, key, path, body, action, guard=None):
        """Resolve a claimed key before any validation; store only successful outcomes."""
        fingerprint = canonical(body)
        with self._lock:
            state = self._state
            user = self._user(state, token)
            if guard is not None:
                guard(state, user)
            if not key:
                raise ApiError(400, "missing_idempotency_key", "Idempotency-Key is required")
            if len(key) > MAX_KEY:
                raise validation(f"Idempotency-Key must be at most {MAX_KEY} characters")
            slot = (user["id"], "POST", path, key)
            stored = state.idempotency.get(slot)
            if stored is not None:
                if stored[0] != fingerprint:
                    raise ApiError(409, "idempotency_key_reuse",
                                   "this key was used with a different body")
                return 200, stored[1]
            response = action(state, user, body)
            state.idempotency[slot] = (fingerprint, response)
            return 201, response

    @staticmethod
    def _counterparty(state: State, user: dict, body: dict, name: str, self_code: str):
        handle = fields.required_string(body, name)
        amount = fields.amount(body)
        note = fields.note(body)
        other = state.user_by_handle(handle)
        if other is None:
            raise not_found(f"no user has the handle {handle}")
        if other["id"] == user["id"]:
            raise ApiError(422, self_code, "you cannot do this with yourself")
        return other, amount, note

    def create_payment(self, token, key, path, body):
        def action(state, user, body):
            visibility = fields.visibility(body)
            other, amount, note = self._counterparty(state, user, body, "to_handle",
                                                     "self_payment")
            [payment] = state.commit_payments(
                [{"from": user, "to": other, "amount": amount, "note": note,
                  "visibility": visibility}], state.clock.now())
            return payment
        return self._idempotent(token, key, path, body, action)

    def create_request(self, token, key, path, body):
        def action(state, user, body):
            other, amount, note = self._counterparty(state, user, body, "payer_handle",
                                                     "self_request")
            return dict(state.new_request(user, other, amount, note, state.clock.now()))
        return self._idempotent(token, key, path, body, action)

    def pay_request(self, token, key, path, request_id, body):
        def action(state, user, body):
            visibility = fields.visibility(body)
            request = state.requests.get(request_id)
            if request is None:
                raise not_found("no such request")
            if request["payer_id"] != user["id"]:
                raise forbidden("only the payer may pay this request")
            if request["status"] != "pending":
                raise request_not_pending(request["status"])
            [payment] = state.commit_payments(
                [{"from": user, "to": state.users[request["requester_id"]],
                  "amount": request["amount"], "note": request["note"],
                  "visibility": visibility, "request_id": request_id}], state.clock.now())
            request["status"] = "paid"
            request["payment_id"] = payment["payment_id"]
            return payment
        return self._idempotent(token, key, path, body, action)

    def create_split(self, token, key, path, body):
        def action(state, user, body):
            amount = fields.amount(body)
            handles = fields.required_string_list(body, "participant_handles")
            if not handles:
                raise validation("participant_handles must not be empty")
            if len(set(handles)) != len(handles):
                raise validation("participant_handles must not repeat a handle")
            note = fields.note(body)
            participants = []
            for handle in handles:
                participant = state.user_by_handle(handle)
                if participant is None:
                    raise not_found(f"no user has the handle {handle}")
                participants.append(participant)
            created_at = state.clock.now()
            shares = equal_split(amount, len(participants))
            requests = [dict(state.new_request(user, p, share, note, created_at))
                        for p, share in zip(participants, shares) if p["id"] != user["id"]]
            split = {"split_id": state.new_id("sp", state.splits), "amount": amount,
                     "currency": state.currency, "note": note,
                     "shares": [{"handle": p["handle"], "amount": share}
                                for p, share in zip(participants, shares)],
                     "requests": requests, "created_at": created_at}
            state.splits[split["split_id"]] = split
            return split
        return self._idempotent(token, key, path, body, action)

    def create_settlement(self, token, key, path, body):
        def guard(state, user):
            if not state.is_operator(user["id"]):
                raise forbidden("only a settlement operator may submit settlements")

        def action(state, user, body):
            transfers = body.get("transfers")
            if not isinstance(transfers, list) or not 1 <= len(transfers) <= MAX_TRANSFERS:
                raise validation(f"transfers must hold 1 to {MAX_TRANSFERS} objects")
            batch = [self._transfer(state, entry) for entry in transfers]
            settlement_id = state.new_id("st", state.settlements)
            committed_at = state.clock.now()
            payments = state.commit_payments(batch, committed_at, settlement_id)
            settlement = {"settlement_id": settlement_id, "committed_at": committed_at,
                          "payments": payments}
            state.settlements[settlement_id] = settlement
            return settlement
        return self._idempotent(token, key, path, body, action, guard)

    @staticmethod
    def _transfer(state: State, entry) -> dict:
        """One settlement entry under the ordinary payment rules; shape errors are 422."""
        if not isinstance(entry, dict):
            raise validation("each transfer must be an object")
        for name in ("from_handle", "to_handle"):
            if not isinstance(entry.get(name), str):
                raise validation(f"each transfer needs a string {name}")
        amount = fields.amount(entry)
        note = fields.note(entry)
        visibility = fields.visibility(entry)
        sender = state.user_by_handle(entry["from_handle"])
        receiver = state.user_by_handle(entry["to_handle"])
        if sender is None or receiver is None:
            raise not_found("a transfer names an unknown handle")
        if sender["id"] == receiver["id"]:
            raise ApiError(422, "self_payment", "a transfer cannot pay its own sender")
        return {"from": sender, "to": receiver, "amount": amount, "note": note,
                "visibility": visibility}

    # ---- request state changes without keys -------------------------------------------

    def _resolve_request(self, token, request_id, role: str, target: str, blocked: tuple):
        with self._lock:
            state = self._state
            user = self._user(state, token)
            request = state.requests.get(request_id)
            if request is None:
                raise not_found("no such request")
            if request[role] != user["id"]:
                raise forbidden(f"only the {role[:-3]} may do this")
            if request["status"] in blocked:
                raise request_not_pending(request["status"])
            request["status"] = target
            return dict(request)

    def decline_request(self, token, request_id):
        return self._resolve_request(token, request_id, "payer_id", "declined",
                                     ("paid", "cancelled"))

    def cancel_request(self, token, request_id):
        return self._resolve_request(token, request_id, "requester_id", "cancelled",
                                     ("paid", "declined"))

    # ---- reads ------------------------------------------------------------------------

    def list_requests(self, token, query: dict) -> dict:
        direction = fields.query_choice(query, "direction", DIRECTIONS)
        status = fields.query_choice(query, "status", ("pending", "paid", "declined",
                                                        "cancelled"))
        paging = _paging(query)
        with self._lock:
            state = self._state
            user_id = self._user(state, token)["id"]
            items = [dict(r) for r in reversed(state.requests.values())
                     if (r["payer_id"] == user_id and direction != "outgoing"
                         or r["requester_id"] == user_id and direction != "incoming")
                     and (status is None or r["status"] == status)]
        page, has_more = _page(items, paging)
        return {"requests": page, "has_more": has_more}

    def activity(self, token, query: dict) -> dict:
        paging = _paging(query)
        with self._lock:
            state = self._state
            user_id = self._user(state, token)["id"]
            items = [p for p in reversed(state.payments)
                     if p["visibility"] == "public"
                     or user_id in (p["from_user_id"], p["to_user_id"])]
        page, has_more = _page(items, paging)
        return {"payments": page, "has_more": has_more}

