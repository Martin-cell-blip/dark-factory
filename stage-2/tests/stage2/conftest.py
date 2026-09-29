"""Stage-2 checks: the stage-1 HTTP client and fixtures, plus a Playwright browser for screens."""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "acceptance"))

import seed  # noqa: E402
from client import BASE_URL, expect, login, request  # noqa: E402


def do_reset(fx: dict) -> None:
    expect(request("POST", "/_test/reset", fx, timeout=15), 204)


@pytest.fixture
def reset():
    return do_reset


@pytest.fixture
def world():
    """Ann (10000), Ben (2500) and Cat (500), EUR with 2 minor units, all signed in."""
    fx = seed.fixture()
    do_reset(fx)
    clients = {u["handle"]: login(u["email"], u["password"]) for u in fx["users"]}
    return SimpleNamespace(fixture=fx, total=seed.total(fx), **clients,
                           everyone=list(clients.values()))


# ---- browser ------------------------------------------------------------------------

@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as playwright:
        chromium = playwright.chromium.launch()
        yield chromium
        chromium.close()


def _new_page(browser, width: int, height: int):
    context = browser.new_context(base_url=BASE_URL, viewport={"width": width,
                                                              "height": height})
    context.set_default_timeout(int(os.environ.get("POCKETFUL_UI_TIMEOUT_MS", "8000")))
    return context, context.new_page()


@pytest.fixture
def page(browser):
    context, page = _new_page(browser, 1280, 900)
    yield page
    context.close()


@pytest.fixture
def phone(browser):
    context, page = _new_page(browser, 375, 812)
    yield page
    context.close()


@pytest.fixture
def new_page(browser):
    """Extra pages (a second browser, another width); all closed after the test."""
    contexts = []

    def make(width: int = 1280, height: int = 900):
        context, page = _new_page(browser, width, height)
        contexts.append(context)
        return page

    yield make
    for context in contexts:
        context.close()
