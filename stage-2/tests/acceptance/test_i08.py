"""Item 8: login, wrong credentials, multiple concurrent tokens."""
import seed
from client import Client, expect, request


def _login(email, password):
    return request("POST", "/auth/login", {"email": email, "password": password})


def test_login_returns_200_with_token(world):
    body = expect(_login("ann@pocket.test", seed.PASSWORD), 200).json()
    assert body["user_id"] == "u_ann" and body["display_name"] == "Ann"
    assert isinstance(body["token"], str) and body["token"]


def test_wrong_password_or_unknown_email_is_401(world):
    expect(_login("ann@pocket.test", "wrong password"), 401, "unauthenticated")
    expect(_login("nobody@pocket.test", seed.PASSWORD), 401, "unauthenticated")


def test_several_tokens_are_valid_together(world):
    tokens = [expect(_login("ann@pocket.test", seed.PASSWORD), 200).json()["token"]
              for _ in range(3)]
    assert len(set(tokens)) == 3
    for token in tokens + [world.ann.token]:
        expect(Client(token).get("/me"), 200)


def test_signup_token_and_login_token_both_work(world):
    signup = expect(request("POST", "/auth/signup", {"email": "two@example.com",
                                                     "password": "password!",
                                                     "display_name": "Two"}), 201).json()
    login = expect(_login("two@example.com", "password!"), 200).json()
    assert signup["user_id"] == login["user_id"]
    expect(Client(signup["token"]).get("/me"), 200)
    expect(Client(login["token"]).get("/me"), 200)
