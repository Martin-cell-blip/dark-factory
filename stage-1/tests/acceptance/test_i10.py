"""Item 10: passwords never stored in clear."""
import json
import re

import seed
from client import expect, request


def test_export_holds_no_clear_password(world):
    expect(request("POST", "/auth/signup", {"email": "sec@example.com",
                                            "password": "a very secret phrase",
                                            "display_name": "Sec"}), 201)
    text = json.dumps(expect(request("GET", "/_test/export"), 200).json())
    assert seed.PASSWORD not in text
    assert "a very secret phrase" not in text


def test_users_sharing_a_password_get_different_hashes(reset):
    """Every user has their own random salt, seeded users included."""
    reset(seed.fixture())
    state = json.dumps(expect(request("GET", "/_test/export"), 200).json()["state"])
    hashes = re.findall(r'"(scrypt\$[^"]+)"', state)
    assert len(hashes) == 3
    assert len(set(hashes)) == 3
