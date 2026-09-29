"""Item 17: wallet numbers are formatted exactly and available is the headline."""
import pytest

import seed
from holdfx import authorize, money, seeded_hold, sel
from ui import amount_of, log_in, open_home, text, wait_amount


@pytest.mark.parametrize("currency,units,balance,shown", [
    ("EUR", 2, 10000, "100.00 EUR"), ("JPY", 0, 1200, "1200 JPY"),
    ("BHD", 3, 1500, "1.500 BHD"), ("EUR", 2, 5, "0.05 EUR"), ("BHD", 3, 7, "0.007 BHD"),
])
def test_balance_formatting(reset, page, currency, units, balance, shown):
    reset(seed.fixture(users=[seed.user("ann", balance), seed.user("ben", 1)],
                       currency=currency, minor_units=units))
    log_in(page)
    open_home(page)
    assert text(page, "wallet-balance") == shown
    assert amount_of(page, "wallet-balance") == balance
    assert text(page, "wallet-available") == shown
    assert amount_of(page, "wallet-available") == balance
    assert page.query_selector(sel("wallet-held")) is None, "absent when nothing is held"


def test_seeded_holds_show_immediately_after_reset(reset, page):
    reset(seed.fixture(authorizations=[seeded_hold("a_1", "ann", "ben", 2500)]))
    log_in(page)
    open_home(page)
    assert text(page, "wallet-available") == money(7500)
    assert amount_of(page, "wallet-available") == 7500
    assert text(page, "wallet-balance") == money(10000)
    assert text(page, "wallet-held") == money(2500)
    assert amount_of(page, "wallet-held") == 2500


def test_available_is_the_headline_number(reset, page):
    reset(seed.fixture(authorizations=[seeded_hold("a_1", "ann", "ben", 2500)]))
    log_in(page)
    open_home(page)
    size = lambda testid: page.eval_on_selector(
        sel(testid), "e => parseFloat(getComputedStyle(e).fontSize)")
    assert size("wallet-available") > size("wallet-balance")
    assert size("wallet-available") > size("wallet-held")


def test_new_holds_update_the_numbers(world, page):
    log_in(page)
    open_home(page)
    authorize(world.ann, "ben", 1234)
    page.click(sel("wallet-refresh"))
    wait_amount(page, "wallet-available", 10000 - 1234)
    assert text(page, "wallet-held") == money(1234)
    assert text(page, "wallet-balance") == money(10000)
