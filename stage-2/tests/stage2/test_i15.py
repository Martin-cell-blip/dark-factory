"""Item 15: screens reachable by URL; /requests and /authorizations still serve JSON."""
import pytest

from client import expect, request
from holdfx import sel
from ui import log_in

SCREENS = {"/": "pay-submit", "/requests": "incoming-list", "/split": "split-submit",
           "/signup": "signup-submit", "/login": "login-submit",
           "/authorizations": "authorization-list"}


@pytest.mark.parametrize("route", list(SCREENS))
def test_html_for_browsers(world, route):
    resp = request("GET", route, headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
    assert resp.status == 200
    assert resp.headers["content-type"].startswith("text/html")


def test_api_paths_keep_json(world):
    for path in ("/requests", "/authorizations"):
        resp = expect(world.ann.get(path), 200)
        assert resp.headers["content-type"].startswith("application/json")
        expect(request("GET", path, headers={"Accept": "application/json"}), 401)


@pytest.mark.parametrize("route", list(SCREENS))
def test_every_screen_directly_navigable(world, page, route):
    log_in(page)
    page.goto(route)
    page.wait_for_selector(sel(SCREENS[route]), state="attached")


@pytest.mark.parametrize("route", ["/", "/requests", "/split", "/authorizations"])
def test_signed_out_visits_lead_to_login(world, page, route):
    page.goto(route)
    page.wait_for_selector(sel("login-submit"))
    assert page.url.endswith("/login")


def test_screens_reachable_through_the_ui(world, page):
    log_in(page)
    page.goto("/")
    for label, anchor in (("Requests", "incoming-list"), ("Split", "split-submit"),
                          ("Holds", "authorization-list"), ("Home", "pay-submit")):
        page.get_by_role("link", name=label, exact=True).click()
        page.wait_for_selector(sel(anchor), state="attached")
    page.click(sel("logout-button"))
    page.get_by_role("link", name="Create account").first.click()
    page.wait_for_selector(sel("signup-submit"))
