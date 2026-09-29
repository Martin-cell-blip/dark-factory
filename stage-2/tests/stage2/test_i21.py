"""Item 21: the requests screen."""
from client import expect
from holdfx import money, sel
from ui import log_in, text, wait_amount


def _ask(requester, payer, amount=1200):
    return expect(requester.write("/requests", {"payer_handle": payer, "amount": amount}),
                  201).json()["request_id"]


def _open(page, handle="ann"):
    log_in(page, handle)
    page.goto("/requests")
    page.wait_for_selector(sel("incoming-list"), state="attached")
    page.wait_for_selector(sel("outgoing-list"), state="attached")


def test_lists_items_and_buttons(world, page):
    incoming = _ask(world.ben, "ann")
    outgoing = _ask(world.ann, "cat", 300)
    _open(page)
    page.wait_for_selector(f"{sel('incoming-list')} {sel('request-item-' + incoming)}")
    page.wait_for_selector(f"{sel('outgoing-list')} {sel('request-item-' + outgoing)}")
    assert page.get_attribute(sel(f"request-item-{incoming}"), "data-status") == "pending"
    assert text(page, f"request-amount-{incoming}") == money(1200)
    assert text(page, f"request-amount-{outgoing}") == money(300)
    assert page.query_selector(sel(f"request-pay-{incoming}"))
    assert page.query_selector(sel(f"request-decline-{incoming}"))
    assert page.query_selector(sel(f"request-cancel-{incoming}")) is None
    assert page.query_selector(sel(f"request-cancel-{outgoing}"))
    assert page.query_selector(sel(f"request-pay-{outgoing}")) is None
    assert page.query_selector(sel(f"request-decline-{outgoing}")) is None
    assert page.query_selector(sel("empty-requests")) is None


def test_pay_decline_cancel(world, page):
    paid, declined = _ask(world.ben, "ann"), _ask(world.cat, "ann", 50)
    cancelled = _ask(world.ann, "ben", 70)
    _open(page)
    page.click(sel(f"request-pay-{paid}"))
    page.wait_for_selector(f"{sel('request-item-' + paid)}[data-status='paid']")
    wait_amount(page, "wallet-balance", 8800)
    page.click(sel(f"request-decline-{declined}"))
    page.wait_for_selector(f"{sel('request-item-' + declined)}[data-status='declined']")
    page.click(sel(f"request-cancel-{cancelled}"))
    page.wait_for_selector(f"{sel('request-item-' + cancelled)}[data-status='cancelled']")
    for rid in (paid, declined, cancelled):
        for action in ("pay", "decline", "cancel"):
            assert page.query_selector(sel(f"request-{action}-{rid}")) is None
    assert page.query_selector(sel("request-error")) is None


def test_refusal_shows_request_error(world, page):
    rid = _ask(world.ann, "cat", 90000)
    _open(page, "cat")
    page.click(sel(f"request-pay-{rid}"))
    page.wait_for_selector(sel("request-error"))
    assert page.get_attribute(sel(f"request-item-{rid}"), "data-status") == "pending"


def test_empty_requests(world, page):
    _open(page)
    page.wait_for_selector(sel("empty-requests"))


def test_items_sit_in_the_right_list_and_closed_ones_have_no_buttons(world, page):
    asked_of_me = _ask(world.ben, "ann")
    i_asked = _ask(world.ann, "cat", 300)
    paid = _ask(world.cat, "ann", 20)
    expect(world.ann.write(f"/requests/{paid}/pay", {}), 201)
    cancelled = _ask(world.ann, "ben", 40)
    expect(world.ann.post(f"/requests/{cancelled}/cancel"), 200)
    declined = _ask(world.ben, "ann", 60)
    expect(world.ann.post(f"/requests/{declined}/decline"), 200)
    _open(page)
    page.wait_for_selector(sel(f"request-item-{asked_of_me}"))
    for rid in (asked_of_me, paid, declined):
        assert page.query_selector(f"{sel('incoming-list')} {sel('request-item-' + rid)}")
    for rid in (i_asked, cancelled):
        assert page.query_selector(f"{sel('outgoing-list')} {sel('request-item-' + rid)}")
    for rid, status in ((paid, "paid"), (cancelled, "cancelled"), (declined, "declined")):
        assert page.get_attribute(sel(f"request-item-{rid}"), "data-status") == status
        for action in ("pay", "decline", "cancel"):
            assert page.query_selector(sel(f"request-{action}-{rid}")) is None
