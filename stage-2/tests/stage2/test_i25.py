"""Item 25: competing clients."""
from client import expect
from holdfx import sel
from ui import fill_form, log_in, open_home, wait_amount


def test_balance_spent_elsewhere(world, page):
    log_in(page, "cat")
    open_home(page)
    fill_form(page, "pay", "ben", "4.00", note="snacks", visibility="private")
    spent = expect(world.cat.write("/payments", {"to_handle": "ann", "amount": 300}), 201).json()
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-error"))
    wait_amount(page, "wallet-balance", 200)
    page.wait_for_selector(sel(f"activity-item-{spent['payment_id']}"))
    assert page.input_value(sel("pay-handle")) == "ben"
    assert page.input_value(sel("pay-amount")) == "4.00"
    assert page.input_value(sel("pay-note")) == "snacks"
    assert page.input_value(sel("pay-visibility")) == "private"


def test_request_cancelled_elsewhere(world, page):
    rid = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 500}),
                 201).json()["request_id"]
    log_in(page)
    page.goto("/requests")
    page.wait_for_selector(sel(f"request-pay-{rid}"))
    expect(world.ben.post(f"/requests/{rid}/cancel"), 200)
    page.click(sel(f"request-pay-{rid}"))
    page.wait_for_selector(sel("request-error"))
    page.wait_for_selector(f"{sel('request-item-' + rid)}[data-status='cancelled']")
    assert page.query_selector(sel(f"request-pay-{rid}")) is None
    assert world.ann.balance() == 10000
