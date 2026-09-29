"""POST /payments/{payment_id}/refunds (stage 4).

A refund is a new ordinary payment back from the original receiver to the original sender,
linked by refund_of. It moves existing money from the receiver's available funds and never
reopens a request or an authorisation, restores a hold, or changes settlement membership.

Mixed into Service, which provides `_idempotent`.
"""
from . import corrections, fields
from .errors import ApiError, forbidden


class RefundEndpoints:
    def refund_payment(self, token, key, path, payment_id, body):
        def action(state, user, body):
            amount = fields.amount(body)
            payment = corrections.find(state, payment_id)
            if payment["to_user_id"] != user["id"]:
                raise forbidden("only the original receiver may refund a payment")
            if payment["refund_of"] is not None:
                raise ApiError(422, "invalid_refund_target", "a refund cannot be refunded")
            corrected = state.revisions.latest(payment_id)["amount"]
            if state.refunded(payment_id) + amount > corrected:
                raise ApiError(422, "refund_exceeds_payment",
                               "refunds would exceed the payment's corrected amount")
            [refund] = state.commit_payments(
                [{"from": user, "to": state.users[payment["from_user_id"]], "amount": amount,
                  "note": payment["note"], "visibility": payment["visibility"],
                  "refund_of": payment_id}],
                state.clock.now())
            return refund
        return self._idempotent(token, key, path, body, action)
