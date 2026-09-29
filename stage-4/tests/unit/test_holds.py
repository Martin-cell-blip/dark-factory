"""In-process checks of holds: what is held, captures, closes and expiry by the clock."""
from datetime import datetime, timedelta, timezone

from pocketful import holds

ANN = {"id": "u_ann", "handle": "ann"}
BEN = {"id": "u_ben", "handle": "ben"}
NOW = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)


def _hold(hold_id, amount, minutes):
    expires = (NOW + timedelta(minutes=minutes)).isoformat()
    return holds.record(hold_id, ANN, BEN, amount, "EUR", "", "public", "open", expires,
                        NOW.isoformat())


def test_held_is_the_sum_of_open_remainders():
    book = holds.Holds()
    book.add(_hold("a", 500, 10))
    book.add(_hold("b", 300, 20))
    assert book.held_by("u_ann") == 800 and book.held_by("u_ben") == 0


def test_partial_capture_then_close_releases_the_rest():
    book = holds.Holds()
    first = _hold("a", 1000, 10)
    book.add(first)
    book.capture(first, 300, closes=False, payment={"payment_id": "p1", "created_at": "t1"})
    assert (first["remaining_amount"], first["status"], book.held_by("u_ann")) == (700, "open", 700)
    book.capture(first, 200, closes=True, payment={"payment_id": "p2", "created_at": "t2"})
    assert first["status"] == "captured" and first["remaining_amount"] == 0
    assert first["captured_amount"] == 500 and first["payment_ids"] == ["p1", "p2"]
    assert first["payment_id"] == "p2" and book.held_by("u_ann") == 0
    assert first["closed_at"] == "t2"


def test_expiry_follows_the_clock_and_remembers_it():
    book = holds.Holds()
    soon, later = _hold("soon", 400, 1), _hold("later", 100, 60)
    book.add(soon)
    book.add(later)
    book.expire_due(NOW)
    assert book.held_by("u_ann") == 500
    book.expire_due(NOW + timedelta(minutes=1))
    assert soon["status"] == "expired" and soon["remaining_amount"] == 0
    assert soon["closed_at"] == soon["expires_at"]
    assert book.clock_expired == {"soon"} and book.held_by("u_ann") == 100


def test_closed_holds_do_not_expire_again():
    book = holds.Holds()
    voided = _hold("v", 400, 1)
    book.add(voided)
    book.close(voided, "voided", "t9")
    book.expire_due(NOW + timedelta(hours=1))
    assert voided["status"] == "voided" and book.clock_expired == set()
    assert book.held_by("u_ann") == 0
