"""JSON in and out: strict parsing, canonical comparison form, UTF-8 output.

Parsing and the canonical form run at C speed for ordinary bodies, so fifty 1 MiB bodies
in flight stay within the per-request time limit; the slower paths only run when the raw
bytes show they are needed.
"""
import hashlib
import json
import math
import re

from .errors import malformed

_MAX_INT_DIGITS = 4000
_LONG_INT = re.compile(rb"[0-9]{%d,}" % (_MAX_INT_DIGITS + 1))
_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89abcdefABCDEF]")
_HUGE_TAG = chr(0) + "integer"  # marks an oversized integer in the canonical form


class HugeInt:
    """A JSON integer too long for Python's int(). No field rule accepts it as a number,
    so it fails validation with 422 rather than parsing with 400; its digits are kept
    for replay comparison."""

    def __init__(self, text: str):
        self.text = text


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


def _parse_int(text: str):
    return int(text) if len(text) <= _MAX_INT_DIGITS else HugeInt(text)


def _parse_float(text: str):
    """1000.0 and 1e3 are the integer 1000; other numbers stay floats."""
    value = float(text)
    return int(value) if math.isfinite(value) and value.is_integer() else value


def _check_strings(value) -> None:
    """Reject strings that cannot be written back as UTF-8 (lone surrogates from \\u escapes)."""
    stack = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            item.encode("utf-8")
        elif isinstance(item, dict):
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


def parse(raw: bytes):
    """Parse a request body; anything that is not valid UTF-8 JSON is 400 malformed_request."""
    hooks = {"parse_constant": _reject_constant, "parse_float": _parse_float}
    if _LONG_INT.search(raw):
        hooks["parse_int"] = _parse_int
    try:
        value = json.loads(raw.decode("utf-8"), **hooks)
        if _SURROGATE_ESCAPE.search(raw):
            _check_strings(value)
    except (UnicodeError, ValueError, RecursionError):
        raise malformed("the body is not valid JSON") from None
    return value


def parse_object(raw: bytes) -> dict:
    """Parse a body that must be a JSON object (decision D2: any other JSON value is 400)."""
    value = parse(raw)
    if not isinstance(value, dict):
        raise malformed("the body must be a JSON object")
    return value


def _encode_huge(value):
    if isinstance(value, HugeInt):
        return [_HUGE_TAG, value.text]
    raise TypeError(f"{type(value).__name__} is not JSON")


def canonical(value) -> str:
    """One string per parsed JSON value: key order, whitespace and 1000 / 1000.0 / 1e3 do
    not matter (parse already made integral numbers ints)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                      default=_encode_huge)


def digest(canonical_text: str) -> str:
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def fingerprint(value) -> str:
    """What a replay must match: a digest of the canonical body, small whatever its size."""
    return digest(canonical(value))


def is_fingerprint(text: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", text) is not None


def dumps(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
