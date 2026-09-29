"""Effective time and recorded time (stage 3): payment revisions and historical views.

Every payment has revisions. Revision 1 is the payment as made (effective_at = recorded_at
= created_at); a correction appends a revision with a new amount, its own effective_at and
a server-assigned recorded_at. A view at (T, K) selects, for each payment, its latest
revision recorded at or before K and counts it when that revision took effect at or before
T. Holds are reconstructed from each authorisation's creation, captures and close.

A wallet's opening balance is what it held before anything moved: its current balance
minus the net of every payment's latest revision. A correction changes the balance and the
latest revision by the same amount, so the opening balance never changes.
"""
import bisect
from datetime import datetime, timezone

from .clock import parse_time

ALWAYS = datetime.max.replace(tzinfo=timezone.utc)   # "everything known" / "no end"
NEVER = datetime.min.replace(tzinfo=timezone.utc)    # "from the opening of the wallet"


class Revisions:
    """Revision lists per payment, each kept in recorded order (recorded times increase)."""

    def __init__(self) -> None:
        self._by_payment: dict[str, list[dict]] = {}
        self._recorded: dict[str, list[datetime]] = {}
        self._effective: dict[str, list[datetime]] = {}

    def start(self, payment: dict) -> None:
        """Revision 1: the payment as made."""
        self._by_payment[payment["payment_id"]] = []
        self._recorded[payment["payment_id"]] = []
        self._effective[payment["payment_id"]] = []
        self._append(payment["payment_id"], payment["amount"], payment["created_at"],
                     payment["created_at"], "")

    def append(self, payment_id: str, amount: int, effective_at: str, recorded_at: str,
               reason: str) -> dict:
        return dict(self._append(payment_id, amount, effective_at, recorded_at, reason))

    def _append(self, payment_id, amount, effective_at, recorded_at, reason) -> dict:
        revisions = self._by_payment[payment_id]
        revision = {"payment_id": payment_id, "revision": len(revisions) + 1, "amount": amount,
                    "effective_at": effective_at, "recorded_at": recorded_at, "reason": reason}
        revisions.append(revision)
        self._recorded[payment_id].append(parse_time(recorded_at))
        self._effective[payment_id].append(parse_time(effective_at))
        return revision

    def of(self, payment_id: str) -> list[dict]:
        return [dict(r) for r in self._by_payment[payment_id]]

    def latest(self, payment_id: str) -> dict:
        return self._by_payment[payment_id][-1]

    def select(self, payment_id: str, known: datetime):
        """(revision, effective datetime) of the latest revision recorded at or before
        `known`, or None when nothing about the payment was recorded yet."""
        index = bisect.bisect_right(self._recorded[payment_id], known) - 1
        if index < 0:
            return None
        return self._by_payment[payment_id][index], self._effective[payment_id][index]

    def corrections(self) -> list[dict]:
        """Every revision after the first, for export."""
        return [dict(r) for revisions in self._by_payment.values() for r in revisions[1:]]


def signed(payment: dict, user_id: str, amount: int) -> int:
    return -amount if payment["from_user_id"] == user_id else amount


def opening_balance(state, user_id: str) -> int:
    total = state.users[user_id]["balance"]
    for payment in state.user_payments.get(user_id, []):
        total -= signed(payment, user_id, state.revisions.latest(payment["payment_id"])["amount"])
    return total


def balance_at(state, user_id: str, as_of: datetime, known: datetime) -> int:
    """Inclusive: payments whose selected revision took effect at or before `as_of`."""
    total = opening_balance(state, user_id)
    for payment in state.user_payments.get(user_id, []):
        selected = state.revisions.select(payment["payment_id"], known)
        if selected is not None and selected[1] <= as_of:
            total += signed(payment, user_id, selected[0]["amount"])
    return total


