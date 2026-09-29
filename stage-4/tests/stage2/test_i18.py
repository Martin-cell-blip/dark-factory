"""Item 18: the pay form's decimal input, errors, kept values and replays."""
import pytest

import seed
from client import expect
from holdfx import sel
from ui import fill_form, log_in, open_home, pay, posts, wait_amount


@pytest.mark.parametrize("typed,minor", [("15.00", 1500), ("15", 1500), ("15.5", 1550),
                                         ("0.01", 1), (" 7.25 ", 725)])
def test_typed_decimals_become_minor_units(world, page, typed, minor):
    log_in(page)
    pay(page, amount=typed)
    wait_amount(page, "wallet-balance", 10000 - minor)
    assert world.ben.balance() == 2500 + minor


@pytest.mark.parametrize("typed", ["15.005", "abc", "1,5", "-5", "", "0", "1e3", "15.", ".5"])
def test_invalid_input_shows_pay_error_and_sends_nothing(world, page, typed):
    log_in(page)
    open_home(page)
    sent = posts(page, "/payments")
    fill_form(page, "pay", "ben", typed)
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-error"))
    assert sent == []
    assert world.ann.balance() == 10000


def test_visibility_options_and_note(world, page):
    log_in(page)
    open_home(page)
    values = page.eval_on_selector_all(f"{sel('pay-visibility')} option", "os => os.map(o => o.value)")
    assert values == ["public", "private"]
    fill_form(page, "pay", "ben", "2.00", note="for the tickets", visibility="private")
    page.click(sel("pay-submit"))
    wait_amount(page, "wallet-balance", 9800)
    [payment] = expect(world.ben.get("/activity"), 200).json()["payments"]
    assert payment["visibility"] == "private" and payment["note"] == "for the tickets"


@pytest.mark.parametrize("handle,amount", [("ben", "99999.00"), ("nobody", "1.00"), ("ann", "1.00")])
def test_every_refusal_shows_pay_error(world, page, handle, amount):
    log_in(page)
    pay(page, handle=handle, amount=amount)
    page.wait_for_selector(sel("pay-error"))
    assert world.ann.balance() == 10000


def test_values_kept_and_unchanged_resubmit_is_a_replay(world, page):
    log_in(page)
    sent = posts(page, "/payments")
    pay(page, amount="15.00", note="lunch")
    wait_amount(page, "wallet-balance", 8500)
    assert page.input_value(sel("pay-handle")) == "ben"
    assert page.input_value(sel("pay-amount")) == "15.00"
    assert page.input_value(sel("pay-note")) == "lunch"
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-success"))
    page.wait_for_timeout(300)
    assert page.query_selector(sel("pay-error")) is None
    assert world.ann.balance() == 8500
    feed = expect(world.ann.get("/activity"), 200).json()["payments"]
    assert len(feed) == 1
    assert len(sent) == 2
    assert sent[0].headers["idempotency-key"] == sent[1].headers["idempotency-key"]
    assert sent[0].post_data_json == sent[1].post_data_json


def test_changing_a_field_makes_a_new_payment(world, page):
    log_in(page)
    pay(page, amount="15.00")
    wait_amount(page, "wallet-balance", 8500)
    page.fill(sel("pay-amount"), "20.00")
    page.click(sel("pay-submit"))
    wait_amount(page, "wallet-balance", 6500)
    page.fill(sel("pay-note"), "again")
    page.click(sel("pay-submit"))
    wait_amount(page, "wallet-balance", 4500)
    assert page.query_selector(sel("pay-error")) is None
    assert len(expect(world.ann.get("/activity"), 200).json()["payments"]) == 3


CONVERSIONS = [
    ("JPY", 0, "1200", 1200), ("BHD", 3, "1.234", 1234), ("BHD", 3, "1.005", 1005),
    ("EUR", 2, "0.29", 29), ("EUR", 2, "1000000.01", 100000001), ("EUR", 2, "0.07", 7),
]
REFUSED = [("JPY", 0, "12.5"), ("JPY", 0, "12."), ("BHD", 3, "1.2345"), ("EUR", 2, "1.001")]
FORMS = {
    "pay": ("/", "/payments", "amount"),
    "request": ("/", "/requests", "amount"),
    "authorize": ("/authorizations", "/authorizations", "amount"),
    "split": ("/split", "/splits", "amount"),
}


def _submit(page, form, handle, typed):
    route, _, _ = FORMS[form]
    page.goto(route)
    page.wait_for_selector(sel(f"{form}-submit"))
    if form == "split":
        page.fill(sel("split-amount"), typed)
        page.fill(sel("split-handles"), f"ann,{handle}")
    else:
        fill_form(page, form, handle, typed)
    page.click(sel(f"{form}-submit"))


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("currency,units,typed,minor", CONVERSIONS)
def test_exact_decimal_conversion_on_every_amount_form(reset, page, form, currency, units,
                                                       typed, minor):
    reset(seed.fixture(users=[seed.user("ann", 200000000), seed.user("ben", 1)],
                       currency=currency, minor_units=units))
    log_in(page)
    sent = posts(page, FORMS[form][1])
    _submit(page, form, "ben", typed)
    page.wait_for_selector(sel(f"{form}-success"))
    sent_amount = sent[-1].post_data_json["amount"]
    assert sent_amount == minor and isinstance(sent_amount, int)


@pytest.mark.parametrize("form", list(FORMS))
@pytest.mark.parametrize("currency,units,typed", REFUSED)
def test_too_many_places_refused_on_every_amount_form(reset, page, form, currency, units, typed):
    reset(seed.fixture(currency=currency, minor_units=units))
    log_in(page)
    sent = posts(page, FORMS[form][1])
    _submit(page, form, "ben", typed)
    page.wait_for_selector(sel(f"{form}-error"))
    assert sent == []
