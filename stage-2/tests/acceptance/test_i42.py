"""Item 42: exact arithmetic up to 2^53."""
import seed
from client import balances_sum, expect, login, request

TOP = 2 ** 53 - 1


def test_largest_balance_reads_back_exactly(reset):
    reset(seed.fixture(users=[seed.user("rich", TOP), seed.user("poor", 0)]))
    rich = login("rich@pocket.test", seed.PASSWORD)
    assert expect(rich.get("/me"), 200).json()["balance"] == TOP
    assert b"9007199254740991" in rich.get("/me").body
    document = expect(request("GET", "/_test/export"), 200).json()
    reset(seed.fixture())
    expect(request("POST", "/_test/import", document), 204)
    assert rich.balance() == TOP


def test_large_payment_near_the_top_is_exact(reset):
    fx = seed.fixture(users=[seed.user("rich", TOP - 7), seed.user("poor", 3)])
    reset(fx)
    rich = login("rich@pocket.test", seed.PASSWORD)
    poor = login("poor@pocket.test", seed.PASSWORD)
    expect(rich.write("/payments", {"to_handle": "poor", "amount": 1000000000}), 201)
    assert rich.balance() == TOP - 7 - 1000000000
    assert poor.balance() == 1000000003
    assert balances_sum([rich, poor]) == seed.total(fx)
