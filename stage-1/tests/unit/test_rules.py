"""In-process checks of the single-place rules: amounts, splits, query integers, JSON."""
import pytest

from pocketful import fields, jsonio
from pocketful.errors import ApiError
from pocketful.money import equal_split


@pytest.mark.parametrize("amount,n,expected", [
    (1000, 3, [334, 333, 333]), (1, 3, [1, 0, 0]), (10, 3, [4, 3, 3]),
    (999, 3, [333, 333, 333]), (5, 5, [1, 1, 1, 1, 1]), (7, 1, [7]),
])
def test_equal_split(amount, n, expected):
    assert equal_split(amount, n) == expected


def test_equal_split_always_sums():
    for amount in range(1, 200):
        for n in range(1, 12):
            shares = equal_split(amount, n)
            assert sum(shares) == amount and max(shares) - min(shares) <= 1
            assert shares == sorted(shares, reverse=True)


@pytest.mark.parametrize("value", [1, 1000, 1000.0, 1e3, 1000000000])
def test_amount_accepts_integral_numbers(value):
    assert fields.amount_value(value) == int(value)
    assert isinstance(fields.amount_value(value), int)


@pytest.mark.parametrize("value", [True, False, None, "5", 0, -1, 1.5, float("inf"),
                                   float("nan"), 1000000001, [], {}])
def test_amount_rejects_everything_else(value):
    with pytest.raises(ApiError) as error:
        fields.amount_value(value)
    assert (error.value.status, error.value.code) == (422, "validation_failed")


@pytest.mark.parametrize("raw,value", [("5", 5), ("007", 7), ("200", 200)])
def test_query_int_digits(raw, value):
    assert fields.query_int({"limit": raw}, "limit", 50, 1, 200) == value


@pytest.mark.parametrize("raw", ["1e9", "4.0", "+4", "-1", "0", "201", "", "٤", " 4"])
def test_query_int_rejects(raw):
    with pytest.raises(ApiError):
        fields.query_int({"limit": raw}, "limit", 50, 1, 200)


@pytest.mark.parametrize("email,handle", [
    ("Ann.Lee@x.io", "ann_lee"), ("a+b-c@x", "a_b_c"), ("x" * 30 + "@y", "x" * 20),
])
def test_derive_handle(email, handle):
    assert fields.derive_handle(email) == handle
    assert fields.is_handle(handle)


def test_canonical_ignores_order_whitespace_and_number_spelling():
    a = jsonio.parse(b'{"a": 1000, "b": [1, {"c": "x"}]}')
    b = jsonio.parse(b'{ "b" : [1.0, {"c":"x"}], "a": 1e3 }')
    assert jsonio.canonical(a) == jsonio.canonical(b)
    assert jsonio.canonical({"v": True}) != jsonio.canonical({"v": 1})
    assert jsonio.canonical({}) != jsonio.canonical({"visibility": "public"})


@pytest.mark.parametrize("raw", [b"NaN", b'{"a": Infinity}', b'"\\ud800"', b"\xff", b"{"])
def test_parse_rejects_non_json(raw):
    with pytest.raises(ApiError) as error:
        jsonio.parse(raw)
    assert error.value.code == "malformed_request"
