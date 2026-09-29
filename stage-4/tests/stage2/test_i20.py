"""Item 20: the activity feed on Home."""
from client import expect
from holdfx import authorize, capture, money, sel
from ui import child_testids, log_in, open_home, text


def _pay(client, to, amount, **extra):
    body = {"to_handle": to, "amount": amount, **extra}
    return expect(client.write("/payments", body), 201).json()


def test_items_parts_and_order(world, page):
    made = [_pay(world.ann, "ben", 2500, note="dinner"),
            _pay(world.ben, "cat", 10, visibility="private"),
            _pay(world.cat, "ann", 5)]
    held = authorize(world.ben, "ann", 300)
    made.append(capture(world.ann, held["authorization_id"]).json())
    log_in(page)
    open_home(page)
    page.wait_for_selector(sel("activity-list"))
    order = child_testids(page, "activity-list", "activity-item-")
    visible = [p for p in made if p["visibility"] == "public"]
    assert order == [f"activity-item-{p['payment_id']}" for p in reversed(visible)]
    first = made[0]["payment_id"]
    assert page.get_attribute(sel(f"activity-item-{first}"), "data-visibility") == "public"
    parties = text(page, f"activity-parties-{first}")
    assert "ann" in parties and "ben" in parties
    assert text(page, f"activity-amount-{first}") == money(2500)
    assert text(page, f"activity-note-{first}") == "dinner"
    assert text(page, f"activity-note-{made[2]['payment_id']}") == ""


def test_private_items_for_the_parties_only(world, page, new_page):
    private = _pay(world.ben, "cat", 10, visibility="private")["payment_id"]
    log_in(page, "cat")
    open_home(page)
    page.wait_for_selector(sel(f"activity-item-{private}"))
    assert page.get_attribute(sel(f"activity-item-{private}"), "data-visibility") == "private"
    other = new_page()
    log_in(other, "ann")
    open_home(other)
    other.wait_for_selector(sel("empty-activity"))
    assert other.query_selector(sel("activity-list")) is None
    assert other.query_selector(sel(f"activity-item-{private}")) is None


def test_empty_activity_replaced_by_the_list(world, page):
    log_in(page, "cat")
    open_home(page)
    page.wait_for_selector(sel("empty-activity"))
    payment = _pay(world.ann, "ben", 1)
    page.click(sel("wallet-refresh"))
    page.wait_for_selector(sel(f"activity-item-{payment['payment_id']}"))
    assert page.query_selector(sel("empty-activity")) is None
