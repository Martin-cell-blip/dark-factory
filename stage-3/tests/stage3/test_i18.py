"""Item 18: historical holds."""
import time

import seed
from client import expect
from timefx import ago, ahead, at, me_at, pay, signed_in


def _server_now(client) -> str:
    """The service's own clock: the created_at of a 1-unit payment made now."""
    return pay(client, "ben", 1)["created_at"]


def _hold(client, to_handle, amount):
    return expect(client.write("/authorizations", {"to_handle": to_handle, "amount": amount}),
                  201).json()


def _find(client, authorization_id):
    for item in expect(client.get("/authorizations"), 200).json()["authorizations"]:
        if item["authorization_id"] == authorization_id:
            return item
    raise AssertionError(authorization_id)


def _view(client, **params):
    body = me_at(client, **params)
    assert body["balance"] == body["total"]
    assert body["available"] == body["total"] - body["held"]
    return body["total"], body["held"], body["available"]


def test_a_hold_through_its_lifecycle(world):
    before = ago(seconds=1)
    time.sleep(0.02)
    hold = _hold(world.ann, "ben", 2000)
    assert hold["closed_at"] is None
    first = expect(world.ben.write(f"/authorizations/{hold['authorization_id']}/capture",
                                   {"amount": 500, "final": False}), 201).json()
    voided = expect(world.ann.post(f"/authorizations/{hold['authorization_id']}/void"), 200).json()
    assert voided["closed_at"] is not None
    assert _view(world.ann, as_of=before) == (10000, 0, 10000)
    assert _view(world.ann, as_of=hold["created_at"]) == (10000, 2000, 8000)
    assert _view(world.ann, as_of=first["created_at"]) == (9500, 1500, 8000)
    assert _view(world.ann, as_of=voided["closed_at"]) == (9500, 0, 9500)
    unknown_void = at(voided["closed_at"], microseconds=-1)
    assert _view(world.ann, as_of=ahead(minutes=1), known_at=unknown_void) == (9500, 1500, 8000), \
        "the void is not yet known, so the hold still stands"
    assert _view(world.ann, as_of=ahead(hours=1), known_at=unknown_void) == (9500, 0, 9500), \
        "beyond its deadline an open hold has expired"
    assert _view(world.ann, known_at=at(hold["created_at"], microseconds=-1))[1] == 0
    assert _view(world.ann) == (9500, 0, 9500)


def test_final_capture_releases_at_its_time(world):
    hold = _hold(world.ann, "ben", 2000)
    payment = expect(world.ben.write(f"/authorizations/{hold['authorization_id']}/capture",
                                     {"amount": 700}), 201).json()
    closed = _find(world.ann, hold["authorization_id"])
    assert closed["status"] == "captured" and closed["closed_at"] == payment["created_at"]
    assert _view(world.ann, as_of=payment["created_at"]) == (9300, 0, 9300)
    assert _view(world.ann, as_of=at(payment["created_at"], microseconds=-1)) == (10000, 2000, 8000)


def test_expiry_at_the_deadline(reset):
    reset(seed.fixture(authorization_ttl_seconds=1))
    [ann] = signed_in("ann")
    hold = _hold(ann, "ben", 3000)
    assert _view(ann, as_of=at(hold["expires_at"], microseconds=-1)) == (10000, 3000, 7000)
    assert _view(ann, as_of=hold["expires_at"]) == (10000, 0, 10000)
    time.sleep(1.2)
    expired = _find(ann, hold["authorization_id"])
    assert expired["status"] == "expired" and expired["closed_at"] == hold["expires_at"]
    assert _view(ann, as_of=at(hold["expires_at"], microseconds=-1),
                 known_at=hold["created_at"]) == (10000, 3000, 7000)


def test_seeded_open_holds_count_from_reset(reset):
    reset(seed.fixture(authorizations=[
        {"id": "a_seed", "from_user_id": "u_ann", "to_user_id": "u_ben", "amount": 1000,
         "status": "open", "expires_at": ahead(hours=2)},
        {"id": "a_dated", "from_user_id": "u_ann", "to_user_id": "u_cat", "amount": 500,
         "status": "open", "expires_at": ahead(hours=2), "created_at": ago(hours=3)},
        {"id": "a_done", "from_user_id": "u_ann", "to_user_id": "u_cat", "amount": 700,
         "status": "voided", "expires_at": ahead(hours=2)}]))
    [ann] = signed_in("ann")
    assert _view(ann) == (10000, 1500, 8500)
    assert _view(ann, as_of=ago(hours=1)) == (10000, 500, 9500)
    assert _view(ann, as_of=ago(hours=4)) == (10000, 0, 10000)
    assert _find(ann, "a_seed")["closed_at"] is None
    assert _find(ann, "a_done")["closed_at"] is not None


def test_closed_holds_that_arrive_by_seed(reset):
    """S3-D8: capture -> latest capture payment, expired -> expires_at, voided -> reset time;
    a seeded closed hold holds nothing at any instant."""
    deadline = ago(hours=2)
    reset(seed.fixture())
    before = _server_now(signed_in("ann")[0])
    reset(seed.fixture(
        payments=[{"id": "p_cap", "from_user_id": "u_ann", "to_user_id": "u_ben", "amount": 300,
                   "created_at": ago(hours=4), "authorization_id": "a_cap"}],
        authorizations=[
            {"id": "a_cap", "from_user_id": "u_ann", "to_user_id": "u_ben", "amount": 500,
             "status": "captured", "expires_at": ahead(hours=1), "created_at": ago(hours=5),
             "captured_amount": 300, "payment_ids": ["p_cap"]},
            {"id": "a_exp", "from_user_id": "u_ann", "to_user_id": "u_cat", "amount": 400,
             "status": "expired", "expires_at": deadline, "created_at": ago(hours=6)},
            {"id": "a_void", "from_user_id": "u_ann", "to_user_id": "u_cat", "amount": 700,
             "status": "voided", "expires_at": ahead(hours=2), "created_at": ago(hours=6)}]))
    [ann] = signed_in("ann")
    after = _server_now(ann)
    capture = next(p for p in expect(ann.get("/activity"), 200).json()["payments"]
                   if p["payment_id"] == "p_cap")
    assert _find(ann, "a_cap")["closed_at"] == capture["created_at"]
    assert _find(ann, "a_exp")["closed_at"] == deadline
    voided = _find(ann, "a_void")["closed_at"]
    assert before <= voided <= after, "reset time, read on the service's own clock"
    for hours in (7, 5.5, 4.5, 3, 1):
        assert _view(ann, as_of=ago(hours=hours))[1] == 0
