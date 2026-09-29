"""Item 29: POST /_test/import."""
import copy

import pytest

import seed
from client import expect, login, new_key, request


def _export():
    return expect(request("GET", "/_test/export"), 200).json()


def _import(document):
    return request("POST", "/_test/import", document, timeout=15)


@pytest.fixture
def source(reset):
    """A lived-in state: signup, payments, a paid request, a split, a settlement."""
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann = login("ann@pocket.test", seed.PASSWORD)
    ben = login("ben@pocket.test", seed.PASSWORD)
    signup = expect(request("POST", "/auth/signup", {"email": "new@pocket.test",
                                                     "password": "brand new pw",
                                                     "display_name": "New"}), 201).json()
    pay_key = new_key()
    payment = expect(ann.post("/payments", {"to_handle": "ben", "amount": 70,
                                            "visibility": "private"}, key=pay_key), 201).json()
    rq = expect(ben.write("/requests", {"payer_handle": "ann", "amount": 30}), 201).json()
    paid = expect(ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    expect(ann.write("/splits", {"amount": 9, "participant_handles": ["ann", "ben", "cat"]}), 201)
    settle_key = new_key()
    settle_body = {"transfers": [{"from_handle": "ben", "to_handle": "cat", "amount": 5}]}
    settlement = expect(ann.post("/settlements", settle_body, key=settle_key), 201).json()
    failed_key = new_key()
    expect(ben.post("/payments", {"to_handle": "cat", "amount": 10 ** 8}, key=failed_key), 409)
    return locals()


def test_round_trip_preserves_everything(source, reset):
    s = source
    document = _export()
    views = {name: (c.get("/me").json(), c.get("/activity").json(), c.get("/requests").json())
             for name, c in (("ann", s["ann"]), ("ben", s["ben"]))}
    reset(seed.fixture(users=[seed.user("other", 1)]))
    expect(_import(document), 204)
    for name, c in (("ann", s["ann"]), ("ben", s["ben"])):
        assert (c.get("/me").json(), c.get("/activity").json(),
                c.get("/requests").json()) == views[name]
    expect(request("POST", "/auth/login", {"email": "new@pocket.test",
                                           "password": "brand new pw"}), 200)
    expect(request("GET", "/me", token=s["signup"]["token"]), 200)
    replay = expect(s["ann"].post("/payments", {"to_handle": "ben", "amount": 70,
                                                "visibility": "private"}, key=s["pay_key"]), 200)
    assert replay.json() == s["payment"]
    settled = expect(s["ann"].post("/settlements", s["settle_body"], key=s["settle_key"]), 200)
    assert settled.json() == s["settlement"]
    expect(s["ann"].write(f"/requests/{s['rq']['request_id']}/pay", {}), 409,
           "request_not_pending")
    expect(s["ben"].post("/payments", {"to_handle": "cat", "amount": 1},
                         key=s["failed_key"]), 201)
    expect(s["ann"].write("/settlements", s["settle_body"]), 201)
    assert _export()["state"] != document["state"]


def test_import_is_replacement_and_repeatable(source):
    document = _export()
    for _ in range(3):
        expect(_import(document), 204)
    assert _export() == document
    ann = source["ann"]
    assert len(ann.get("/activity").json()["payments"]) == 3


def test_import_removes_previous_destination_data(source, reset):
    document = _export()
    reset(seed.fixture(users=[seed.user("gone", 10)]))
    gone = login("gone@pocket.test", seed.PASSWORD)
    expect(_import(document), 204)
    expect(gone.get("/me"), 401, "unauthenticated")
    expect(request("POST", "/auth/login", {"email": "gone@pocket.test",
                                           "password": seed.PASSWORD}), 401)


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("track"),
    lambda d: d.pop("format_version"),
    lambda d: d.pop("state"),
    lambda d: d.update(track="tablekeeper"),
    lambda d: d.update(format_version=2),
    lambda d: d.update(format_version="1"),
    lambda d: d.update(state="nope"),
    lambda d: d.update(state={}),
    lambda d: d["state"]["users"][0].update(balance=-5),
    lambda d: d["state"].update(payments="many"),
])
def test_invalid_import_is_422_and_changes_nothing(source, mutate):
    document = _export()
    broken = copy.deepcopy(document)
    mutate(broken)
    expect(_import(broken), 422, "validation_failed")
    assert _export() == document


def test_invalid_json_is_400(source):
    expect(request("POST", "/_test/import", raw=b"{nope"), 400, "malformed_request")
    expect(request("POST", "/_test/import", raw=b"[]"), 400, "malformed_request")


def test_reset_clears_imported_state(source, reset):
    document = _export()
    expect(_import(document), 204)
    reset(seed.fixture())
    expect(source["ann"].get("/me"), 401)
    expect(request("GET", "/me", token=source["signup"]["token"]), 401)
