"""Item 14: notes are stored and returned verbatim."""
import json

import pytest

from client import expect

NOTES = ["  padded  ", "<b>&amp;</b>", "line\nbreak\ttab", "é vs é",
         "\U0001f355\U0001f1ea\U0001f1fa\U0001f468‍\U0001f469‍\U0001f467",
         "中文 🎉", "\\ \" '", ""]


def _raw_note(resp) -> bytes:
    """The note re-encoded from the response bytes, to compare byte for byte."""
    return json.loads(resp.body)["note"].encode("utf-8")


@pytest.mark.parametrize("note", NOTES)
def test_payment_note_verbatim(world, note):
    resp = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1, "note": note}),
                  201)
    assert _raw_note(resp) == note.encode("utf-8")
    [feed] = world.ben.get("/activity").json()["payments"]
    assert feed["note"].encode("utf-8") == note.encode("utf-8")


@pytest.mark.parametrize("note", NOTES)
def test_request_note_verbatim(world, note):
    resp = expect(world.ann.write("/requests", {"payer_handle": "ben", "amount": 1,
                                                "note": note}), 201)
    assert _raw_note(resp) == note.encode("utf-8")
    [listed] = world.ben.get("/requests").json()["requests"]
    assert listed["note"] == note
    paid = expect(world.ben.write(f"/requests/{listed['request_id']}/pay", {}), 201).json()
    assert paid["note"] == note


@pytest.mark.parametrize("note", NOTES)
def test_split_note_verbatim(world, note):
    body = expect(world.ann.write("/splits", {"amount": 10, "participant_handles":
                                              ["ann", "ben"], "note": note}), 201).json()
    assert body["note"] == note
    assert body["requests"][0]["note"] == note
