"""Item 29: no horizontal page scrolling at 375 and 1280 CSS pixels."""
import pytest

from client import expect
from holdfx import authorize, sel
from ui import ROUTES, log_in

LONG = "a note that is long enough to wrap " * 5
WIDTHS = [375, 1280]


@pytest.fixture
def busy(world):
    """Data with long notes on every list."""
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 9999, "note": LONG[:200]}), 201)
    expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 1000000000,
                                         "note": "x" * 200}), 201)
    authorize(world.ben, "ann", 1000, note="w" * 200)
    authorize(world.ann, "cat", 1, note=LONG[:200])
    return world


def _no_horizontal_scroll(page):
    width = page.viewport_size["width"]
    assert page.evaluate("document.documentElement.scrollWidth") <= width
    assert page.evaluate("document.body.scrollWidth") <= width


@pytest.mark.parametrize("width", WIDTHS)
def test_signed_in_with_data(busy, new_page, width):
    page = new_page(width, 800)
    log_in(page)
    for route in ROUTES + ["/login", "/signup"]:
        page.goto(route)
        page.wait_for_selector(sel("current-user"))
        page.wait_for_timeout(300)
        _no_horizontal_scroll(page)
    page.goto("/split")
    page.fill(sel("split-amount"), "123456.78")
    page.fill(sel("split-handles"), "ann,ben,cat,abcdefghijklmnopqrst")
    page.wait_for_selector(sel("split-preview"))
    _no_horizontal_scroll(page)


@pytest.mark.parametrize("width", WIDTHS)
def test_signed_out(world, new_page, width):
    page = new_page(width, 800)
    for route in ("/login", "/signup"):
        page.goto(route)
        page.wait_for_selector(sel("login-submit" if route == "/login" else "signup-submit"))
        _no_horizontal_scroll(page)
