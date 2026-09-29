"""Stage-3 endpoints: GET /me at an instant, GET /statement with snapshots, and payment
corrections with their revision history.

Mixed into Service, which provides the lock, `_state_now`, `_user` and `_idempotent`.
"""
import secrets

from . import fields, history
from .clock import parse_instant
from .errors import ApiError, forbidden, malformed, not_found, validation
from .holds import utc_now
from .paging import page, page_params

MAX_REASON = 200
WINDOW_PARAMS = ("from", "to", "known_at")


def _read_instant(state):
    """The instant a read begins: never before the last event the service recorded."""
    now = utc_now()
    return max(now, state.clock.last) if state.clock.last is not None else now


def _is_party(payment: dict, user_id: str) -> bool:
    return user_id in (payment["from_user_id"], payment["to_user_id"])


class HistoryEndpoints:
    # ---- GET /me?as_of=&known_at= ----------------------------------------------------

    def me_at(self, token, query: dict) -> dict:
        as_of_text, as_of = fields.query_instant(query, "as_of")
        known_text, known = fields.query_instant(query, "known_at")
        if as_of is None and known is None:
            return self.me(token)
        with self._lock:
            state = self._state_now()
            user = self._user(state, token)
            view_at = as_of or _read_instant(state)
            known = known or history.ALWAYS
            total = history.balance_at(state, user["id"], view_at, known)
            held = history.held_at(state, user["id"], view_at, known)
            body = {"user_id": user["id"], "display_name": user["display_name"],
                    "handle": user["handle"], "balance": total, "total": total,
                    "available": total - held, "held": held, "currency": state.currency,
                    "minor_units": state.minor_units}
        if as_of_text is not None:
            body["as_of"] = as_of_text
        if known_text is not None:
            body["known_at"] = known_text
        return body

    # ---- GET /statement ----------------------------------------------------------------

    def statement(self, token, query: dict) -> dict:
        if "snapshot" in query:
            if any(name in query for name in WINDOW_PARAMS):
                raise validation("only limit and offset may accompany a snapshot")
            params = page_params(query)
            with self._lock:
                state = self._state_now()
                user = self._user(state, token)
                snapshot = query["snapshot"]
                frozen = state.snapshots.get(snapshot)
                if frozen is None or frozen["user_id"] != user["id"]:
                    raise not_found("no such statement snapshot")
                result = frozen["result"]
        else:
            _, start = fields.query_instant(query, "from")
            _, end = fields.query_instant(query, "to")
            known_text, known = fields.query_instant(query, "known_at")
            if start is not None and end is not None and start > end:
                raise validation("from must not be after to")
            params = page_params(query)
            with self._lock:
                state = self._state_now()
                user = self._user(state, token)
                result = history.statement(state, user["id"], start or history.NEVER,
                                           end or _read_instant(state),
                                           known or history.ALWAYS)
                if known_text is not None:
                    result["known_at"] = known_text
                snapshot = secrets.token_urlsafe(24)
                state.snapshots[snapshot] = {"user_id": user["id"], "result": result}
        entries, has_more = page(result["entries"], params)
        body = {"opening_balance": result["opening_balance"], "entries": entries,
                "closing_balance": result["closing_balance"], "has_more": has_more,
                "snapshot": snapshot}
        if "known_at" in result:
            body["known_at"] = result["known_at"]
        return body

    # ---- corrections -------------------------------------------------------------------

    def correct_payment(self, token, key, path, payment_id, body):
        def action(state, user, body):
            expected, amount, effective_text, reason = _correction_fields(body)
            payment = state.payments_by_id.get(payment_id)
            if payment is None:
                raise not_found("no such payment")
            if payment["from_user_id"] != user["id"]:
                raise forbidden("only the original sender may correct a payment")
            if payment["settlement_id"] is not None or payment["authorization_id"] is not None:
                raise ApiError(422, "linked_payment_immutable",
                               "settlement members and captures cannot be corrected")
            latest = state.revisions.latest(payment_id)
            if expected != latest["revision"]:
                raise ApiError(409, "stale_revision",
                               f"the payment is at revision {latest['revision']}")
            sender, receiver = payment["from_user_id"], payment["to_user_id"]
            change = amount - latest["amount"]
            deltas = {sender: -change, receiver: change}
            for user_id, delta in deltas.items():
                if delta < 0 and state.available(user_id) < -delta:
                    raise ApiError(409, "insufficient_funds",
                                   "the wallet cannot afford this correction now")
            override = {payment_id: (amount, parse_instant(effective_text))}
            if not all(history.never_negative(state, u, override) for u in (sender, receiver)):
                raise ApiError(409, "historical_overdraft",
                               "a wallet would have been overdrawn in the past")
            state.move(deltas)
            return state.revisions.append(payment_id, amount, effective_text,
                                          state.clock.now(), reason)
        return self._idempotent(token, key, path, body, action)

    def list_revisions(self, token, payment_id) -> dict:
        with self._lock:
            state = self._state_now()
            user = self._user(state, token)
            payment = state.payments_by_id.get(payment_id)
            if payment is None or not _is_party(payment, user["id"]):
                raise not_found("no such payment")
            return {"revisions": state.revisions.of(payment_id)}


def _correction_fields(body: dict):
    """The correction body: every field required; wrong JSON types 400, rules 422."""
    for name in ("expected_revision", "amount", "effective_at", "reason"):
        if name not in body:
            raise validation(f"{name} is required")
    expected = body["expected_revision"]
    if isinstance(expected, bool) or not isinstance(expected, (int, float)):
        raise malformed("expected_revision must be a number")
    expected = fields.positive_integer(expected, "expected_revision")
    amount = fields.count_amount(body["amount"])
    effective_text = fields.required_string(body, "effective_at")
    effective = parse_instant(effective_text)
    if effective is None:
        raise validation("effective_at must be an RFC 3339 instant with an offset")
    if effective > utc_now():
        raise validation("effective_at cannot be later than now")
    reason = fields.required_string(body, "reason")
    if not 1 <= len(reason) <= MAX_REASON:
        raise validation(f"reason must be 1 to {MAX_REASON} characters")
    return expected, amount, effective_text, reason
