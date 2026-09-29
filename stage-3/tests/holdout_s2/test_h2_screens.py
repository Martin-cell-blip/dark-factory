"""Holdout: stage-2 screens, driven with the Playwright sync API in Chromium.

Elements are found only by data-testid. Network interception is used only on the spec'd API
paths (POST /payments, GET /me) to observe what the browser sends or to lose a response.
"""
import json
import re

import pytest
from playwright.sync_api import sync_playwright

from holdout2_client import (BASE, Client, ask, authorize, call, fixture, login, make_world,
                            new_key, pay, reset, user)

RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
ROUTES = ["/", "/requests", "/split", "/authorizations"]


def sel(name):
    return f"[data-testid='{name}']"


def money(minor, mu=2, cur="EUR"):
    if mu == 0:
        return f"{minor} {cur}"
    t = str(minor).rjust(mu + 1, "0")
    return f"{t[:-mu]}.{t[-mu:]} {cur}"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture(params=[1280])
def page(browser, request):
    ctx = browser.new_context(base_url=BASE, viewport={"width": request.param, "height": 900})
    pg = ctx.new_page()
    pg.set_default_timeout(8000)
    yield pg
    ctx.close()


def ui_login(page, email="ada@example.com", password="correct horse"):
    page.goto("/login")
    page.fill(sel("login-email"), email)
    page.fill(sel("login-password"), password)
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))


def posts(page, path):
    """Record the JSON bodies and Idempotency-Keys of browser POSTs to an API path."""
    seen = []

    def on_req(req):
        if req.method == "POST" and req.url.split("?")[0].endswith(path):
            try:
                body = json.loads(req.post_data or "null")
            except ValueError:
                body = req.post_data
            seen.append((body, req.headers.get("idempotency-key")))
    page.on("request", on_req)
    return seen


def wait_attr(page, tid, attr, value):
    page.wait_for_function(
        "([t, a, v]) => { const e = document.querySelector(`[data-testid='${t}']`);"
        " return !!e && e.getAttribute(a) === v; }", arg=[tid, attr, value])


def text(page, tid):
    return page.text_content(sel(tid)).strip()


def fill_pay(page, handle="bob", amount="15.00", note=None, visibility=None):
    page.fill(sel("pay-handle"), handle)
    page.fill(sel("pay-amount"), amount)
    if note is not None:
        page.fill(sel("pay-note"), note)
    if visibility is not None:
        page.select_option(sel("pay-visibility"), visibility)


# ---- wallet numbers ------------------------------------------------------------------

def test_wallet_numbers_with_seeded_hold(page):
    from holdout2_client import iso
    reset(fixture(authorizations=[{"id": "a_1", "from_user_id": "u_ada", "to_user_id": "u_bob",
                                   "amount": 2000, "note": "deposit", "visibility": "public",
                                   "status": "open", "expires_at": iso(7200)}]))
    ui_login(page)
    page.goto("/")
    assert text(page, "wallet-available") == money(8000)
    assert page.get_attribute(sel("wallet-available"), "data-amount") == "8000"
    assert text(page, "wallet-balance") == money(10000)
    assert page.get_attribute(sel("wallet-balance"), "data-amount") == "10000"
    assert text(page, "wallet-held") == money(2000)
    assert page.get_attribute(sel("wallet-held"), "data-amount") == "2000"
    # headline: available rendered larger than total and held
    size = lambda t: float(page.eval_on_selector(sel(t), "e => parseFloat(getComputedStyle(e).fontSize)"))
    assert size("wallet-available") > size("wallet-balance")
    assert size("wallet-available") > size("wallet-held")


