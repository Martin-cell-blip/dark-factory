"""Item 34: 50 concurrent requests answered within 5 s without 5xx; reset within 10 s."""
import time

import seed
from burst import burst, statuses
from client import expect, login, request


def test_fifty_in_flight_within_five_seconds(world):
    people = world.everyone

    def call(i):
        started = time.monotonic()
        client = people[i % 3]
        if i % 3 == 0:
            resp = client.write("/payments", {"to_handle": "cat", "amount": 1})
        elif i % 3 == 1:
            resp = client.get("/activity")
        else:
            resp = request("POST", "/auth/login", {"email": "ben@pocket.test",
                                                   "password": seed.PASSWORD})
        return resp, time.monotonic() - started

    results = burst([lambda i=i: call(i) for i in range(50)])
    statuses([r for r, _ in results])
    assert max(elapsed for _, elapsed in results) < 5


def test_reset_of_a_large_fixture_within_ten_seconds():
    fx = seed.fixture(users=[seed.user(f"u{i}", 100) for i in range(100)])
    started = time.monotonic()
    expect(request("POST", "/_test/reset", fx, timeout=10), 204)
    assert time.monotonic() - started < 10
    assert login("u99@pocket.test", seed.PASSWORD).balance() == 100
