"""Item 7: POST /payments/{payment_id}/corrections."""
from datetime import datetime

import pytest

from client import expect, request
from timefx import ago, ahead, correct, pay


def _body(**change):
    return {"expected_revision": 1, "amount": 50, "effective_at": ago(minutes=1),
            "reason": "fix", **change}


def test_correction_shape_and_effect(world):
    payment = pay(world.ann, "ben", 300, visibility="private", note="dinner")
    body = correct(world.ann, payment["payment_id"], 120, payment["created_at"],
                   reason="wrong amount").json()
    assert set(body) == {"payment_id", "revision", "amount", "effective_at", "recorded_at",
                         "reason", "correction_batch_id"}
    assert body["payment_id"] == payment["payment_id"] and body["revision"] == 2
    assert body["amount"] == 120 and body["effective_at"] == payment["created_at"]
    assert body["reason"] == "wrong amount"
    assert datetime.fromisoformat(body["recorded_at"]) > datetime.fromisoformat(payment["created_at"])
    assert world.ann.balance() == 9880 and world.ben.balance() == 2620
    [item] = expect(world.ben.get("/activity"), 200).json()["payments"]
    assert item["from_handle"] == "ann" and item["to_handle"] == "ben"
    assert item["visibility"] == "private" and item["note"] == "dinner"


def test_zero_reverses_the_payment(world):
    payment = pay(world.ann, "ben", 300)
    correct(world.ann, payment["payment_id"], 0, payment["created_at"])
    assert world.ann.balance() == 10000 and world.ben.balance() == 2500


def test_recorded_times_strictly_increase(world):
    payment = pay(world.ann, "ben", 300)
    stamps = [payment["created_at"]]
    for revision, amount in ((1, 200), (2, 250), (3, 0), (4, 300)):
        body = correct(world.ann, payment["payment_id"], amount, ago(seconds=1),
                       expected_revision=revision).json()
        stamps.append(body["recorded_at"])
    moments = [datetime.fromisoformat(s) for s in stamps]
    assert moments == sorted(moments) and len(set(moments)) == len(moments)


@pytest.mark.parametrize("change", [
    {"expected_revision": 0}, {"expected_revision": -1}, {"expected_revision": 1.5},
    {"amount": -1}, {"amount": 1000000001}, {"amount": 2.5}, {"amount": "5"}, {"amount": None},
    {"amount": True}, {"reason": ""}, {"reason": "x" * 201},
    {"effective_at": "2026-09-24"}, {"effective_at": "2026-09-24T10:00:00"},
    {"effective_at": ""}, {"effective_at": ahead(hours=1)},
])
def test_invalid_input_is_422(world, change):
    payment = pay(world.ann, "ben", 300)
    expect(world.ann.write(f"/payments/{payment['payment_id']}/corrections", _body(**change)),
           422, "validation_failed")
    assert world.ann.balance() == 9700


@pytest.mark.parametrize("missing", ["expected_revision", "amount", "effective_at", "reason"])
def test_every_field_is_required(world, missing):
    payment = pay(world.ann, "ben", 300)
    body = _body()
    body.pop(missing)
    expect(world.ann.write(f"/payments/{payment['payment_id']}/corrections", body),
           422, "validation_failed")


@pytest.mark.parametrize("change", [{"expected_revision": "1"}, {"reason": 5},
                                    {"effective_at": 17}, {"expected_revision": None}])
def test_wrong_json_types_are_400(world, change):
    payment = pay(world.ann, "ben", 300)
    expect(world.ann.write(f"/payments/{payment['payment_id']}/corrections", _body(**change)),
           400, "malformed_request")


def test_reason_counts_code_points(world):
    payment = pay(world.ann, "ben", 300)
    correct(world.ann, payment["payment_id"], 10, ago(seconds=1), reason="\U0001F600" * 200)


def test_who_may_correct(world):
    payment = pay(world.ann, "ben", 300)
    path = f"/payments/{payment['payment_id']}/corrections"
    expect(world.ben.write(path, _body()), 403, "forbidden")
    expect(world.cat.write(path, _body()), 403, "forbidden")
    expect(world.ann.write("/payments/p_nope/corrections", _body()), 404, "not_found")
    expect(request("POST", path, _body(), key="k"), 401, "unauthenticated")
    assert world.ann.balance() == 9700
