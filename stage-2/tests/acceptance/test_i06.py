"""Item 6: the error envelope and malformed / missing / wrong-typed bodies."""
import pytest

from client import expect, request


def test_envelope_on_4xx(world):
    for resp in (request("GET", "/me"), request("GET", "/nope"),
                 world.ann.write("/payments", {"to_handle": "ben", "amount": 10 ** 7})):
        error = resp.json()["error"]
        assert set(error) >= {"code", "message"}
        assert isinstance(error["message"], str)


@pytest.mark.parametrize("raw", [b"{", b"not json", b'{"amount": NaN}', b"\xff\xfe",
                                 b"[1, 2]", b'"text"', b"42", b"null", b""])
def test_unparseable_or_non_object_body_is_400(world, raw):
    expect(world.ann.write("/payments", raw=raw), 400, "malformed_request")
    expect(world.ann.write("/requests", raw=raw), 400, "malformed_request")
    expect(request("POST", "/auth/signup", raw=raw), 400, "malformed_request")
    expect(request("POST", "/_test/reset", raw=raw), 400, "malformed_request")


@pytest.mark.parametrize("path,body", [
    ("/payments", {"to_handle": 7, "amount": 5}),
    ("/requests", {"payer_handle": ["ben"], "amount": 5}),
    ("/splits", {"amount": 5, "participant_handles": "ben"}),
    ("/splits", {"amount": 5, "participant_handles": ["ben", 3]}),
])
def test_wrong_json_type_is_400(world, path, body):
    expect(world.ann.write(path, body), 400, "malformed_request")


def test_wrong_type_on_auth_fields_is_400():
    expect(request("POST", "/auth/signup", {"email": 1, "password": "long enough",
                                            "display_name": "X"}), 400, "malformed_request")
    expect(request("POST", "/auth/login", {"email": "a@b", "password": 12345678}),
           400, "malformed_request")


@pytest.mark.parametrize("path,body", [
    ("/payments", {"amount": 5}),
    ("/payments", {"to_handle": "ben"}),
    ("/requests", {"amount": 5}),
    ("/splits", {"amount": 5}),
    ("/splits", {"participant_handles": ["ben"]}),
])
def test_missing_required_field_is_422(world, path, body):
    expect(world.ann.write(path, body), 422, "validation_failed")


def test_missing_auth_fields_are_422():
    expect(request("POST", "/auth/signup", {"email": "x@y.z", "password": "long enough"}),
           422, "validation_failed")
    expect(request("POST", "/auth/login", {"email": "x@y.z"}), 422, "validation_failed")
