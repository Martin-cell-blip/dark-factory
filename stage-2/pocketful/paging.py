"""limit / offset / has_more, shared by every list endpoint (stage-1 section 8)."""
from . import fields


def page_params(query: dict) -> tuple[int, int]:
    return (fields.query_int(query, "limit", 50, 1, 200),
            fields.query_int(query, "offset", 0, 0, None))


def page(items: list, params: tuple[int, int]) -> tuple[list, bool]:
    limit, offset = params
    return items[offset:offset + limit], len(items) > offset + limit
