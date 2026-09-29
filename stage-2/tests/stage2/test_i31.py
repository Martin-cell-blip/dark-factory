"""Item 31: every runtime asset comes from the service; no other host is contacted."""
from urllib.parse import urlsplit

from client import BASE_URL
from holdfx import sel
from ui import ROUTES, log_in


def test_every_route_loads_only_from_the_service(world, page):
    origin = urlsplit(BASE_URL).netloc
    seen = []
    page.on("request", lambda r: seen.append(r.url))
    failed = []
    page.on("requestfailed", lambda r: failed.append(r.url))
    for route in ("/login", "/signup"):
        page.goto(route)
        page.wait_for_load_state("networkidle")
    log_in(page)
    for route in ROUTES:
        page.goto(route)
        page.wait_for_selector(sel("current-user"))
        page.wait_for_load_state("networkidle")
    others = [url for url in seen if urlsplit(url).scheme in ("http", "https")
              and urlsplit(url).netloc != origin]
    assert others == []
    assert failed == []
    assert any(url.endswith(".css") for url in seen) and any(url.endswith(".js") for url in seen)
