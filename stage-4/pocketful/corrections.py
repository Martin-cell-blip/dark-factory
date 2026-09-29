"""Payment corrections, one or many at once (stages 3 and 4).

A single correction (the original sender) and a correction batch (a settlement operator)
share every rule here: field validation, which payments may be corrected, the expected
revision, refunded amounts, and one combined check of current and historical funds before
all new revisions are recorded at one instant.
"""
from . import fields, history
from .clock import parse_instant
from .errors import ApiError, malformed, not_found, validation
from .holds import utc_now

MAX_REASON = 200


def parse_fields(body: dict):
    """(expected_revision, amount, effective_at text, reason); wrong JSON types 400,
    rules 422. Every field is required."""
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


def immutable(message: str) -> ApiError:
    return ApiError(422, "linked_payment_immutable", message)


def find(state, payment_id: str) -> dict:
    payment = state.payments_by_id.get(payment_id)
    if payment is None:
        raise not_found(f"no such payment {payment_id}")
    return payment


def check_linked(payment: dict, allow_settlement: bool) -> None:
    """Captures and refunds are never corrected; a settlement member only in a batch."""
    if payment["authorization_id"] is not None:
        raise immutable("a capture cannot be corrected")
    if payment["refund_of"] is not None:
        raise immutable("a refund cannot be corrected")
    if payment["settlement_id"] is not None and not allow_settlement:
        raise immutable("a settlement member can only be corrected in a correction batch")


def check_revision(state, payment: dict, expected: int, amount: int) -> None:
    latest = state.revisions.latest(payment["payment_id"])
    if expected != latest["revision"]:
        raise ApiError(409, "stale_revision", f"the payment is at revision {latest['revision']}")
    if amount < state.refunded(payment["payment_id"]):
        raise ApiError(422, "refund_exceeds_payment",
                       "the payment cannot be corrected below what was already refunded")


def record(state, items: list[tuple[dict, int, str, str]], batch_id=None) -> list[dict]:
    """Record new revisions for (payment, amount, effective_at, reason) items as one step.

    Each item moves the difference from the payment's latest amount between its two
    wallets. The combined movement must be affordable from available funds now (else
    insufficient_funds) and keep every affected wallet's total and available nonnegative
    at every effective and hold-event boundary (else historical_overdraft)."""
    deltas: dict[str, int] = {}
    override = {}
    for payment, amount, effective_text, _ in items:
        change = amount - state.revisions.latest(payment["payment_id"])["amount"]
        deltas[payment["from_user_id"]] = deltas.get(payment["from_user_id"], 0) - change
        deltas[payment["to_user_id"]] = deltas.get(payment["to_user_id"], 0) + change
        override[payment["payment_id"]] = (amount, parse_instant(effective_text))
    for user_id, delta in deltas.items():
        if delta < 0 and state.available(user_id) < -delta:
            raise ApiError(409, "insufficient_funds",
                           "a wallet cannot afford this correction now")
    if not all(history.never_negative(state, user_id, override) for user_id in deltas):
        raise ApiError(409, "historical_overdraft",
                       "a wallet would have been overdrawn in the past")
    state.move(deltas)
    recorded_at = state.clock.now()
    return [state.revisions.append(payment["payment_id"], amount, effective_text, recorded_at,
                                   reason, batch_id)
            for payment, amount, effective_text, reason in items]
