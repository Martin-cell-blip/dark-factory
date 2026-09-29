"""Item 24: wallet-refresh keeps the pay form, and the latest refresh wins."""
from client import expect
from holdfx import authorize, sel
from ui import amount_of, fill_form, log_in, open_home, wait_amount


def test_refresh_keeps_the_pay_form(world, page):
    log_in(page)
    open_home(page)
    fill_form(page, "pay", "ben", "12.34", note="kept", visibility="private")
    expect(world.ann.write("/payments", {"to_handle": "cat", "amount": 300}), 201)
    page.click(sel("wallet-refresh"))
    wait_amount(page, "wallet-balance", 9700)
    assert page.input_value(sel("pay-handle")) == "ben"
    assert page.input_value(sel("pay-amount")) == "12.34"
    assert page.input_value(sel("pay-note")) == "kept"
    assert page.input_value(sel("pay-visibility")) == "private"


def test_a_delayed_earlier_read_never_overwrites_a_later_one(world, page):
    log_in(page)
    open_home(page)
    held = []
    page.route("**/me", lambda route: held.append((route, route.fetch())))
    page.click(sel("wallet-refresh"))
    while len(held) < 1:
        page.wait_for_timeout(20)
    expect(world.ann.write("/payments", {"to_handle": "cat", "amount": 300}), 201)
    authorize(world.ann, "ben", 200)
    page.click(sel("wallet-refresh"))
    while len(held) < 2:
        page.wait_for_timeout(20)
    (early, early_body), (late, late_body) = held
    late.fulfill(response=late_body)
    wait_amount(page, "wallet-available", 9500)
    early.fulfill(response=early_body)
    page.wait_for_timeout(400)
    assert amount_of(page, "wallet-available") == 9500
    assert amount_of(page, "wallet-balance") == 9700
    assert amount_of(page, "wallet-held") == 200
    page.unroute("**/me")
