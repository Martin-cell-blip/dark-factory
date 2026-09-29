"""Password storage with scrypt (section 6). Only the derived hash is ever stored."""
import base64
import hashlib
import hmac
import os

_N, _R, _P, _LEN = 2 ** 12, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                          maxmem=_MAXMEM, dklen=_LEN)


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = _derive(password, salt, _N, _R, _P)
    return "scrypt${}${}${}${}${}".format(
        _N, _R, _P, base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        actual = _derive(password, base64.b64decode(salt), int(n), int(r), int(p))
        return hmac.compare_digest(actual, base64.b64decode(digest))
    except (ValueError, TypeError):
        return False


def is_hash(stored) -> bool:
    """A structurally valid stored hash, as accepted from an import."""
    if not isinstance(stored, str):
        return False
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != "scrypt":
        return False
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        base64.b64decode(parts[4], validate=True)
        base64.b64decode(parts[5], validate=True)
    except ValueError:
        return False
    return n > 1 and n & (n - 1) == 0 and n <= 2 ** 20 and 1 <= r <= 32 and 1 <= p <= 16
