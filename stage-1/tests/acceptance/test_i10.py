"""Item 10: passwords never stored in clear."""
import json

import seed
from client import expect, request


def test_export_holds_no_clear_password(world):
    expect(request("POST", "/auth/signup", {"email": "sec@example.com",
                                            "password": "a very secret phrase",
                                            "display_name": "Sec"}), 201)
    text = json.dumps(expect(request("GET", "/_test/export"), 200).json())
    assert seed.PASSWORD not in text
    assert "a very secret phrase" not in text
