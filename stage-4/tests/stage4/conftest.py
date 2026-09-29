"""Stage-4 checks: the stage-1 HTTP client and fixtures, the stage-3 time helpers and
upgrade sources."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "stage3"))
sys.path.insert(0, str(HERE.parent / "acceptance"))

import seed  # noqa: E402
from client import expect, login, request  # noqa: E402


def do_reset(fx: dict) -> None:
    expect(request("POST", "/_test/reset", fx, timeout=15), 204)


@pytest.fixture
def reset():
    return do_reset


@pytest.fixture
def world():
    """Ann (10000, a settlement operator), Ben (2500), Cat (500), all signed in."""
    fx = seed.fixture(settlement_operator_ids=["u_ann"])
    do_reset(fx)
    clients = {u["handle"]: login(u["email"], u["password"]) for u in fx["users"]}
    return SimpleNamespace(fixture=fx, total=seed.total(fx), **clients,
                           everyone=list(clients.values()))