def _capture_times(state, authorization: dict) -> list[tuple[datetime, int]]:
    return [(parse_time(state.payments_by_id[p]["created_at"]), state.payments_by_id[p]["amount"])
            for p in authorization["payment_ids"]]


def _close_time(authorization: dict) -> datetime | None:
    if authorization["closed_at"] is None:
        return None
    return max(parse_time(authorization["closed_at"]), parse_time(authorization["created_at"]))


def held_at(state, user_id: str, as_of: datetime, known: datetime) -> int:
    """What the user's authorisations held at `as_of`, as known at `known`.

    Creation, captures, voids and final captures are known at their own event time; clock
    expiry is known as soon as creation is, so an open hold expires at its deadline."""
    held = 0
    for authorization in state.holds.by_payer(user_id):
        created = parse_time(authorization["created_at"])
        if created > as_of or created > known:
            continue
        seen = min(as_of, known)
        captured = sum(amount for at, amount in _capture_times(state, authorization) if at <= seen)
        closed = _close_time(authorization)
        if closed is not None and closed <= as_of:
            by_clock = authorization["authorization_id"] in state.holds.clock_expired
            if (created if by_clock else closed) <= known:
                continue
        if parse_time(authorization["expires_at"]) <= as_of:
            continue
        held += max(0, authorization["amount"] - captured)
    return held


def never_negative(state, user_id: str, override: dict | None = None) -> bool:
    """Under the latest revisions (with `override` = {payment_id: (amount, effective)}),
    total and available stay nonnegative at every effective and hold-event boundary,
    counting everything that happens at one instant together."""
    override = override or {}
    events: list[tuple[datetime, int, int]] = []   # (instant, balance change, held change)
    for payment in state.user_payments.get(user_id, []):
        payment_id = payment["payment_id"]
        if payment_id in override:
            amount, effective = override[payment_id]
        else:
            revision = state.revisions.latest(payment_id)
            amount, effective = revision["amount"], parse_time(revision["effective_at"])
        events.append((effective, signed(payment, user_id, amount), 0))
    for authorization in state.holds.by_payer(user_id):
        created = parse_time(authorization["created_at"])
        events.append((created, 0, authorization["amount"]))
        captures = _capture_times(state, authorization)
        events.extend((max(at, created), 0, -amount) for at, amount in captures)
        release = authorization["amount"] - sum(amount for _, amount in captures)
        closed = _close_time(authorization) or parse_time(authorization["expires_at"])
        events.append((max(closed, created), 0, -release))
    events.sort(key=lambda event: event[0])
    total, held = opening_balance(state, user_id), 0
    for index, (instant, balance_change, held_change) in enumerate(events):
        total += balance_change
        held += held_change
        last_at_instant = index + 1 == len(events) or events[index + 1][0] != instant
        if last_at_instant and (total < 0 or total - held < 0):
            return False
    return True


def statement(state, user_id: str, start: datetime, end: datetime, known: datetime) -> dict:
    """The half-open window [start, end) by selected effective time, oldest first, with the
    balance after each entry. The whole window is computed; callers page it."""
    before, window = opening_balance(state, user_id), []
    for payment in state.user_payments.get(user_id, []):
        selected = state.revisions.select(payment["payment_id"], known)
        if selected is None:
            continue
        revision, effective = selected
        if effective < start:
            before += signed(payment, user_id, revision["amount"])
        elif effective < end:
            window.append((effective, payment["payment_id"], payment, revision))
    window.sort(key=lambda item: (item[0], item[1]))
    running, entries = before, []
    for _, _, payment, revision in window:
        delta = signed(payment, user_id, revision["amount"])
        running += delta
        entries.append({"payment": {**payment, "amount": revision["amount"]}, "delta": delta,
                        "balance_after": running, "revision": revision["revision"],
                        "effective_at": revision["effective_at"],
                        "recorded_at": revision["recorded_at"]})
    return {"opening_balance": before, "entries": entries, "closing_balance": running}
