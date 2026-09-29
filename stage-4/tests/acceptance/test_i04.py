"""Item 4: content type, RFC 3339 timestamps, unknown fields and parameters, id length."""
import re

from client import expect, request

RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


def _json_type(resp):
    assert resp.headers["content-type"].replace(" ", "").lower() == \
        "application/json;charset=utf-8", resp.headers


def test_content_type_on_success_and_error(world):
    _json_type(request("GET", "/health"))
    _json_type(world.ann.get("/me"))
    _json_type(request("GET", "/me"))
    _json_type(request("GET", "/nowhere"))


def test_timestamps_and_ids(world):
    payment = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 5}), 201).json()
    req = expect(world.ann.write("/requests", {"payer_handle": "ben", "amount": 5}), 201).json()
    split = expect(world.ann.write("/splits", {"amount": 9, "participant_handles":
                                               ["ann", "ben"]}), 201).json()
    for stamp in (payment["created_at"], req["created_at"], split["created_at"]):
        assert RFC3339.match(stamp), stamp
    for value in (payment["payment_id"], payment["from_user_id"], req["request_id"],
                  split["split_id"], split["requests"][0]["request_id"]):
        assert isinstance(value, str) and 0 < len(value) <= 64


def test_unknown_body_fields_and_query_parameters_are_ignored(world):
    body = {"to_handle": "ben", "amount": 5, "flavour": "mint", "nested": {"a": [1]}}
    expect(world.ann.write("/payments", body), 201)
    expect(world.ann.get("/activity?colour=blue&limit=5"), 200)
    expect(world.ann.get("/requests?sort=weird"), 200)
    expect(world.ann.get("/me?x=1"), 200)
