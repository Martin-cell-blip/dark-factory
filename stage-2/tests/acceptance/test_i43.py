"""Item 43: an operator settles across wallets it is not party to."""
import seed
from client import expect, login


def test_operator_outside_the_transfers(reset):
    reset(seed.fixture(users=[seed.user("ada", 1000), seed.user("bob", 0), seed.user("cy", 0),
                              seed.user("opr", 0)], settlement_operator_ids=["u_opr"]))
    opr = login("opr@pocket.test", seed.PASSWORD)
    body = {"transfers": [{"from_handle": "ada", "to_handle": "bob", "amount": 100},
                          {"from_handle": "bob", "to_handle": "cy", "amount": 50}]}
    result = expect(opr.write("/settlements", body), 201).json()
    assert [p["amount"] for p in result["payments"]] == [100, 50]
    balances = [login(f"{h}@pocket.test", seed.PASSWORD).balance()
                for h in ("ada", "bob", "cy", "opr")]
    assert balances == [900, 50, 50, 0]
