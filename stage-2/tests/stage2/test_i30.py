"""Item 30: visible labels for every input; every control reachable by keyboard with a
visible focus indicator."""
import pytest

from holdfx import authorize, sel
from ui import log_in

UNLABELLED = """() => [...document.querySelectorAll('input, select, textarea')]
  .filter(el => el.type !== 'hidden')
  .filter(el => !el.labels || el.labels.length === 0
          || [...el.labels].every(l => l.offsetWidth === 0 || l.offsetHeight === 0
                                       || !l.textContent.trim()))
  .map(el => el.outerHTML)"""

FOCUS_STYLE = """() => {
  const el = document.activeElement;
  if (!el || el === document.body) return null;
  const s = getComputedStyle(el);
  return { tag: el.tagName, id: [...document.querySelectorAll('*')].indexOf(el),
           outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 2,
           shadow: s.boxShadow !== 'none' };
}"""

CONTROLS = """() => [...document.querySelectorAll('a[href], button, input, select')]
  .filter(el => !el.disabled && el.offsetParent !== null).length"""

SCREENS = ["/", "/requests", "/split", "/authorizations"]


@pytest.fixture
def data(world):
    authorize(world.ben, "ann", 500)
    authorize(world.ann, "ben", 300)
    world.ben.write("/requests", {"payer_handle": "ann", "amount": 100})
    return world


def _tab_through(page):
    """Tab once per control; each focused control must show a focus indicator."""
    count = page.evaluate(CONTROLS)
    reached = set()
    for _ in range(count + 2):
        page.keyboard.press("Tab")
        state = page.evaluate(FOCUS_STYLE)
        if state is None:
            continue
        assert state["outline"] or state["shadow"], state
        reached.add((state["tag"], state["id"]))
    return reached, count


@pytest.mark.parametrize("route", SCREENS)
def test_signed_in_screens(data, page, route):
    log_in(page)
    page.goto(route)
    page.wait_for_selector(sel("wallet-available") if route != "/split" else sel("split-submit"))
    page.wait_for_timeout(300)
    assert page.evaluate(UNLABELLED) == []
    reached, count = _tab_through(page)
    assert len(reached) >= count, (len(reached), count)


@pytest.mark.parametrize("route", ["/login", "/signup"])
def test_signed_out_screens(world, page, route):
    page.goto(route)
    page.wait_for_selector(sel(f"{route[1:]}-submit"))
    assert page.evaluate(UNLABELLED) == []
    reached, count = _tab_through(page)
    assert len(reached) >= count


def test_keyboard_only_payment(world, page):
    log_in(page)
    page.goto("/")
    page.wait_for_selector(sel("wallet-available"))
    page.focus(sel("pay-handle"))
    page.keyboard.type("ben")
    page.keyboard.press("Tab")
    page.keyboard.type("1.00")
    page.keyboard.press("Enter")
    page.wait_for_selector(f"{sel('wallet-balance')}[data-amount='9900']")
