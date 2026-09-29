"""The authorisation endpoints (stage 2): authorise, capture, void and list.

Mixed into Service, which provides the lock, `_state_now`, `_user`, `_counterparty`,
and `_idempotent`, which these methods rely on.
"""
from . import fields, holds
from .errors import ApiError, forbidden, insufficient_funds, not_found
from .paging import page, page_params

DIRECTIONS = ("outgoing", "incoming")


def _view(authorization: dict) -> dict:
    """A copy the caller may keep: later captures must not change a stored response."""
    return {**authorization, "payment_ids": list(authorization["payment_ids"])}


def _require_open(state, authorization: dict) -> None:
    """S2-D3: an authorisation expired by the clock answers authorization_expired; any
    other closed one (captured, voided, or seeded as expired) authorization_not_open."""
    status = authorization["status"]
    if status == "open":
        return
    if status == "expired" and authorization["authorization_id"] in state.holds.clock_expired:
        raise ApiError(409, "authorization_expired", "the authorization has expired")
    raise ApiError(409, "authorization_not_open", f"the authorization is {status}")


class AuthorizationEndpoints:
    def create_authorization(self, token, key, path, body):
        def action(state, user, body):
            visibility = fields.visibility(body)
            receiver, amount, note = self._counterparty(state, user, body, "to_handle",
                                                        "self_payment")
            if state.available(user["id"]) < amount:
                raise insufficient_funds()
            created_at = state.clock.now()
            authorization = holds.record(
                state.new_id("a", state.holds.authorizations), user, receiver, amount,
                state.currency, note, visibility, "open",
                holds.expires_at(created_at, state.holds.ttl_seconds), created_at)
            state.holds.add(authorization)
            return _view(authorization)
        return self._idempotent(token, key, path, body, action)

    def capture_authorization(self, token, key, path, authorization_id, body):
        def action(state, user, body):
            amount = fields.positive_integer(body["amount"]) if "amount" in body else None
            final = fields.optional_boolean(body, "final", True)
            authorization = state.holds.authorizations.get(authorization_id)
            if authorization is None:
                raise not_found("no such authorization")
            if authorization["to_user_id"] != user["id"]:
                raise forbidden("only the receiver may capture this authorization")
            _require_open(state, authorization)
            remaining = authorization["remaining_amount"]
            amount = remaining if amount is None else amount
            if amount > remaining:
                raise ApiError(422, "capture_exceeds_authorization",
                               f"only {remaining} remains to capture")
            closes = final or amount == remaining
            payer = state.users[authorization["from_user_id"]]
            [payment] = state.commit_payments(
                [{"from": payer, "to": user, "amount": amount,
                  "note": authorization["note"], "visibility": authorization["visibility"],
                  "authorization_id": authorization_id}],
                state.clock.now(), held_release={payer["id"]: remaining if closes else amount})
            state.holds.capture(authorization, amount, closes, payment)
            return payment
        return self._idempotent(token, key, path, body, action)

    def void_authorization(self, token, authorization_id):
        with self._lock:
            state = self._state_now()
            user = self._user(state, token)
            authorization = state.holds.authorizations.get(authorization_id)
            if authorization is None:
                raise not_found("no such authorization")
            if authorization["from_user_id"] != user["id"]:
                raise forbidden("only the payer may void this authorization")
            if authorization["status"] != "voided":
                if authorization["status"] != "open":
                    raise ApiError(409, "authorization_not_open",
                                   f"the authorization is {authorization['status']}")
                state.holds.close(authorization, "voided", state.clock.now())
            return _view(authorization)

    def list_authorizations(self, token, query: dict) -> dict:
        direction = fields.query_choice(query, "direction", DIRECTIONS)
        status = fields.query_choice(query, "status", holds.STATUSES)
        paging = page_params(query)
        with self._lock:
            state = self._state_now()
            user_id = self._user(state, token)["id"]
            items = [_view(a) for a in reversed(state.holds.authorizations.values())
                     if (a["from_user_id"] == user_id and direction != "incoming"
                         or a["to_user_id"] == user_id and direction != "outgoing")
                     and (status is None or a["status"] == status)]
        shown, has_more = page(items, paging)
        return {"authorizations": shown, "has_more": has_more}
