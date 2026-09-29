"""JSON in and out: strict parsing, canonical comparison form, UTF-8 output."""
import json
import math

from .errors import malformed


def _reject_constant(name):
    raise ValueError(f"{name} is not valid JSON")


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


_MAX_INT_DIGITS = 4000
_HUGE_TAG = chr(0) + "integer"  # marks an oversized integer in the canonical form


class HugeInt(float):
    """A JSON integer too long for Python's int(): an infinite number to the range rules
    (so they answer 422, not a parse error), its digits kept for replay comparison."""

    def __new__(cls, text: str):
        value = super().__new__(cls, "-inf" if text.startswith("-") else "inf")
        value.text = text
        return value


def _parse_int(text: str):
    return int(text) if len(text) <= _MAX_INT_DIGITS else HugeInt(text)


def parse(raw: bytes):
    """Parse a request body; anything that is not valid UTF-8 JSON is 400 malformed_request."""
    try:
        value = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant,
                           parse_int=_parse_int)
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


def _normalise(value):
    if isinstance(value, HugeInt):
        return [_HUGE_TAG, value.text]
    if isinstance(value, bool) or value is None or isinstance(value, (int, str)):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else value
    if isinstance(value, dict):
        return {k: _normalise(v) for k, v in value.items()}
    return [_normalise(v) for v in value]


def canonical(value) -> str:
    """One string per JSON value: key order, whitespace and 1000 / 1000.0 / 1e3 do not matter."""
    return json.dumps(_normalise(value), sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def dumps(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
