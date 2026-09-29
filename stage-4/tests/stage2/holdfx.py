"""Helpers for stage-2 checks: authorisations, money formatting and screen selectors."""
from datetime import datetime, timedelta, timezone

import seed
from client import expect, login


def later(hours: float) -> str:
    """An RFC 3339 time relative to now (seeded expiries are at least an hour away)."""
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat(timespec="seconds")


def seeded_hold(hold_id: str, payer: str, receiver: str, amount: int, *, status="open",
                hours: float = 2, note: str = "deposit", visibility: str = "public") -> dict:
    return {"id": hold_id, "from_user_id": f"u_{payer}", "to_user_id": f"u_{receiver}",
            "amount": amount, "note": note, "visibility": visibility, "status": status,
            "expires_at": later(hours)}


def authorize(client, to_handle: str, amount: int, **extra) -> dict:
    body = {"to_handle": to_handle, "amount": amount, **extra}
    return expect(client.write("/authorizations", body), 201).json()


def capture(client, authorization_id: str, body=None, status: int = 201, code=None):
    return expect(client.write(f"/authorizations/{authorization_id}/capture",
                               {} if body is None else body), status, code)


def me(client) -> dict:
    return expect(client.get("/me"), 200).json()


def signed_in(*handles):
    return [login(f"{h}@pocket.test", seed.PASSWORD) for h in handles]


def sel(testid: str) -> str:
    return f"[data-testid='{testid}']"


def money(minor: int, minor_units: int = 2, currency: str = "EUR") -> str:
    """The spec's formatted amount: `100.00 EUR`, `1200 JPY`, `1.500 BHD`."""
    if minor_units == 0:
        return f"{minor} {currency}"
    text = str(minor).rjust(minor_units + 1, "0")
    return f"{text[:-minor_units]}.{text[-minor_units:]} {currency}"
