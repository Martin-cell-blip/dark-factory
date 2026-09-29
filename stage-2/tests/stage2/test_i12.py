"""Item 12: GET /authorizations filters, order and paging."""
from urllib.parse import quote

import pytest

from client import expect
from holdfx import authorize, capture


def _ids(client, query=""):
    return [a["authorization_id"] for a in
            expect(client.get(f"/authorizations{query}"), 200).json()["authorizations"]]


@pytest.fixture
def mix(world):
    """Ann pays into four holds and receives one; Ben and Cat share one Ann cannot see."""
    made = [authorize(world.ann, "ben", 10)["authorization_id"],
            authorize(world.ben, "ann", 20)["authorization_id"],
            authorize(world.ann, "cat", 30)["authorization_id"],
            authorize(world.ann, "ben", 40)["authorization_id"]]
    authorize(world.ben, "cat", 50)
    capture(world.ben, made[0])
    expect(world.ann.post(f"/authorizations/{made[2]}/void"), 200)
    return made


def test_only_own_newest_first(world, mix):
    assert _ids(world.ann) == list(reversed(mix))
    body = expect(world.ann.get("/authorizations"), 200).json()
    stamps = [a["created_at"] for a in body["authorizations"]]
    assert stamps == sorted(stamps, reverse=True) and body["has_more"] is False


def test_direction_and_status(world, mix):
    assert _ids(world.ann, "?direction=outgoing") == [mix[3], mix[2], mix[0]]
    assert _ids(world.ann, "?direction=incoming") == [mix[1]]
    assert _ids(world.ann, "?status=open") == [mix[3], mix[1]]
    assert _ids(world.ann, "?status=captured") == [mix[0]]
    assert _ids(world.ann, "?status=voided&direction=outgoing") == [mix[2]]
    assert _ids(world.ann, "?status=expired") == []


@pytest.mark.parametrize("query", ["direction=sideways", "direction=", "status=pending",
                                   "status=OPEN", "limit=0", "limit=201", "limit=1e1",
                                   "limit=4.0", "limit=%2B4", "offset=-1", "offset=x"])
def test_invalid_query_is_422(world, query):
    expect(world.ann.get(f"/authorizations?{query}"), 422, "validation_failed")


def test_paging(world, mix):
    page = expect(world.ann.get("/authorizations?limit=3"), 200).json()
    assert len(page["authorizations"]) == 3 and page["has_more"] is True
    page = expect(world.ann.get("/authorizations?limit=3&offset=1"), 200).json()
    assert len(page["authorizations"]) == 3 and page["has_more"] is False
    assert _ids(world.ann, "?limit=1&offset=2") == [mix[1]]
    assert _ids(world.ann, f"?offset={quote('99999999999999999999')}") == []


def test_json_without_html_accept(world):
    resp = expect(world.ann.get("/authorizations"), 200)
    assert resp.headers["content-type"].startswith("application/json")
    expect(world.ann.get("/authorizations", headers={"Accept": "application/json"}), 200)
