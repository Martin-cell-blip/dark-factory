"""Item 3: negative seeded balance is 422 with state unchanged; minor units 0, 2, 3."""
import pytest

import seed
from client import expect, login, request


def test_negative_balance_is_rejected_and_changes_nothing(reset):
    reset(seed.fixture())
    ann = login("ann@pocket.test", seed.PASSWORD)
    bad = seed.fixture(users=[seed.user("zed", -1)])
    expect(request("POST", "/_test/reset", bad), 422, "validation_failed")
    assert ann.balance() == 10000
    expect(request("POST", "/auth/login", {"email": "zed@pocket.test",
                                           "password": seed.PASSWORD}), 401)


@pytest.mark.parametrize("currency,minor_units", [("JPY", 0), ("EUR", 2), ("BHD", 3)])
def test_minor_units_reported_by_me(reset, currency, minor_units):
    reset(seed.fixture(currency=currency, minor_units=minor_units))
    me = login("ann@pocket.test", seed.PASSWORD).get("/me").json()
    assert me["currency"] == currency and me["minor_units"] == minor_units
