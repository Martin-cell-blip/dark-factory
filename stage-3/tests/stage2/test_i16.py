"""Item 16: signup, login, errors, the signed-in person on every screen, logout."""
import seed
from holdfx import sel
from ui import ROUTES, log_in, text


def test_signup_signs_in_with_the_derived_handle(world, page):
    page.goto("/signup")
    for testid in ("signup-email", "signup-password", "signup-display-name", "signup-submit"):
        page.wait_for_selector(sel(testid))
    assert page.query_selector(sel("auth-error")) is None
    page.fill(sel("signup-email"), "Zoe.Q@example.com")
    page.fill(sel("signup-password"), "long enough 1")
    page.fill(sel("signup-display-name"), "Zoë Quinn")
    page.click(sel("signup-submit"))
    page.wait_for_selector(sel("current-user"))
    assert "Zoë Quinn" in text(page, "current-user")
    assert page.text_content(sel("current-handle")) == "zoe_q"


def test_auth_errors_appear_only_on_error(world, page):
    page.goto("/login")
    assert page.query_selector(sel("auth-error")) is None
    page.fill(sel("login-email"), "ann@pocket.test")
    page.fill(sel("login-password"), "not the password")
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("auth-error"))
    page.goto("/signup")
    assert page.query_selector(sel("auth-error")) is None
    page.fill(sel("signup-email"), "ann@pocket.test")
    page.fill(sel("signup-password"), "long enough 1")
    page.fill(sel("signup-display-name"), "Ann again")
    page.click(sel("signup-submit"))
    page.wait_for_selector(sel("auth-error"))
    page.fill(sel("signup-email"), "short@pocket.test")
    page.fill(sel("signup-password"), "short")
    page.click(sel("signup-submit"))
    page.wait_for_selector(sel("auth-error"))


def test_current_user_on_every_screen(world, page):
    log_in(page, "ben")
    for route in ROUTES + ["/login", "/signup"]:
        page.goto(route)
        page.wait_for_selector(sel("current-user"))
        assert page.is_visible(sel("current-user"))
        assert "Ben" in text(page, "current-user")
        assert page.text_content(sel("current-handle")) == "ben"


def test_logout_signs_out(world, page):
    log_in(page)
    page.click(sel("logout-button"))
    page.wait_for_selector(sel("login-submit"))
    assert page.query_selector(sel("current-user")) is None
    page.goto("/")
    page.wait_for_selector(sel("login-submit"))
    log_in(page, "cat", seed.PASSWORD)
    assert page.text_content(sel("current-handle")) == "cat"
