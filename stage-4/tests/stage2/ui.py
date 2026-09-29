"""Browser helpers for the screen checks. Elements are found only by data-testid."""
import seed
from holdfx import sel

ROUTES = ["/", "/requests", "/split", "/authorizations"]


def log_in(page, handle: str = "ann", password: str = seed.PASSWORD) -> None:
    page.goto("/login")
    page.fill(sel("login-email"), f"{handle}@pocket.test")
    page.fill(sel("login-password"), password)
    page.click(sel("login-submit"))
    page.wait_for_selector(sel("current-user"))


def amount_of(page, testid: str) -> int:
    return int(page.get_attribute(sel(testid), "data-amount"))


def wait_amount(page, testid: str, minor: int) -> None:
    page.wait_for_selector(f"{sel(testid)}[data-amount='{minor}']")


def fill_form(page, prefix: str, handle: str, amount: str, note: str = "",
              visibility: str | None = None) -> None:
    page.fill(sel(f"{prefix}-handle"), handle)
    page.fill(sel(f"{prefix}-amount"), amount)
    page.fill(sel(f"{prefix}-note"), note)
    if visibility:
        page.select_option(sel(f"{prefix}-visibility"), visibility)


def open_home(page) -> None:
    page.goto("/")
    page.wait_for_selector(sel("wallet-available"))


def pay(page, handle: str = "ben", amount: str = "15.00", note: str = "",
        visibility: str | None = None) -> None:
    open_home(page)
    fill_form(page, "pay", handle, amount, note, visibility)
    page.click(sel("pay-submit"))


def text(page, testid: str) -> str:
    return page.text_content(sel(testid)).strip()


def child_testids(page, container: str, prefix: str) -> list[str]:
    ids = page.eval_on_selector_all(f"{sel(container)} > *",
                                    "els => els.map(e => e.getAttribute('data-testid'))")
    return [i for i in ids if i and i.startswith(prefix)]


def posts(page, path_suffix: str) -> list:
    """Record every request whose URL ends with path_suffix (method, headers, body)."""
    seen = []
    page.on("request", lambda r: seen.append(r) if r.url.split("?")[0].endswith(path_suffix)
            and r.method == "POST" else None)
    return seen
