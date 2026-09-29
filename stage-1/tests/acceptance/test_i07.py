"""Item 7: signup, derived handles and signup errors."""
import pytest

from client import Client, expect, request

PASSWORD = "correct horse"


def _signup(email, password=PASSWORD, name="New"):
    return request("POST", "/auth/signup",
                   {"email": email, "password": password, "display_name": name})


def test_signup_returns_201_and_a_working_token(world):
    body = expect(_signup("Zoe.Q@example.com", name="Zoë"), 201).json()
    assert set(body) >= {"user_id", "display_name", "token"}
    assert body["display_name"] == "Zoë"
    me = expect(Client(body["token"]).get("/me"), 200).json()
    assert me["user_id"] == body["user_id"]
    assert me["handle"] == "zoe_q" and me["balance"] == 0


@pytest.mark.parametrize("email,handle", [
    ("MiXeD@example.com", "mixed"),
    ("a-b+c@example.com", "a_b_c"),
    ("under_score9@example.com", "under_score9"),
    ("abcdefghijklmnopqrstuvwxyz@example.com", "abcdefghijklmnopqrst"),
    ("josé@example.com", "jos_"),
])
def test_handle_is_derived_from_the_local_part(world, email, handle):
    token = expect(_signup(email), 201).json()["token"]
    assert Client(token).get("/me").json()["handle"] == handle


def test_email_taken(world):
    expect(_signup("dup@example.com"), 201)
    expect(_signup("dup@example.com"), 409, "email_taken")


def test_short_password_and_bad_email(world):
    expect(_signup("short@example.com", password="1234567"), 422, "validation_failed")
    for email in ("no-at-sign", "@example.com", "local@", "a@b@c", ""):
        expect(_signup(email), 422, "validation_failed")


def test_handle_taken_creates_no_account(world):
    expect(_signup("ann@elsewhere.test"), 409, "handle_taken")
    expect(request("POST", "/auth/login", {"email": "ann@elsewhere.test",
                                           "password": PASSWORD}), 401)
    expect(_signup("ann@elsewhere.test"), 409, "handle_taken")


def test_new_users_can_receive_and_be_asked_immediately(world):
    token = expect(_signup("fresh@example.com"), 201).json()["token"]
    fresh = Client(token)
    expect(world.ann.write("/requests", {"payer_handle": "fresh", "amount": 50}), 201)
    expect(world.ann.write("/payments", {"to_handle": "fresh", "amount": 70}), 201)
    assert fresh.balance() == 70
    assert len(fresh.get("/requests?direction=incoming").json()["requests"]) == 1
