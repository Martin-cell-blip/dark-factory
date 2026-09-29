"""Item 22: the split screen and its preview."""
import pytest

import seed
from client import expect
from holdfx import money, sel
from ui import log_in, posts, text


def _open(page):
    log_in(page)
    page.goto("/split")
    page.wait_for_selector(sel("split-submit"))


@pytest.mark.parametrize("typed,handles,expected", [
    ("10.00", "ann,ben,cat", [334, 333, 333]),
    ("10", "cat, ben , ann", [334, 333, 333]),
    ("0.01", "ann,ben,cat", [1, 0, 0]),
    ("0.10", "ben,cat,ann", [4, 3, 3]),
    ("9.99", "ann,ben,cat", [333, 333, 333]),
])
def test_preview_before_anything_is_posted(world, page, typed, handles, expected):
    _open(page)
    sent = posts(page, "/splits")
    page.fill(sel("split-amount"), typed)
    page.fill(sel("split-handles"), handles)
    page.wait_for_selector(sel("split-preview"))
    people = [h.strip() for h in handles.split(",")]
    assert [text(page, f"split-share-{h}") for h in people] == [money(m) for m in expected]
    assert sent == []


def test_submitted_split_matches_the_preview(world, page):
    _open(page)
    page.fill(sel("split-amount"), "10.00")
    page.fill(sel("split-handles"), "ben,ann,cat")
    page.fill(sel("split-note"), "pizza")
    page.wait_for_selector(sel("split-preview"))
    shown = {h: text(page, f"split-share-{h}") for h in ("ben", "ann", "cat")}
    page.click(sel("split-submit"))
    page.wait_for_selector(sel("split-success"))
    requests = {r["payer_handle"]: r for r in
                expect(world.ann.get("/requests?direction=outgoing"), 200).json()["requests"]}
    assert set(requests) == {"ben", "cat"}
    assert money(requests["ben"]["amount"]) == shown["ben"] == money(334)
    assert money(requests["cat"]["amount"]) == shown["cat"]
    assert requests["ben"]["note"] == "pizza"


def test_minor_units_zero(reset, page):
    reset(seed.fixture(currency="JPY", minor_units=0))
    _open(page)
    page.fill(sel("split-amount"), "1000")
    page.fill(sel("split-handles"), "ann,ben,cat")
    page.wait_for_selector(sel("split-preview"))
    assert text(page, "split-share-ann") == "334 JPY"


@pytest.mark.parametrize("typed,handles", [("10.00", "ann,nobody"), ("10.00", "ben,ben"),
                                           ("10.001", "ben"), ("10.00", " , ")])
def test_split_error(world, page, typed, handles):
    _open(page)
    page.fill(sel("split-amount"), typed)
    page.fill(sel("split-handles"), handles)
    page.click(sel("split-submit"))
    page.wait_for_selector(sel("split-error"))
    assert expect(world.ann.get("/requests"), 200).json()["requests"] == []
