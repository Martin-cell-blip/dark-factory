"""Field rules shared by every endpoint (spec sections 4 and 5, decision D3).

Wrong JSON type -> 400 malformed_request, except amount, note and visibility which are
422 validation_failed. A missing required field -> 422 validation_failed.
"""
import math
import re

from .errors import malformed, validation

MAX_AMOUNT = 1_000_000_000
MAX_NOTE = 200
VISIBILITIES = ("public", "private")
HANDLE_PATTERN = re.compile(r"[a-z0-9_]{1,20}")
MAX_ID = 64


def positive_integer(value, name: str = "amount") -> int:
    """An integral JSON number of at least 1 (1000, 1000.0 and 1e3 are the same value)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise validation(f"{name} must be a number")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise validation(f"{name} must be an integer")
        value = int(value)
    if value < 1:
        raise validation(f"{name} must be at least 1")
    return value


def amount_value(value) -> int:
    """The one amount rule: an integral JSON number from 1 to 1000000000."""
    value = positive_integer(value)
    if value > MAX_AMOUNT:
        raise validation(f"amount must be between 1 and {MAX_AMOUNT}")
    return value


def amount(body: dict) -> int:
    if "amount" not in body:
        raise validation("amount is required")
    return amount_value(body["amount"])


def note(body: dict) -> str:
    if "note" not in body:
        return ""
    value = body["note"]
    if not isinstance(value, str):
        raise validation("note must be a string")
    if len(value) > MAX_NOTE:
        raise validation(f"note must be at most {MAX_NOTE} characters")
    return value


def visibility(body: dict) -> str:
    if "visibility" not in body:
        return "public"
    value = body["visibility"]
    if not isinstance(value, str) or value not in VISIBILITIES:
        raise validation("visibility must be public or private")
    return value


def required_string(body: dict, name: str) -> str:
    if name not in body:
        raise validation(f"{name} is required")
    value = body[name]
    if not isinstance(value, str):
        raise malformed(f"{name} must be a string")
    return value


def optional_boolean(body: dict, name: str, default: bool) -> bool:
    if name not in body:
        return default
    value = body[name]
    if not isinstance(value, bool):
        raise malformed(f"{name} must be true or false")
    return value


def required_string_list(body: dict, name: str) -> list:
    if name not in body:
        raise validation(f"{name} is required")
    value = body[name]
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise malformed(f"{name} must be an array of strings")
    return value


def is_handle(value) -> bool:
    return isinstance(value, str) and HANDLE_PATTERN.fullmatch(value) is not None


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+")


def is_email(value) -> bool:
    """The form local@domain (section 6)."""
    return isinstance(value, str) and _EMAIL.fullmatch(value) is not None


def email_key(email: str) -> str:
    """Emails are compared case-insensitively."""
    return email.lower()


def derive_handle(email: str) -> str:
    """Section 4: lowercase the local part, map every char outside [a-z0-9_] to _, cut to 20."""
    local = email.rsplit("@", 1)[0].lower()
    return "".join(c if c in _HANDLE_CHARS else "_" for c in local)[:20]


_HANDLE_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")


def is_id(value) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= MAX_ID


_DIGITS = re.compile(r"[0-9]+")


def query_int(query: dict, name: str, default: int, minimum: int, maximum: int | None) -> int:
    """Integer query parameters are plain decimal digits (section 5)."""
    if name not in query:
        return default
    raw = query[name]
    if _DIGITS.fullmatch(raw) is None:
        raise validation(f"{name} must be plain decimal digits")
    digits = raw.lstrip("0") or "0"
    value = int(digits) if len(digits) <= 18 else 10 ** 18
    if value < minimum or (maximum is not None and value > maximum):
        raise validation(f"{name} is out of range")
    return value


def query_choice(query: dict, name: str, choices: tuple) -> str | None:
    if name not in query:
        return None
    value = query[name]
    if value not in choices:
        raise validation(f"{name} must be one of {', '.join(choices)}")
    return value
