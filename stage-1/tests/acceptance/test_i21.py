"""Item 21: POST /requests/{id}/cancel."""
from client import expect


def _ask(world):
    return expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 40}),
                  201).json()["request_id"]


def test_cancel_without_key_and_twice(world):
    rid = _ask(world)
    body = expect(world.ben.post(f"/requests/{rid}/cancel"), 200).json()
    assert body["request_id"] == rid and body["status"] == "cancelled"
    assert expect(world.ben.post(f"/requests/{rid}/cancel"), 200).json()["status"] == "cancelled"


def test_paid_or_declined_is_not_pending(world):
    paid = _ask(world)
    expect(world.ann.write(f"/requests/{paid}/pay", {}), 201)
    expect(world.ben.post(f"/requests/{paid}/cancel"), 409, "request_not_pending")
    declined = _ask(world)
    expect(world.ann.post(f"/requests/{declined}/decline"), 200)
    expect(world.ben.post(f"/requests/{declined}/cancel"), 409, "request_not_pending")


def test_only_the_requester_and_unknown(world):
    rid = _ask(world)
    expect(world.ann.post(f"/requests/{rid}/cancel"), 403, "forbidden")
    expect(world.cat.post(f"/requests/{rid}/cancel"), 403, "forbidden")
    expect(world.ben.post("/requests/rq_nope/cancel"), 404, "not_found")
