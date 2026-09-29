"""Item 32 (judged from screenshots by the auditor): the loading and unreachable states sit
inside the normal shell, with navigation and log out, as DESIGN.md describes."""
import pytest

from holdfx import sel
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
