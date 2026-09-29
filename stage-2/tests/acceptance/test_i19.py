"""Item 19: POST /requests/{id}/pay."""
from client import expect, new_key


def _ask(world, requester, payer_handle, amount=1200, note="taxi"):
    return expect(requester.write("/requests", {"payer_handle": payer_handle, "amount": amount,
                                                "note": note}), 201).json()


def test_pay_default_public_and_request_becomes_paid(world):
    rq = _ask(world, world.ben, "ann")
    payment = expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201).json()
    assert set(payment) == {"payment_id", "from_user_id", "from_handle", "to_user_id",
                            "to_handle", "amount", "currency", "note", "visibility",
                            "request_id", "settlement_id", "authorization_id",
                            "created_at"}
    assert payment["from_handle"] == "ann" and payment["to_handle"] == "ben"
    assert payment["amount"] == 1200 and payment["note"] == "taxi"
    assert payment["visibility"] == "public" and payment["request_id"] == rq["request_id"]
    assert payment["settlement_id"] is None and payment["authorization_id"] is None
    [listed] = world.ben.get("/requests").json()["requests"]
    assert listed["status"] == "paid" and listed["payment_id"] == payment["payment_id"]
    assert world.ann.balance() == 8800 and world.ben.balance() == 3700


def test_payer_chooses_private(world):
    rq = _ask(world, world.ben, "ann")
    payment = expect(world.ann.write(f"/requests/{rq['request_id']}/pay",
                                     {"visibility": "private"}), 201).json()
    assert payment["visibility"] == "private"
    assert world.cat.get("/activity").json()["payments"] == []
    expect(world.ann.write(f"/requests/{_ask(world, world.ben, 'ann')['request_id']}/pay",
                           {"visibility": "secret"}), 422, "validation_failed")


def test_not_pending(world):
    rq = _ask(world, world.ben, "ann")
    expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 201)
    expect(world.ann.write(f"/requests/{rq['request_id']}/pay", {}), 409, "request_not_pending")
    declined = _ask(world, world.ben, "ann")
    expect(world.ann.post(f"/requests/{declined['request_id']}/decline"), 200)
    expect(world.ann.write(f"/requests/{declined['request_id']}/pay", {}),
           409, "request_not_pending")


def test_short_payer_changes_nothing_then_pays_later(world):
    rq = _ask(world, world.ann, "cat", amount=800)
    expect(world.cat.write(f"/requests/{rq['request_id']}/pay", {}), 409, "insufficient_funds")
    assert world.cat.balance() == 500 and world.ann.balance() == 10000
    [listed] = world.cat.get("/requests").json()["requests"]
    assert listed["status"] == "pending" and listed["payment_id"] is None
    assert world.cat.get("/activity").json()["payments"] == []
    expect(world.ben.write("/payments", {"to_handle": "cat", "amount": 300}), 201)
    expect(world.cat.write(f"/requests/{rq['request_id']}/pay", {}), 201)
    assert world.cat.balance() == 0


def test_only_the_payer(world):
    rq = _ask(world, world.ben, "ann")
    expect(world.ben.write(f"/requests/{rq['request_id']}/pay", {}), 403, "forbidden")
    expect(world.cat.write(f"/requests/{rq['request_id']}/pay", {}), 403, "forbidden")
    expect(world.ann.write("/requests/rq_does_not_exist/pay", {}), 404, "not_found")


def test_replay_returns_original_even_though_paid(world):
    rq = _ask(world, world.ben, "ann")
    key = new_key()
    path = f"/requests/{rq['request_id']}/pay"
    first = expect(world.ann.post(path, {"visibility": "private"}, key=key), 201).json()
    again = expect(world.ann.post(path, {"visibility": "private"}, key=key), 200).json()
    assert again == first
    assert world.ann.balance() == 8800


def test_empty_object_and_explicit_public_are_different_bodies(world):
    rq = _ask(world, world.ben, "ann")
    key = new_key()
    path = f"/requests/{rq['request_id']}/pay"
    expect(world.ann.post(path, {}, key=key), 201)
    expect(world.ann.post(path, {"visibility": "public"}, key=key), 409, "idempotency_key_reuse")
    other = _ask(world, world.ben, "ann")
    key = new_key()
    path = f"/requests/{other['request_id']}/pay"
    expect(world.ann.post(path, {"visibility": "public"}, key=key), 201)
    expect(world.ann.post(path, {}, key=key), 409, "idempotency_key_reuse")
