"""Stage-3 endpoints: GET /me at an instant, GET /statement with snapshots, and payment
corrections with their revision history.

Mixed into Service, which provides the lock, `_state_now`, `_user` and `_idempotent`.
"""
import secrets

from . import corrections, fields, history
from .errors import forbidden, not_found, validation
from .holds import utc_now
from .paging import page, page_params

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
            expected, amount, effective_text, reason = corrections.parse_fields(body)
            payment = corrections.find(state, payment_id)
            if payment["from_user_id"] != user["id"]:
                raise forbidden("only the original sender may correct a payment")
            corrections.check_linked(payment, allow_settlement=False)
            corrections.check_revision(state, payment, expected, amount)
            [revision] = corrections.record(state, [(payment, amount, effective_text, reason)])
            return revision
        return self._idempotent(token, key, path, body, action)

    def list_revisions(self, token, payment_id) -> dict:
        with self._lock:
            state = self._state_now()
            user = self._user(state, token)
            payment = state.payments_by_id.get(payment_id)
            if payment is None or not _is_party(payment, user["id"]):
                raise not_found("no such payment")
            return {"revisions": state.revisions.of(payment_id)}

