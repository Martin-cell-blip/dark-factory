"""Item 28: GET /_test/export."""
from client import expect, request


def test_export_envelope(world):
    body = expect(request("GET", "/_test/export"), 200).json()
    assert body["track"] == "pocketful" and body["format_version"] == 1
    assert isinstance(body["state"], dict)


def test_snapshot_unchanged_by_later_writes(world):
    before = expect(request("GET", "/_test/export"), 200).body
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 5}), 201)
    after = expect(request("GET", "/_test/export"), 200).body
    assert before != after
    expect(request("POST", "/_test/import", raw=before), 204)
    assert world.ann.balance() == 10000 and world.ben.balance() == 2500
    assert world.ann.get("/activity").json()["payments"] == []
