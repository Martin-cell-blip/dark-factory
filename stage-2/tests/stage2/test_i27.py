"""Item 27: upgrade. The service takes this team's stage-1 export; a browser signed in
before an export/import stays signed in, keeps its form and pending retry, and recovers."""
import json
from pathlib import Path

from client import Client, expect, request
from holdfx import sel
from ui import fill_form, open_home, posts, wait_amount

STAGE1 = json.loads((Path(__file__).resolve().parent / "upgrade" / "stage1_export.json")
                    .read_text(encoding="utf-8"))


def _import(document):
    expect(request("POST", "/_test/import", document, timeout=15), 204)


def _signed_in_as(page, token):
    page.add_init_script(f"localStorage.setItem('pocketful.token', {json.dumps(token)})")


def test_signed_in_browser_survives_the_upgrade(world, page):
    _import(STAGE1["export"])
    token = STAGE1["tokens"]["ann"]
    _signed_in_as(page, token)
    open_home(page)
    wait_amount(page, "wallet-balance", STAGE1["balances"]["ann"])
    sent = posts(page, "/payments")

    def lose(route):
        route.fetch()
        route.abort("connectionreset")
        page.unroute("**/payments", lose)

    page.route("**/payments", lose)
    fill_form(page, "pay", "ben", "10.00", note="before the upgrade")
    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-uncertain"))

    exported = expect(request("GET", "/_test/export"), 200).json()
    expect(request("POST", "/_test/reset", {"currency": "EUR", "minor_units": 2, "users": []}), 204)
    _import(exported)

    page.click(sel("pay-submit"))
    page.wait_for_selector(sel("pay-success"))
    wait_amount(page, "wallet-balance", STAGE1["balances"]["ann"] - 1000)
    assert page.query_selector(sel("pay-uncertain")) is None
    assert len(sent) == 2 and sent[0].headers["idempotency-key"] == sent[1].headers["idempotency-key"]
    assert Client(token).balance() == STAGE1["balances"]["ann"] - 1000

    rid = STAGE1["pending_request_id"]
    page.goto("/requests")
    page.click(sel(f"request-pay-{rid}"))
    page.wait_for_selector(f"{sel('request-item-' + rid)}[data-status='paid']")
    page.wait_for_selector(sel("current-user"))


def test_stage_one_replay_is_unchanged_across_the_upgrade(world):
    _import(STAGE1["export"])
    exported = expect(request("GET", "/_test/export"), 200).json()
    _import(exported)
    ann = Client(STAGE1["tokens"]["ann"])
    paid = STAGE1["payment"]
    replay = expect(ann.post("/payments", paid["body"], key=paid["key"]), 200).json()
    assert replay == paid["response"] and "authorization_id" not in replay
