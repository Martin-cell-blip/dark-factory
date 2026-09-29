"""Item 23: integer query parameters are plain decimal digits."""
from urllib.parse import quote

import pytest

from client import expect

BAD_LIMIT = ["1e9", "4.0", "+4", "-1", "0", "201", "abc", "", " 4", "4 ", "0x10", "٤"]
BAD_OFFSET = ["1e9", "4.0", "+4", "-1", "abc", "", "1.5"]


@pytest.mark.parametrize("path", ["/requests", "/activity"])
@pytest.mark.parametrize("value", BAD_LIMIT)
def test_bad_limit(world, path, value):
    expect(world.ann.get(f"{path}?limit={quote(value, safe='')}"), 422, "validation_failed")


@pytest.mark.parametrize("path", ["/requests", "/activity"])
@pytest.mark.parametrize("value", BAD_OFFSET)
def test_bad_offset(world, path, value):
    expect(world.ann.get(f"{path}?offset={quote(value, safe='')}"), 422, "validation_failed")


@pytest.mark.parametrize("path", ["/requests", "/activity"])
def test_good_values(world, path):
    for query in ("limit=1", "limit=200", "limit=007", "offset=0", "offset=99999999999999999999"):
        expect(world.ann.get(f"{path}?{query}"), 200)
