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
    """Decision D7: 1000 users, here each with a different password, within 5 s."""
    fx = seed.fixture(users=[seed.user(f"u{i}", 100, password=f"password number {i}")
                             for i in range(1000)])
    started = time.monotonic()
    expect(request("POST", "/_test/reset", fx, timeout=10), 204)
    assert time.monotonic() - started < 5
    assert login("u999@pocket.test", "password number 999").balance() == 100


def test_export_and_import_within_ten_seconds(reset):
    fx = seed.fixture(users=[seed.user(f"u{i}", 1000) for i in range(100)])
    reset(fx)
    people = [login(f"u{i}@pocket.test", seed.PASSWORD) for i in range(10)]
    statuses(burst([lambda i=i: people[i % 10].write("/payments", {
        "to_handle": f"u{(i + 1) % 10}", "amount": 1}) for i in range(200)]))
    started = time.monotonic()
    document = expect(request("GET", "/_test/export", timeout=10), 200).json()
    assert time.monotonic() - started < 10
    started = time.monotonic()
    expect(request("POST", "/_test/import", document, timeout=10), 204)
    assert time.monotonic() - started < 10


API_LIMIT = 1024 * 1024


def _padded_payment(size: int) -> bytes:
    """A valid payment body of exactly `size` bytes, grown by an ignored array field."""
    head, tail = b'{"to_handle": "ben", "amount": 1, "pad": [', b"]}"
    zeros = (size - len(head) - len(tail) + 1) // 2
    body = head + b",".join([b"0"] * zeros) + tail
    return body + b" " * (size - len(body))


def test_api_bodies_above_one_mib_are_refused_with_the_envelope(world):
    """Decision D8 (amended): API routes cap bodies at 1 MiB."""
    expect(world.ann.write("/payments", raw=_padded_payment(API_LIMIT + 1)),
           413, "payload_too_large")
    assert world.ann.balance() == 10000
    expect(world.ann.write("/payments", {"to_handle": "ben", "amount": 1}), 201)


def test_fifty_concurrent_maximal_api_bodies_within_five_seconds(world):
    body = _padded_payment(API_LIMIT)
    assert len(body) == API_LIMIT

    def call():
        started = time.monotonic()
        resp = world.ann.write("/payments", raw=body)
        return resp, time.monotonic() - started

    results = burst([call] * 50)
    codes = statuses([r for r, _ in results])
    assert codes == [201] * 50, codes
    assert max(elapsed for _, elapsed in results) < 5
    assert world.ann.balance() == 10000 - 50


def test_thirty_mib_import_is_accepted(reset):
    """Decision D8 (amended): reset and import take up to 64 MiB; an unchanged export of a
    30 MiB state is imported, not refused."""
    fx = seed.fixture(users=[seed.user(f"u{i}", 1, display_name="n" * 3000)
                             for i in range(10000)])
    expect(request("POST", "/_test/reset", fx, timeout=10), 204)
    exported = expect(request("GET", "/_test/export", timeout=10), 200).body
    assert len(exported) > 30 * 1024 * 1024
    expect(request("POST", "/_test/import", raw=exported, timeout=10), 204)
    assert login("u9999@pocket.test", seed.PASSWORD).balance() == 1
