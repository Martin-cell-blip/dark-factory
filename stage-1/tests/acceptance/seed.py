"""Reset fixtures (spec section 4) used by the acceptance checks."""
PASSWORD = "long enough 1"


def user(handle: str, balance: int, **extra) -> dict:
    record = {"id": f"u_{handle}", "email": f"{handle}@pocket.test", "password": PASSWORD,
              "display_name": handle.capitalize(), "handle": handle, "balance": balance}
    record.update(extra)
    return record


def fixture(users=None, currency="EUR", minor_units=2, **extra) -> dict:
    body = {"currency": currency, "minor_units": minor_units,
            "users": users if users is not None else
            [user("ann", 10000), user("ben", 2500), user("cat", 500)]}
    body.update(extra)
    return body


def total(fx: dict) -> int:
    return sum(u["balance"] for u in fx["users"])
