"""Authorisations and the holds they place on the payer's wallet (stages 2 and 3).

A hold reserves money without moving it: `held` per user is the sum of the remaining
amounts of that user's open authorisations. Expiry follows the clock: every read or write
first calls `expire_due`, so an authorisation past its `expires_at` is expired and holds
nothing even if no request arrived at the deadline.
"""
import heapq
from datetime import datetime, timedelta, timezone

from .clock import format_time, parse_time

STATUSES = ("open", "captured", "voided", "expired")
DEFAULT_TTL_SECONDS = 600


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def expires_at(created_at: str, ttl_seconds: int) -> str:
    return format_time(parse_time(created_at) + timedelta(seconds=ttl_seconds))


def record(authorization_id: str, payer: dict, receiver: dict, amount: int, currency: str,
           note: str, visibility: str, status: str, expires: str, created_at: str,
           captured_amount: int = 0, remaining_amount: int | None = None,
           payment_ids: list | None = None, closed_at: str | None = None) -> dict:
    """An authorisation exactly as the API returns it. closed_at is null while open and
    the time of the capture, void or expiry that closed it (stage 3)."""
    payment_ids = list(payment_ids or [])
    if remaining_amount is None:
        remaining_amount = amount - captured_amount if status == "open" else 0
    return {
        "authorization_id": authorization_id,
        "from_user_id": payer["id"], "from_handle": payer["handle"],
        "to_user_id": receiver["id"], "to_handle": receiver["handle"],
        "amount": amount, "captured_amount": captured_amount,
        "remaining_amount": remaining_amount, "currency": currency,
        "note": note, "visibility": visibility, "status": status,
        "expires_at": expires, "payment_id": payment_ids[-1] if payment_ids else None,
        "payment_ids": payment_ids, "created_at": created_at, "closed_at": closed_at,
    }


class Holds:
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self.authorizations: dict[str, dict] = {}
        self.clock_expired: set[str] = set()
        self._held: dict[str, int] = {}
        self._by_payer: dict[str, list[dict]] = {}
        self._deadlines: list[tuple[datetime, str]] = []

    def held_by(self, user_id: str) -> int:
        return self._held.get(user_id, 0)

    def by_payer(self, user_id: str) -> list[dict]:
        return self._by_payer.get(user_id, [])

    def add(self, authorization: dict) -> None:
        """Track an authorisation; an open one holds its remaining amount until it closes."""
        self.authorizations[authorization["authorization_id"]] = authorization
        self._by_payer.setdefault(authorization["from_user_id"], []).append(authorization)
        if authorization["status"] == "open":
            payer = authorization["from_user_id"]
            self._held[payer] = self.held_by(payer) + authorization["remaining_amount"]
            heapq.heappush(self._deadlines, (parse_time(authorization["expires_at"]),
                                             authorization["authorization_id"]))

    def expire_due(self, now: datetime) -> None:
        while self._deadlines and self._deadlines[0][0] <= now:
            _, authorization_id = heapq.heappop(self._deadlines)
            authorization = self.authorizations.get(authorization_id)
            if authorization is not None and authorization["status"] == "open":
                self.close(authorization, "expired", authorization["expires_at"])
                self.clock_expired.add(authorization_id)

    def capture(self, authorization: dict, amount: int, closes: bool, payment: dict) -> None:
        """Record a capture whose money has moved; a closing capture releases the rest."""
        authorization["captured_amount"] += amount
        authorization["payment_ids"].append(payment["payment_id"])
        authorization["payment_id"] = payment["payment_id"]
        self._release(authorization, amount)
        if closes:
            self.close(authorization, "captured", payment["created_at"])

    def close(self, authorization: dict, status: str, at: str) -> None:
        """Void, expiry or a closing capture at `at`: release what is still held."""
        self._release(authorization, authorization["remaining_amount"])
        authorization["status"] = status
        authorization["closed_at"] = at

    def _release(self, authorization: dict, amount: int) -> None:
        payer = authorization["from_user_id"]
        self._held[payer] = self.held_by(payer) - amount
        authorization["remaining_amount"] -= amount
