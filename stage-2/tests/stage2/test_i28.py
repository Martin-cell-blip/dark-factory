"""Item 28: the holds (authorisations) screens."""
import pytest

import seed
from client import expect
from holdfx import authorize, capture, money, seeded_hold, sel, signed_in
from ui import child_testids, fill_form, log_in, posts, text, wait_amount


def _open(page, handle="ann"):
    log_in(page, handle)
    page.goto("/authorizations")
    page.wait_for_selector(sel("wallet-available"))


@pytest.mark.parametrize("route", ["/", "/authorizations"])
def test_authorize_form(world, page, route):
    log_in(page)
    page.goto(route)
    page.wait_for_selector(sel("authorize-submit"))
    fill_form(page, "authorize", "ben", "25.5", note="deposit", visibility="private")
    page.click(sel("authorize-submit"))
    wait_amount(page, "wallet-available", 10000 - 2550)
    [hold] = expect(world.ann.get("/authorizations"), 200).json()["authorizations"]
    assert hold["amount"] == 2550 and hold["note"] == "deposit"
    assert hold["visibility"] == "private"


@pytest.mark.parametrize("handle,typed", [("ben", "25.555"), ("ben", "abc"), ("ben", "200.01"),
                                          ("nobody", "1.00"), ("ann", "1.00")])
def test_authorize_error(world, page, handle, typed):
    _open(page, "cat" if typed == "200.01" else "ann")
    fill_form(page, "authorize", handle, typed)
    page.click(sel("authorize-submit"))
    page.wait_for_selector(sel("authorize-error"))
    assert expect(world.ann.get("/authorizations"), 200).json()["authorizations"] == []


def test_list_items_and_controls(reset, page):
    reset(seed.fixture(authorizations=[seeded_hold("a_old", "ben", "ann", 900, status="expired",
                                                   hours=-3)]))
    ann, ben, cat = signed_in("ann", "ben", "cat")
    outgoing = authorize(ann, "ben", 1500)
    incoming = authorize(ben, "ann", 700)
    done = authorize(cat, "ann", 300)
    capture(ann, done["authorization_id"], {"amount": 120})
    _open(page)
    page.wait_for_selector(sel("authorization-list"))
    ids = [done["authorization_id"], incoming["authorization_id"], outgoing["authorization_id"]]
    assert child_testids(page, "authorization-list", "authorization-item-") == \
        [f"authorization-item-{i}" for i in ids + ["a_old"]]
    out_id, in_id, done_id = outgoing["authorization_id"], incoming["authorization_id"], done["authorization_id"]
    assert page.get_attribute(sel(f"authorization-item-{out_id}"), "data-status") == "open"
    assert page.get_attribute(sel(f"authorization-item-{done_id}"), "data-status") == "captured"
    assert page.get_attribute(sel("authorization-item-a_old"), "data-status") == "expired"
    assert text(page, f"authorization-amount-{out_id}") == money(1500)
    assert text(page, f"authorization-captured-{done_id}") == money(120)
    assert page.query_selector(sel(f"authorization-captured-{out_id}")) is None
    assert text(page, f"authorization-expires-{out_id}") == outgoing["expires_at"]
    assert page.input_value(sel(f"authorization-capture-amount-{in_id}")) == "7.00"
    assert page.query_selector(sel(f"authorization-capture-{in_id}"))
    assert page.query_selector(sel(f"authorization-void-{in_id}")) is None
    assert page.query_selector(sel(f"authorization-void-{out_id}"))
    assert page.query_selector(sel(f"authorization-capture-{out_id}")) is None
    for closed in (done_id, "a_old"):
        for control in ("capture", "capture-amount", "void"):
            assert page.query_selector(sel(f"authorization-{control}-{closed}")) is None


def test_capture_and_void_from_the_screen(world, page):
    incoming = authorize(world.ben, "ann", 2000)["authorization_id"]
    outgoing = authorize(world.ann, "cat", 400)["authorization_id"]
    _open(page)
    page.fill(sel(f"authorization-capture-amount-{incoming}"), "12.50")
    page.click(sel(f"authorization-capture-{incoming}"))
    page.wait_for_selector(f"{sel('authorization-item-' + incoming)}[data-status='captured']")
    assert text(page, f"authorization-captured-{incoming}") == money(1250)
    wait_amount(page, "wallet-balance", 11250)
    page.click(sel(f"authorization-void-{outgoing}"))
    page.wait_for_selector(f"{sel('authorization-item-' + outgoing)}[data-status='voided']")
    wait_amount(page, "wallet-available", 11250)
    assert page.query_selector(sel("authorization-error")) is None


def test_refused_capture_and_void_show_authorization_error(world, page):
    incoming = authorize(world.ben, "ann", 2000)["authorization_id"]
    outgoing = authorize(world.ann, "cat", 400)["authorization_id"]
    _open(page)
    sent = posts(page, "/capture")
    page.fill(sel(f"authorization-capture-amount-{incoming}"), "20.01")
    page.click(sel(f"authorization-capture-{incoming}"))
    page.wait_for_selector(sel("authorization-error"))
    assert len(sent) == 1
    expect(world.ann.post(f"/authorizations/{outgoing}/void"), 200)
    expect(world.ben.post(f"/authorizations/{incoming}/void"), 200)
    page.click(sel(f"authorization-capture-{incoming}"))
    page.wait_for_selector(f"{sel('authorization-item-' + incoming)}[data-status='voided']")
    page.wait_for_selector(sel("authorization-error"))
    assert page.query_selector(sel(f"authorization-void-{outgoing}")) is None


def test_invalid_capture_amount_is_refused_without_sending(world, page):
    incoming = authorize(world.ben, "ann", 2000)["authorization_id"]
    _open(page)
    sent = posts(page, "/capture")
    page.fill(sel(f"authorization-capture-amount-{incoming}"), "1.234")
    page.click(sel(f"authorization-capture-{incoming}"))
    page.wait_for_selector(sel("authorization-error"))
    assert sent == []


def test_empty_authorizations(world, page):
    _open(page)
    page.wait_for_selector(sel("empty-authorizations"))
