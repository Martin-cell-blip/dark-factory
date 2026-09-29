"""Item 19: the request form on Home."""
import pytest

from client import expect
from holdfx import sel
from ui import fill_form, log_in, open_home, posts


def _requests_of(client):
    return expect(client.get("/requests"), 200).json()["requests"]


def test_request_is_sent_in_minor_units(world, page):
    log_in(page)
    open_home(page)
    for testid in ("request-handle", "request-amount", "request-note", "request-submit"):
        assert page.is_visible(sel(testid))
    fill_form(page, "request", "ben", "12.5", note="taxi")
    page.click(sel("request-submit"))
    page.wait_for_selector(sel("request-success"))
    [made] = _requests_of(world.ben)
    assert made["amount"] == 1250 and made["note"] == "taxi" and made["requester_handle"] == "ann"


@pytest.mark.parametrize("typed", ["12.345", "twelve", "", "0.00"])
def test_invalid_amount_shows_request_error_without_sending(world, page, typed):
    log_in(page)
    open_home(page)
    sent = posts(page, "/requests")
    fill_form(page, "request", "ben", typed)
    page.click(sel("request-submit"))
    page.wait_for_selector(sel("request-error"))
    assert sent == [] and _requests_of(world.ben) == []


@pytest.mark.parametrize("handle", ["nobody", "ann"])
def test_refusal_shows_request_error(world, page, handle):
    log_in(page)
    open_home(page)
    fill_form(page, "request", handle, "5.00")
    page.click(sel("request-submit"))
    page.wait_for_selector(sel("request-error"))
    assert _requests_of(world.ann) == []
