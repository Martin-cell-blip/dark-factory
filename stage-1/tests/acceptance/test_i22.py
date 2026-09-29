"""Item 22: GET /requests filters, order and paging."""
import pytest

from client import expect


def _ids(resp):
    return [r["request_id"] for r in expect(resp, 200).json()["requests"]]


@pytest.fixture
def mix(world):
    """Four requests touching Ann in creation order, plus one Ann is not party to."""
    made = []
    for client, handle in ((world.ben, "ann"), (world.ann, "ben"), (world.cat, "ann"),
                           (world.ann, "cat")):
        made.append(expect(client.write("/requests", {"payer_handle": handle, "amount": 5}),
                           201).json()["request_id"])
    expect(world.ben.write("/requests", {"payer_handle": "cat", "amount": 5}), 201)
    expect(world.ann.post(f"/requests/{made[0]}/decline"), 200)
    return made


def test_only_own_requests_newest_first(world, mix):
    assert _ids(world.ann.get("/requests")) == list(reversed(mix))
    body = world.ann.get("/requests").json()
    assert body["has_more"] is False
    stamps = [r["created_at"] for r in body["requests"]]
    assert stamps == sorted(stamps, reverse=True)


def test_direction_and_status(world, mix):
    assert _ids(world.ann.get("/requests?direction=incoming")) == [mix[2], mix[0]]
    assert _ids(world.ann.get("/requests?direction=outgoing")) == [mix[3], mix[1]]
    assert _ids(world.ann.get("/requests?status=declined")) == [mix[0]]
    assert _ids(world.ann.get("/requests?direction=incoming&status=pending")) == [mix[2]]
    assert _ids(world.ann.get("/requests?status=paid")) == []
    assert _ids(world.ann.get("/requests?status=cancelled")) == []


@pytest.mark.parametrize("query", ["direction=sideways", "direction=", "status=open",
                                   "status=PENDING", "status="])
def test_unknown_filter_values_are_422(world, query):
    expect(world.ann.get(f"/requests?{query}"), 422, "validation_failed")


def test_limit_offset_has_more(world, mix):
    page = world.ann.get("/requests?limit=3").json()
    assert len(page["requests"]) == 3 and page["has_more"] is True
    page = world.ann.get("/requests?limit=3&offset=1").json()
    assert len(page["requests"]) == 3 and page["has_more"] is False
    page = world.ann.get("/requests?limit=4").json()
    assert len(page["requests"]) == 4 and page["has_more"] is False
    page = world.ann.get("/requests?offset=10").json()
    assert page == {"requests": [], "has_more": False}
    assert _ids(world.ann.get("/requests?limit=1&offset=2")) == [mix[1]]
    expect(world.ann.get("/requests?limit=200"), 200)
    expect(world.ann.get("/requests?limit=1&offset=0"), 200)
