"""POST /correction-batches (stage 4): a settlement operator corrects up to 32 payments at
once, including whole settlements.

Checks, in order: the batch shape; each item's own errors in input order; settlement
completeness and shared effective instants; then the combined current and historical
funds (corrections.record). All revisions are recorded at one instant.

Mixed into Service, which provides `_idempotent`.
"""
from . import corrections
from .clock import parse_instant
from .errors import ApiError, forbidden, validation

MAX_ITEMS = 32


def _check_settlements(state, items) -> None:
    """Any settlement touched must be corrected whole, at one effective instant."""
    included = {payment["payment_id"]: effective for payment, _, effective, _ in items}
    touched = {payment["settlement_id"] for payment, _, _, _ in items
               if payment["settlement_id"] is not None}
    for settlement_id in sorted(touched):
        if any(member not in included for member in state.settlement_members[settlement_id]):
            raise ApiError(422, "incomplete_settlement",
                           f"every member of settlement {settlement_id} must be corrected")
    for settlement_id in sorted(touched):
        instants = {parse_instant(included[member])
                    for member in state.settlement_members[settlement_id]}
        if len(instants) != 1:
            raise validation(f"members of settlement {settlement_id} need one effective_at")


class CorrectionBatchEndpoints:
    def correct_batch(self, token, key, path, body):
        def guard(state, user):
            if not state.is_operator(user["id"]):
                raise forbidden("only a settlement operator may submit correction batches")

        def action(state, user, body):
            requested = body.get("corrections")
            if (not isinstance(requested, list) or not 1 <= len(requested) <= MAX_ITEMS
                    or not all(isinstance(item, dict) for item in requested)):
                raise validation(f"corrections must hold 1 to {MAX_ITEMS} objects")
            ids = [item.get("payment_id") for item in requested]
            if not all(isinstance(payment_id, str) for payment_id in ids):
                raise validation("each correction needs a payment_id")
            if len(set(ids)) != len(ids):
                raise validation("each payment may appear once in a batch")
            items = []
            for item in requested:
                expected, amount, effective_text, reason = corrections.parse_fields(item)
                payment = corrections.find(state, item["payment_id"])
                corrections.check_linked(payment, allow_settlement=True)
                corrections.check_revision(state, payment, expected, amount)
                items.append((payment, amount, effective_text, reason))
            _check_settlements(state, items)
            batch_id = state.new_id("cb", ())
            revisions = corrections.record(state, items, batch_id)
            return {"correction_batch_id": batch_id, "recorded_at": revisions[0]["recorded_at"],
                    "revisions": revisions}
        return self._idempotent(token, key, path, body, action, guard)
