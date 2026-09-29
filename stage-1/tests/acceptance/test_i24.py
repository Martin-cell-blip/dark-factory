"""Item 24: POST /splits."""
from client import expect


def test_split_shape_and_requests(world):
    body = expect(world.ann.write("/splits", {"amount": 3000, "note": "dinner",
                                              "participant_handles": ["cat", "ann", "ben"]}),
                  201).json()
    assert set(body) == {"split_id", "amount", "currency", "note", "shares", "requests",
                         "created_at"}
    assert body["amount"] == 3000 and body["currency"] == "EUR" and body["note"] == "dinner"
    assert body["shares"] == [{"handle": "cat", "amount": 1000},
                              {"handle": "ann", "amount": 1000},
                              {"handle": "ben", "amount": 1000}]
    assert [r["payer_handle"] for r in body["requests"]] == ["cat", "ben"]
    for req in body["requests"]:
        assert req["requester_handle"] == "ann" and req["requester_id"] == "u_ann"
        assert req["status"] == "pending" and req["amount"] == 1000
        assert req["payment_id"] is None and req["note"] == "dinner"
    listed = {r["request_id"] for r in world.cat.get("/requests").json()["requests"]}
    assert body["requests"][0]["request_id"] in listed


def test_caller_may_be_omitted(world):
    body = expect(world.ann.write("/splits", {"amount": 10,
                                              "participant_handles": ["ben", "cat"]}),
                  201).json()
    assert [s["amount"] for s in body["shares"]] == [5, 5]
    assert [r["payer_handle"] for r in body["requests"]] == ["ben", "cat"]


def test_zero_share_still_gets_a_request(world):
    body = expect(world.ann.write("/splits", {"amount": 1, "participant_handles":
                                              ["ann", "ben", "cat"]}), 201).json()
    assert [s["amount"] for s in body["shares"]] == [1, 0, 0]
    assert [(r["payer_handle"], r["amount"]) for r in body["requests"]] == [("ben", 0),
                                                                          ("cat", 0)]


def test_caller_only_split(world):
    body = expect(world.ann.write("/splits", {"amount": 50, "participant_handles": ["ann"]}),
                  201).json()
    assert body["shares"] == [{"handle": "ann", "amount": 50}] and body["requests"] == []


def test_no_balance_checked_and_not_a_feed_item(world):
    body = expect(world.cat.write("/splits", {"amount": 1000000000,
                                              "participant_handles": ["ann", "ben"]}),
                  201).json()
    assert sum(s["amount"] for s in body["shares"]) == 1000000000
    for viewer in world.everyone:
        assert viewer.get("/activity").json()["payments"] == []
    assert world.cat.balance() == 500