def test_wallet_held_absent_when_zero(page):
    make_world()
    ui_login(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-available"))
    assert page.query_selector(sel("wallet-held")) is None


@pytest.mark.parametrize("cur,mu,bal,shown", [("JPY", 0, 1200, "1200 JPY"), ("BHD", 3, 1234, "1.234 BHD"),
                                               ("EUR", 2, 5, "0.05 EUR")])
def test_formats(page, cur, mu, bal, shown):
    reset(fixture(currency=cur, minor_units=mu, users=[user("ada", bal), user("bob", 0)]))
    ui_login(page)
    page.goto("/")
    assert text(page, "wallet-balance") == shown
    assert text(page, "wallet-available") == shown


# ---- pay form decimals -----------------------------------------------------------------

@pytest.mark.parametrize("cur,mu,typed,minor", [
    ("EUR", 2, "15.00", 1500), ("EUR", 2, "15", 1500), ("EUR", 2, "15.5", 1550),
    ("EUR", 2, "0.29", 29), ("EUR", 2, "1000000.01", 100000001), ("EUR", 2, "0.07", 7),
    ("JPY", 0, "1200", 1200), ("BHD", 3, "1.234", 1234), ("BHD", 3, "1.005", 1005),
])
def test_pay_amount_converts_exactly(page, cur, mu, typed, minor):
    reset(fixture(currency=cur, minor_units=mu, users=[user("ada", 10 ** 9), user("bob", 0)]))
    ui_login(page)
    page.goto("/")
    seen = posts(page, "/payments")
    fill_pay(page, amount=typed)
    page.click(sel("pay-submit"))
    wait_attr(page, "wallet-available", "data-amount", str(10 ** 9 - minor))
    assert [b["amount"] for b, _ in seen] == [minor]


@pytest.mark.parametrize("cur,mu,typed", [
    ("EUR", 2, "15.005"), ("EUR", 2, "abc"),
    ("JPY", 0, "12.5"), ("JPY", 0, "12."), ("BHD", 3, "1.2345"), ("EUR", 2, "")])
def test_pay_amount_invalid_sends_nothing(page, cur, mu, typed):
    reset(fixture(currency=cur, minor_units=mu))
    ui_login(page)
    page.goto("/")
    seen = posts(page, "/payments")
    fill_pay(page, amount=typed)
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-error"))
    page.wait_for_timeout(300)
    assert seen == []


def test_invalid_request_and_authorize_amounts_send_nothing(page):
    make_world()
    ui_login(page)
    page.goto("/")
    rq = posts(page, "/requests")
    page.fill(sel("request-handle"), "bob")
    page.fill(sel("request-amount"), "2.345")
    page.click(sel("request-submit"))
    page.wait_for_selector(sel("request-error"))
    page.goto("/authorizations")
    au = posts(page, "/authorizations")
    page.fill(sel("authorize-handle"), "bob")
    page.fill(sel("authorize-amount"), "x1")
    page.click(sel("authorize-submit"))
    page.wait_for_selector(sel("authorize-error"))
    page.wait_for_timeout(300)
    assert rq == [] and au == []


# ---- retries, uncertainty, competition -----------------------------------------------------

def test_resubmit_unchanged_is_one_payment_and_change_is_new(page):
    w = make_world()
    ui_login(page)
    page.goto("/")
    seen = posts(page, "/payments")
    fill_pay(page, amount="1.00", note="lunch")
    page.click(sel("pay-submit"))
    wait_attr(page, "wallet-balance", "data-amount", "9900")
    assert page.input_value(sel("pay-amount")) == "1.00" and page.input_value(sel("pay-note")) == "lunch"
    page.click(sel("pay-submit"))
    page.wait_for_timeout(800)
    assert w.ada.me()["total"] == 9900
    assert page.query_selector(sel("pay-error")) is None
    assert len(page.query_selector_all("[data-testid^='activity-item-']")) == 1
    assert len({k for _, k in seen}) == 1
    page.fill(sel("pay-note"), "lunch 2")
    page.click(sel("pay-submit"))
    wait_attr(page, "wallet-balance", "data-amount", "9800")
    assert len({k for _, k in seen}) == 2


def test_lost_response_shows_uncertain_and_retry_moves_once(page):
    w = make_world()
    ui_login(page)
    page.goto("/")
    seen = posts(page, "/payments")
    state = {"lose": True}

    def handler(route):
        if route.request.method == "POST" and state["lose"]:
            route.fetch()          # the server commits the payment
            state["lose"] = False
            route.abort()          # ...but the browser never sees the response
        else:
            route.continue_()
    page.route(re.compile(r".*/payments$"), handler)
    fill_pay(page, amount="2.50", note="lost")
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"))
    assert text(page, "pay-uncertain") != ""
    assert page.query_selector(sel("pay-error")) is None
    assert w.ada.me()["total"] == 9750
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"), state="detached")
    assert page.query_selector(sel("pay-error")) is None
    wait_attr(page, "wallet-balance", "data-amount", "9750")
    assert len(seen) == 2 and seen[0] == seen[1], seen
    assert w.ada.me()["total"] == 9750
    assert len(page.query_selector_all("[data-testid^='activity-item-']")) == 1


def test_refused_after_another_client_spent(page):
    w = make_world()
    ui_login(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-balance"))
    assert pay(w.ada, "cy", 9990).status == 201      # another client drains the wallet
    fill_pay(page, amount="50.00", note="keep me", visibility="private")
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-error"))
    wait_attr(page, "wallet-balance", "data-amount", "10")
    assert page.input_value(sel("pay-handle")) == "bob"
    assert page.input_value(sel("pay-amount")) == "50.00"
    assert page.input_value(sel("pay-note")) == "keep me"
    assert page.input_value(sel("pay-visibility")) == "private"
    assert page.query_selector_all("[data-testid^='activity-item-']")  # the drain shows


def test_latest_refresh_wins(page):
    w = make_world()
    ui_login(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-balance"))
    held = []

    def hold_first(route):
        if not held:
            held.append((route, route.fetch()))  # old state, delivered late
        else:
            route.continue_()
    page.route(re.compile(r".*/me(\?.*)?$"), hold_first)
    page.fill(sel("pay-note"), "draft")
    page.click(sel("wallet-refresh"))
    page.wait_for_timeout(300)
    assert pay(w.ada, "bob", 100).status == 201
    page.click(sel("wallet-refresh"))
    wait_attr(page, "wallet-balance", "data-amount", "9900")
    route, resp = held[0]
    route.fulfill(response=resp)
    page.wait_for_timeout(800)
    assert page.get_attribute(sel("wallet-balance"), "data-amount") == "9900"
    assert page.get_attribute(sel("wallet-available"), "data-amount") == "9900"
    assert page.input_value(sel("pay-note")) == "draft"


def test_stale_pay_button_after_cancel_elsewhere(page):
    w = make_world()
    rid = ask(w.bob, "ada", 100).json()["request_id"]
    ui_login(page)
    page.goto("/requests")
    page.wait_for_selector(sel(f"request-pay-{rid}"))
    assert w.bob.post(f"/requests/{rid}/cancel", {}).status == 200
    page.click(sel(f"request-pay-{rid}"))
    page.wait_for_selector(sel("request-error"))
    page.wait_for_selector(sel(f"request-pay-{rid}"), state="detached")
    assert page.get_attribute(sel(f"request-item-{rid}"), "data-status") == "cancelled"
    assert w.ada.me()["total"] == 10000


def test_request_lists_placement_and_buttons(page):
    w = make_world()
    inc = ask(w.bob, "ada", 100).json()["request_id"]
    out = ask(w.ada, "cy", 200).json()["request_id"]
    done = ask(w.bob, "ada", 5).json()["request_id"]
    w.ada.post(f"/requests/{done}/decline", {})
    ui_login(page)
    page.goto("/requests")
    page.wait_for_selector(sel(f"request-item-{inc}"))
    assert page.query_selector(f"{sel('incoming-list')} {sel(f'request-item-{inc}')}")
    assert page.query_selector(f"{sel('outgoing-list')} {sel(f'request-item-{out}')}")
    assert page.query_selector(f"{sel('incoming-list')} {sel(f'request-item-{done}')}")
    assert page.get_attribute(sel(f"request-item-{done}"), "data-status") == "declined"
    assert page.query_selector(sel(f"request-pay-{done}")) is None
    assert page.query_selector(sel(f"request-cancel-{inc}")) is None
    assert page.query_selector(sel(f"request-pay-{out}")) is None
    assert text(page, f"request-amount-{out}") == money(200)
    page.click(sel(f"request-pay-{inc}"))
    wait_attr(page, f"request-item-{inc}", "data-status", "paid")
    assert page.query_selector(sel(f"request-pay-{inc}")) is None


def test_split_preview_matches_server(page):
    make_world()
    ui_login(page)
    page.goto("/split")
    seen = posts(page, "/splits")
    page.fill(sel("split-amount"), "10.00")
    page.fill(sel("split-handles"), "cy, ada, bob")
    page.fill(sel("split-note"), "pizza")
    page.wait_for_selector(sel("split-share-cy"))
    assert [text(page, f"split-share-{h}") for h in ("cy", "ada", "bob")] == \
        ["3.34 EUR", "3.33 EUR", "3.33 EUR"]
    assert seen == []
    with page.expect_response(lambda r: r.url.endswith("/splits") and r.request.method == "POST") as ri:
        page.click(sel("split-submit"))
    shares = ri.value.json()["shares"]
    assert [(s["handle"], s["amount"]) for s in shares] == [("cy", 334), ("ada", 333), ("bob", 333)]


def test_split_invalid_amount_sends_nothing(page):
    make_world()
    ui_login(page)
    page.goto("/split")
    seen = posts(page, "/splits")
    page.fill(sel("split-amount"), "1.001")
    page.fill(sel("split-handles"), "bob")
    page.click(sel("split-submit"))
    page.wait_for_selector(sel("split-error"))
    page.wait_for_timeout(300)
    assert seen == []


# ---- authorizations screen -------------------------------------------------------------------

def test_authorization_flow_on_screen(browser):
    w = make_world()
    ctx = browser.new_context(base_url=BASE, viewport={"width": 1280, "height": 900})
    ada, bob = ctx.new_page(), None
    ui_login(ada)
    ada.goto("/authorizations")
    ada.fill(sel("authorize-handle"), "bob")
    ada.fill(sel("authorize-amount"), "20.00")
    ada.fill(sel("authorize-note"), "deposit")
    ada.click(sel("authorize-submit"))
    ada.wait_for_selector("[data-testid^='authorization-item-']")
    aid = w.ada.get("/authorizations").json()["authorizations"][0]["authorization_id"]
    assert ada.get_attribute(sel(f"authorization-item-{aid}"), "data-status") == "open"
    assert text(ada, f"authorization-amount-{aid}") == money(2000)
    assert RFC3339.match(text(ada, f"authorization-expires-{aid}"))
    assert ada.query_selector(sel(f"authorization-void-{aid}"))
    assert ada.query_selector(sel(f"authorization-capture-{aid}")) is None
    assert ada.query_selector(sel(f"authorization-captured-{aid}")) is None
    ada.goto("/")
    assert ada.get_attribute(sel("wallet-available"), "data-amount") == "8000"
    assert ada.get_attribute(sel("wallet-held"), "data-amount") == "2000"
    ctx.close()
    ctx2 = browser.new_context(base_url=BASE, viewport={"width": 1280, "height": 900})
    bob = ctx2.new_page()
    ui_login(bob, "bob@example.com")
    bob.goto("/authorizations")
    bob.wait_for_selector(sel(f"authorization-capture-amount-{aid}"))
    assert bob.input_value(sel(f"authorization-capture-amount-{aid}")) in ("20.00", "20")
    assert bob.query_selector(sel(f"authorization-void-{aid}")) is None
    bob.fill(sel(f"authorization-capture-amount-{aid}"), "15.00")
    bob.click(sel(f"authorization-capture-{aid}"))
    wait_attr(bob, f"authorization-item-{aid}", "data-status", "captured")
    assert text(bob, f"authorization-captured-{aid}") == money(1500)
    assert bob.query_selector(sel(f"authorization-capture-{aid}")) is None
    ctx2.close()
    me = w.ada.me()
    assert (me["total"], me["held"]) == (8500, 0)
    w.conserved()


def test_authorize_insufficient_and_capture_refused(page):
    w = make_world()
    ui_login(page, "cy@example.com")
    page.goto("/authorizations")
    page.fill(sel("authorize-handle"), "bob")
    page.fill(sel("authorize-amount"), "5.01")
    page.click(sel("authorize-submit"))
    page.wait_for_selector(sel("authorize-error"))
    aid = authorize(w.ada, "cy", 100).json()["authorization_id"]
    page.goto("/authorizations")
    page.wait_for_selector(sel(f"authorization-capture-{aid}"))
    assert w.ada.post(f"/authorizations/{aid}/void", {}).status == 200  # voided elsewhere
    page.click(sel(f"authorization-capture-{aid}"))
    page.wait_for_selector(sel("authorization-error"))
    assert w.cy.me()["total"] == 500


def test_empty_states(page):
    make_world()
    ui_login(page, "cy@example.com")
    page.goto("/")
    page.wait_for_selector(sel("empty-activity"))
    page.goto("/requests")
    page.wait_for_selector(sel("empty-requests"))
    page.goto("/authorizations")
    page.wait_for_selector(sel("empty-authorizations"))


# ---- identity, navigation, layout -------------------------------------------------------------

def test_current_user_on_every_route_and_handle(page):
    make_world()
    ui_login(page)
    for r in ROUTES:
        page.goto(r)
        page.wait_for_selector(sel("current-user"))
        assert "Ada" in text(page, "current-user")
        assert text(page, "current-handle") == "ada"


def test_accept_negotiation():
    w = make_world()
    for path in ("/requests", "/authorizations"):
        h = call("GET", path, headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"})
        assert h.status == 200 and "text/html" in h.headers.get("content-type", ""), (path, h)
        j = call("GET", path, token=w.ada.token)
        assert "application/json" in j.headers.get("content-type", ""), (path, j)
        assert j.json() and "has_more" in j.json()


@pytest.mark.parametrize("width", [375, 1280])
def test_no_horizontal_scroll(browser, width):
    w = make_world()
    for i in range(6):
        pay(w.ada, "bob", i + 1, note="a fairly long note to stress the layout " * 3)
        ask(w.bob, "ada", 10 + i, note="n" * 150)
        authorize(w.ada, "bob", 10 + i, note="deposit for the flat rental agreement")
    ctx = browser.new_context(base_url=BASE, viewport={"width": width, "height": 800})
    pg = ctx.new_page()
    for r in ("/login", "/signup"):
        pg.goto(r)
        pg.wait_for_load_state("networkidle")
        sw = pg.evaluate("() => document.documentElement.scrollWidth")
        assert sw <= width, f"{r} at {width}px signed out: scrollWidth {sw}"
    ui_login(pg)
    for r in ROUTES:
        pg.goto(r)
        pg.wait_for_selector(sel("current-user"))
        pg.wait_for_load_state("networkidle")
        sw = pg.evaluate("() => document.documentElement.scrollWidth")
        assert sw <= width, f"{r} at {width}px: scrollWidth {sw}"
    ctx.close()


def test_no_request_to_other_hosts(browser):
    make_world()
    from urllib.parse import urlsplit
    host = urlsplit(BASE).netloc
    ctx = browser.new_context(base_url=BASE)
    pg = ctx.new_page()
    foreign = []
    pg.on("request", lambda r: urlsplit(r.url).netloc not in (host, "") and not r.url.startswith("data:")
          and foreign.append(r.url))
    for r in ("/login", "/signup"):
        pg.goto(r)
        pg.wait_for_load_state("networkidle")
    ui_login(pg)
    for r in ROUTES:
        pg.goto(r)
        pg.wait_for_load_state("networkidle")
    ctx.close()
    assert foreign == []


def test_import_keeps_browser_signed_in_and_retry_identity(page):
    """Import between browser requests: the page, its token and a pending lost-response retry
    survive a stage-2 export/import with no reload."""
    w = make_world()
    ui_login(page)
    page.goto("/")
    seen = posts(page, "/payments")
    state = {"lose": True}

    def handler(route):
        if route.request.method == "POST" and state["lose"]:
            route.fetch()
            state["lose"] = False
            route.abort()
        else:
            route.continue_()
    page.route(re.compile(r".*/payments$"), handler)
    fill_pay(page, amount="3.00", note="upgrade")
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"))
    snap = call("GET", "/_test/export").json()
    reset(fixture(users=[user("zed", 1)]))
    assert call("POST", "/_test/import", snap, timeout=30).status == 204
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"), state="detached")
    wait_attr(page, "wallet-balance", "data-amount", "9700")
    assert page.query_selector(sel("current-user"))
    assert seen[0] == seen[1]
    assert w.ada.me()["total"] == 9700
