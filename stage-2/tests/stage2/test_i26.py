"""Item 26: a lost payment response is uncertain, and retrying moves money exactly once."""
import pytest

from client import expect
from holdfx import sel
from ui import fill_form, log_in, open_home, posts, text, wait_amount


def _lose_the_next_response(page, committed: bool):
    """Answer the next POST /payments with a network failure, after (or instead of)
    delivering it to the service."""
    def handler(route):
        if committed:
            route.fetch()
        route.abort("connectionreset")
        page.unroute("**/payments", handler)
    page.route("**/payments", handler)


@pytest.mark.parametrize("committed", [True, False], ids=["after-commit", "before-commit"])
def test_uncertain_then_retry_moves_money_once(world, page, committed):
    log_in(page)
    open_home(page)
    sent = posts(page, "/payments")
    _lose_the_next_response(page, committed)
    fill_form(page, "pay", "ben", "15.00", note="lost")
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"))
    assert text(page, "pay-uncertain")
    assert page.query_selector(sel("pay-error")) is None
    assert world.ann.balance() == (8500 if committed else 10000)
    page.click(sel("pay-submit"))
    wait_amount(page, "wallet-balance", 8500)
    page.wait_for_selector(sel("pay-success"))
    assert page.query_selector(sel("pay-uncertain")) is None
    assert page.query_selector(sel("pay-error")) is None
    [payment] = expect(world.ann.get("/activity"), 200).json()["payments"]
    page.wait_for_selector(sel(f"activity-item-{payment['payment_id']}"))
    assert world.ann.balance() == 8500 and world.ben.balance() == 4000
    assert len(sent) == 2
    assert sent[0].headers["idempotency-key"] == sent[1].headers["idempotency-key"]
    assert sent[0].post_data_json == sent[1].post_data_json
