"""Item 13: concurrency on the seven idempotent paths and the hold invariants."""
import seed
from burst import burst, statuses
from client import balances_sum, expect, login, new_key
from holdfx import authorize, me


def _race(client, path, body, copies=20):
    key = new_key()
    responses = burst([lambda: client.post(path, body, key=key)] * copies)
    codes = statuses(responses)
    assert codes.count(201) == 1 and codes.count(200) == copies - 1, codes
    assert all(r.json() == responses[0].json() for r in responses)
    return responses[0].json()


def test_one_key_takes_effect_once_on_every_path(reset):
    reset(seed.fixture(settlement_operator_ids=["u_ann"]))
    ann, ben, cat = (login(f"{h}@pocket.test", seed.PASSWORD) for h in ("ann", "ben", "cat"))
    _race(ann, "/payments", {"to_handle": "ben", "amount": 100})
    rq = _race(ann, "/requests", {"payer_handle": "ben", "amount": 50})
    _race(ben, f"/requests/{rq['request_id']}/pay", {})
    _race(ann, "/splits", {"amount": 90, "participant_handles": ["ann", "cat"]})
    _race(ann, "/settlements", {"transfers": [{"from_handle": "ben", "to_handle": "cat",
                                               "amount": 5}]})
    held = _race(ann, "/authorizations", {"to_handle": "cat", "amount": 700})
    _race(cat, f"/authorizations/{held['authorization_id']}/capture", {"amount": 300})
    assert me(ann) == {**me(ann), "total": 10000 - 100 + 50 - 300, "held": 0}
    assert me(cat)["total"] == 500 + 5 + 300
    assert balances_sum([ann, ben, cat]) == 13000


def _people(reset, n=6, balance=1000):
    fx = seed.fixture(users=[seed.user(f"p{i}", balance) for i in range(n)])
    reset(fx)
    return [login(f"p{i}@pocket.test", seed.PASSWORD) for i in range(n)], seed.total(fx)


def test_holds_and_payments_never_overdraw_available(reset):
    people, total = _people(reset)
    spender = people[0]
    calls = []
    for i in range(50):
        path = "/authorizations" if i % 2 else "/payments"
        calls.append(lambda path=path, i=i: spender.write(
            path, {"to_handle": f"p{1 + i % 5}", "amount": 70}))
    codes = statuses(burst(calls))
    assert codes.count(201) == 14 and codes.count(409) == 36, codes
    body = me(spender)
    assert body["available"] == 20 and body["available"] >= 0
    assert balances_sum(people) == total


def test_concurrent_captures_never_exceed_the_authorization(reset):
    people, total = _people(reset, n=3)
    payer, receiver = people[0], people[1]
    aid = authorize(payer, "p1", 900)["authorization_id"]
    path = f"/authorizations/{aid}/capture"
    responses = burst([lambda: receiver.write(path, {"amount": 100, "final": False})
                       for _ in range(30)])
    codes = statuses(responses)
    assert codes.count(201) == 9, codes
    assert {r.json()["error"]["code"] for r in responses if r.status != 201} <= {
        "authorization_not_open", "capture_exceeds_authorization"}
    assert me(receiver)["total"] == 1900 and me(payer) == {**me(payer), "total": 100,
                                                           "held": 0, "available": 100}
    expect(receiver.write(path, {"amount": 1}), 409, "authorization_not_open")
    assert balances_sum(people) == total


def test_invariants_hold_at_every_read(reset):
    people, total = _people(reset)
    holds = [authorize(people[i], f"p{(i + 1) % 6}", 400)["authorization_id"]
             for i in range(6)]

    def work(i):
        me_ = people[i % 6]
        kind = i % 4
        if kind == 0:
            return people[(i + 1) % 6].write(f"/authorizations/{holds[i % 6]}/capture",
                                             {"amount": 50, "final": False})
        if kind == 1:
            return me_.write("/payments", {"to_handle": f"p{(i + 2) % 6}", "amount": 90})
        if kind == 2:
            return me_.write("/authorizations", {"to_handle": f"p{(i + 3) % 6}", "amount": 60})
        return me_.get("/me")

    for chunk in range(3):
        statuses(burst([lambda i=i: work(i + chunk * 40) for i in range(40)]))
        bodies = [me(p) for p in people]
        assert sum(b["total"] for b in bodies) == total
        assert all(b["available"] >= 0 and b["available"] == b["total"] - b["held"]
                   for b in bodies)
