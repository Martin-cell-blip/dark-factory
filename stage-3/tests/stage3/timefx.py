"""Helpers for stage-3 checks: instants, historical reads, statements and corrections."""
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import seed
from client import expect, login


def instant(moment: datetime) -> str:
    return moment.isoformat()


def now() -> datetime:
    return datetime.now(timezone.utc)


def ago(**delta) -> str:
    return instant(now() - timedelta(**delta))


def ahead(**delta) -> str:
    return instant(now() + timedelta(**delta))


def at(stamp: str, **delta) -> str:
    return instant(datetime.fromisoformat(stamp) + timedelta(**delta))


def query(**params) -> str:
    return "?" + urlencode({k.rstrip("_"): v for k, v in params.items()}) if params else ""


def me_at(client, status=200, code=None, **params):
    return expect(client.get("/me" + query(**params)), status, code).json()


def statement(client, status=200, code=None, **params):
    return expect(client.get("/statement" + query(**params)), status, code).json()


def whole_statement(client, **params) -> dict:
    """Every entry of one window, paging through its snapshot."""
    first = statement(client, limit=200, **params)
    entries = list(first["entries"])
    while len(entries) < 10_000:
        page = statement(client, snapshot=first["snapshot"], limit=200, offset=len(entries))
        if not page["entries"]:
            break
        entries += page["entries"]
    return {**first, "entries": entries}


def pay(client, to_handle, amount, **extra) -> dict:
    return expect(client.write("/payments", {"to_handle": to_handle, "amount": amount, **extra}),
                  201).json()


def correct(client, payment_id, amount, effective_at, expected_revision=1, reason="fix",
            status=201, code=None, key=None):
    body = {"expected_revision": expected_revision, "amount": amount,
            "effective_at": effective_at, "reason": reason}
    return expect(client.write(f"/payments/{payment_id}/corrections", body, key=key),
                  status, code)


def signed_in(*handles):
    return [login(f"{h}@pocket.test", seed.PASSWORD) for h in handles]


def seeded_payment(payment_id, payer, receiver, amount, created_at=None, **extra) -> dict:
    record = {"id": payment_id, "from_user_id": f"u_{payer}", "to_user_id": f"u_{receiver}",
              "amount": amount, **extra}
    if created_at is not None:
        record["created_at"] = created_at
    return record
