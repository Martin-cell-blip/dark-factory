"""Item 32 (judged from screenshots by the auditor): the loading and unreachable states sit
inside the normal shell, with navigation and log out, and hold lines keep one time zone
and one wording, as DESIGN.md describes."""
import re

import pytest

import seed
from client import expect
from holdfx import authorize, capture, seeded_hold, sel, signed_in
from ui import ROUTES, log_in

SHELL = "() => ({nav: !!document.querySelector('nav.nav'), " \
        "cards: document.querySelectorAll('main .card').length, " \
        "skeletons: document.querySelectorAll('main .skeleton').length})"


@pytest.mark.parametrize("route", ROUTES)
def test_shell_while_the_person_loads(world, page, route):
    log_in(page)
    held = []
    page.route("**/me", lambda r: held.append(r))
    page.goto(route)
    page.wait_for_selector(sel("logout-button"))
    state = page.evaluate(SHELL)
    assert state["nav"] and state["cards"] >= 2 and state["skeletons"] >= 2, state
    assert page.query_selector(sel("current-user")) is None
    for r in held:
        r.continue_()
    page.unroute("**/me")
    page.wait_for_selector(sel("current-user"))


def test_unreachable_service_inside_the_shell(world, page):
    log_in(page)
    page.route("**/me", lambda r: r.abort("connectionrefused"))
    page.goto("/requests")
    page.get_by_text("Pocketful can't be reached right now").wait_for()
    assert page.evaluate(SHELL)["nav"]
    assert page.is_visible(sel("logout-button"))
    page.unroute("**/me")
    page.get_by_role("button", name="Try again").click()
    page.wait_for_selector(sel("incoming-list"), state="attached")
    page.wait_for_selector(sel("current-user"))


RFC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
EXACT = "Exact expiry, with its UTC offset: "


def test_hold_lines_use_one_time_zone_and_one_wording(reset, page):
    reset(seed.fixture(authorization_ttl_seconds=3600, authorizations=[
        seeded_hold("a_gone", "ben", "ann", 900, hours=-2)]))
    ann, ben = signed_in("ann", "ben")
    open_hold = authorize(ann, "ben", 1500)
    captured = authorize(ann, "ben", 700)
    capture(ben, captured["authorization_id"], {"amount": 250})
    voided = authorize(ann, "ben", 400)
    expect(ann.post(f"/authorizations/{voided['authorization_id']}/void"), 200)
    log_in(page)
    page.goto("/authorizations")
    page.wait_for_selector(sel("authorization-list"))
    lines = {}
    for hold in (open_hold, captured, voided, {"authorization_id": "a_gone"}):
        aid = hold["authorization_id"]
        item = page.inner_text(sel(f"authorization-item-{aid}"))
        exact = page.text_content(sel(f"authorization-expires-{aid}"))
        assert item.count(exact) == 1 and EXACT + exact in item, item
        human = item.replace(EXACT + exact, "")
        assert not RFC.search(human), human
        lines[aid] = human
    assert "Expires " in lines[open_hold["authorization_id"]]
    assert "Captured " in lines[captured["authorization_id"]]
    assert "Released" in lines[voided["authorization_id"]]
    assert "Expired " in lines["a_gone"]
    assert "Expires " not in lines[captured["authorization_id"]] + lines[voided["authorization_id"]]
