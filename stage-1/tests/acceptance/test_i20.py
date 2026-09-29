"""Item 20: POST /requests/{id}/decline."""
from client import expect


def _ask(world):
    return expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 40}),
                  201).json()["request_id"]


def test_decline_without_key_and_twice(world):
    rid = _ask(world)
    body = expect(world.ann.post(f"/requests/{rid}/decline"), 200).json()
    assert body["request_id"] == rid and body["status"] == "declined"
    again = expect(world.ann.post(f"/requests/{rid}/decline"), 200).json()
    assert again["status"] == "declined"
    assert world.ann.balance() == 10000


def test_paid_or_cancelled_is_not_pending(world):
    paid = _ask(world)
    expect(world.ann.write(f"/requests/{paid}/pay", {}), 201)
    expect(world.ann.post(f"/requests/{paid}/decline"), 409, "request_not_pending")
    cancelled = _ask(world)
    expect(world.ben.post(f"/requests/{cancelled}/cancel"), 200)
    expect(world.ann.post(f"/requests/{cancelled}/decline"), 409, "request_not_pending")


def test_only_the_payer_and_unknown(world):
    rid = _ask(world)
    expect(world.ben.post(f"/requests/{rid}/decline"), 403, "forbidden")
    expect(world.cat.post(f"/requests/{rid}/decline"), 403, "forbidden")
    expect(world.ann.post("/requests/rq_nope/decline"), 404, "not_found")
