"""Item 23: after a successful action the same page shows the new state without a reload,
and refreshes only after the write succeeded."""
from client import expect
from holdfx import sel
from ui import log_in, pay, wait_amount


def _order_of_calls(page):
    """Every API call the page makes, in order: ('request'|'response', method, path)."""
    events = []
    api = lambda url: url.split("//", 1)[1].split("/", 1)[1].split("?")[0]
    page.on("request", lambda r: events.append(("request", r.method, "/" + api(r.url))))
    page.on("response", lambda r: events.append(("response", r.request.method,
                                                 "/" + api(r.url))))
    return events


def test_pay_updates_balance_and_feed_after_the_write(world, page):
    log_in(page)
    events = _order_of_calls(page)
    navigations = []
    page.on("framenavigated", lambda frame: navigations.append(frame.url))
    pay(page, amount="15.00", note="lunch")
    wait_amount(page, "wallet-balance", 8500)
    [payment] = expect(world.ann.get("/activity"), 200).json()["payments"]
    page.wait_for_selector(sel(f"activity-item-{payment['payment_id']}"))
    written = events.index(("response", "POST", "/payments"))
    reads = [i for i, e in enumerate(events) if e == ("request", "GET", "/me")]
    assert any(i > written for i in reads), "the balance is read again after the write"
    assert len(navigations) == 1, "no reload after the payment"


def test_request_form_and_request_actions_refresh_the_page(world, page):
    log_in(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-available"))
    page.fill(sel("request-handle"), "ben")
    page.fill(sel("request-amount"), "3.00")
    page.click(sel("request-submit"))
    page.wait_for_selector(sel("request-success"))
    rid = expect(world.ben.write("/requests", {"payer_handle": "ann", "amount": 700}),
                 201).json()["request_id"]
    page.goto("/requests")
    page.click(sel(f"request-pay-{rid}"))
    page.wait_for_selector(f"{sel('request-item-' + rid)}[data-status='paid']")
    wait_amount(page, "wallet-balance", 9300)


def test_holds_page_refreshes_after_hold_capture_and_release(world, page, new_page):
    log_in(page)
    page.goto("/authorizations")
    page.wait_for_selector(sel("wallet-available"))
    page.fill(sel("authorize-handle"), "ben")
    page.fill(sel("authorize-amount"), "20.00")
    page.click(sel("authorize-submit"))
    wait_amount(page, "wallet-available", 8000)
    [hold] = expect(world.ann.get("/authorizations"), 200).json()["authorizations"]
    aid = hold["authorization_id"]
    page.wait_for_selector(f"{sel('authorization-item-' + aid)}[data-status='open']")
    ben = new_page()
    log_in(ben, "ben")
    ben.goto("/authorizations")
    ben.fill(sel(f"authorization-capture-amount-{aid}"), "5.00")
    ben.click(sel(f"authorization-capture-{aid}"))
    ben.wait_for_selector(f"{sel('authorization-item-' + aid)}[data-status='captured']")
    wait_amount(ben, "wallet-balance", 3000)
