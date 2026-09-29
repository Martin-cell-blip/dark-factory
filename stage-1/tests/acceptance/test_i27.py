"""Item 27: GET /activity and the feed contract."""
from client import expect


def _ids(client, query=""):
    return [p["payment_id"] for p in expect(client.get(f"/activity{query}"), 200)
            .json()["payments"]]


def test_visibility_rule(world):
    public = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1}),
                    201).json()["payment_id"]
    private = expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 2,
                                                   "visibility": "private"}),
                     201).json()["payment_id"]
    assert _ids(world.ann) == [private, public]
    assert _ids(world.ben) == [private, public]
    assert _ids(world.cat) == [public]


def test_requests_and_splits_never_appear(world):
    expect(world.ann.write("/requests", {"payer_handle": "ben", "amount": 1}), 201)
    expect(world.ann.write("/splits", {"amount": 9, "participant_handles": ["ann", "cat"]}), 201)
    rq = expect(world.cat.write("/requests", {"payer_handle": "ben", "amount": 3}), 201).json()
    for viewer in world.everyone:
        assert _ids(viewer) == []
    paid = expect(world.ben.write(f"/requests/{rq['request_id']}/pay",
                                  {"visibility": "private"}), 201).json()
    assert _ids(world.cat) == [paid["payment_id"]]
    assert _ids(world.ann) == []


def test_newest_first_and_paging(world):
    made = [expect(world.ann.write("/payments", {"to_handle": "ben", "amount": i + 1}),
                   201).json() for i in range(5)]
    newest_first = [p["payment_id"] for p in reversed(made)]
    assert _ids(world.cat) == newest_first
    page = world.cat.get("/activity?limit=2&offset=1").json()
    assert [p["payment_id"] for p in page["payments"]] == newest_first[1:3]
    assert page["has_more"] is True
    page = world.cat.get("/activity?limit=2&offset=3").json()
    assert page["has_more"] is False and len(page["payments"]) == 2
    stamps = [p["created_at"] for p in world.cat.get("/activity").json()["payments"]]
    assert stamps == sorted(stamps, reverse=True)
