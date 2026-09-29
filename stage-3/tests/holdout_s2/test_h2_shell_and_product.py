"""Holdout for the foreman's item-32 follow-ups on stage 2: R1 (shell first), P1/P2 (times), P3 (phone)."""
import re
import time

import pytest

from holdout2_client import chromium, BASE, authorize, capture, fixture, iso, make_world, void

RFC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
MICRO = re.compile(r"\d{2}:\d{2}:\d{2}\.\d{3,}")


def sel(t):
    return f"[data-testid='{t}']"


@pytest.fixture(scope="module")
def browser():
    with chromium() as b:
        yield b


def signed_in(browser, width):
    ctx = browser.new_context(base_url=BASE, viewport={"width": width, "height": 800})
    pg = ctx.new_page()
    pg.set_default_timeout(8000)
    pg.goto("/login")
    pg.fill(sel("login-email"), "ada@example.com")
    pg.fill(sel("login-password"), "correct horse")
    pg.click(sel("login-submit"))
    pg.wait_for_selector(sel("current-user"))
    return ctx, pg


@pytest.mark.parametrize("width", [375, 1280])
@pytest.mark.parametrize("route", ["/", "/requests", "/split", "/authorizations"])
def test_shell_present_while_me_is_held(browser, width, route):
    make_world()
    ctx, pg = signed_in(browser, width)
    held = []
    pg.route(re.compile(r".*/me(\?.*)?$"), lambda r: held.append(r))
    pg.goto(route)
    time.sleep(1.0)
    assert pg.query_selector(sel("logout-button")), f"{route}@{width}: no log out while /me pending"
    links = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    for r in ("/", "/requests", "/split", "/authorizations"):
        assert r in links, f"{route}@{width}: nav link {r} missing while /me pending: {links}"
    for r in held:
        r.continue_()
    pg.wait_for_selector(sel("current-user"))
    assert pg.text_content(sel("current-handle")).strip() == "ada"
    ctx.close()


@pytest.mark.parametrize("width", [375, 1280])
def test_shell_present_when_me_unreachable(browser, width):
    make_world()
    ctx, pg = signed_in(browser, width)
    pg.route(re.compile(r".*/me(\?.*)?$"), lambda r: r.abort())
    pg.goto("/requests")
    time.sleep(1.5)
    assert pg.query_selector(sel("logout-button"))
    links = pg.eval_on_selector_all("a[href]", "els => els.map(e => e.getAttribute('href'))")
    assert "/" in links and "/authorizations" in links, links
    ctx.close()


def test_hold_times_one_zone_and_no_microseconds(browser):
    w = make_world(fixture(ttl=600))
    a_open = authorize(w.ada, "bob", 100).json()["authorization_id"]
    a_cap = authorize(w.ada, "bob", 100).json()["authorization_id"]
    capture(w.bob, a_cap, {"amount": 50})
    a_void = authorize(w.ada, "bob", 100).json()["authorization_id"]
    void(w.ada, a_void)
    ctx, pg = signed_in(browser, 1280)
    pg.goto("/authorizations")
    pg.wait_for_selector(sel(f"authorization-item-{a_open}"))
    for aid in (a_open, a_cap, a_void):
        item = pg.query_selector(sel(f"authorization-item-{aid}"))
        exp = pg.query_selector(sel(f"authorization-expires-{aid}"))
        human = pg.evaluate("([i, e]) => { const c = i.cloneNode(true);"
                            " const x = c.querySelector(`[data-testid='${e}']`); if (x) x.remove();"
                            " return c.innerText; }", [item, f"authorization-expires-{aid}"])
        assert not RFC.search(human), f"{aid}: raw RFC 3339 wall time in human text: {human!r}"
        assert not MICRO.search(human), f"{aid}: microseconds in human text: {human!r}"
        if exp is not None:
            assert exp.text_content().strip()  # the machine text stays present where rendered
    open_text = pg.inner_text(sel(f"authorization-item-{a_open}"))
    assert "Expires" in open_text
    cap_text = pg.inner_text(sel(f"authorization-item-{a_cap}"))
    assert ("Captured" in cap_text or "Collected" in cap_text) and "Expires" not in cap_text, cap_text
    assert "Expires" not in pg.inner_text(sel(f"authorization-item-{a_void}"))
    assert "Released" in pg.inner_text(sel(f"authorization-item-{a_void}"))
    ctx.close()


def test_phone_reaches_balance_and_activity_without_passing_forms(browser):
    from holdout2_client import pay
    w = make_world()
    pay(w.ada, "bob", 100, note="lunch")
    ctx, pg = signed_in(browser, 375)
    pg.goto("/")
    pg.wait_for_selector(sel("activity-list"))
    feed_top = pg.eval_on_selector(sel("activity-list"), "e => e.getBoundingClientRect().top + scrollY")
    form_top = pg.eval_on_selector(sel("pay-handle"), "e => e.getBoundingClientRect().top + scrollY")
    if feed_top > form_top:
        # forms first: there must be a visible jump link to the feed in the first screen,
        # or the forms must be collapsed so the feed sits within the first two screens
        jump = pg.evaluate("""() => [...document.querySelectorAll('a[href^="#"], button, summary')]
            .some(e => { const r = e.getBoundingClientRect();
                         return r.top < innerHeight && /activ/i.test(e.textContent + (e.getAttribute('href')||'')); })""")
        assert jump or feed_top < 2 * 800, f"feed at {feed_top}px below forms at {form_top}px, no jump link"
    ctx.close()
