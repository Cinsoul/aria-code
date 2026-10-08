"""Each shipment once, and a looping API is an error, not a hang."""

import pytest

from client import fetch_all


class FakeApi:
    def __init__(self, pages, max_calls=50):
        self.pages = pages          # cursor -> (items, next)
        self.calls = 0
        self.max_calls = max_calls

    def __call__(self, cursor, limit):
        self.calls += 1
        if self.calls > self.max_calls:
            raise AssertionError("fetch_all kept paging: it never noticed the loop")
        items, nxt = self.pages[cursor]
        return {"items": [{"id": i} for i in items], "next": nxt}


def ids(items):
    return [item["id"] for item in items]


def test_three_pages():
    api = FakeApi({None: ([1, 2], "b"), "b": ([3, 4], "c"), "c": ([5], None)})
    assert ids(fetch_all(api)) == [1, 2, 3, 4, 5]


def test_an_empty_first_page():
    assert fetch_all(FakeApi({None: ([], None)})) == []


def test_a_repeated_item_appears_once():
    api = FakeApi({None: ([1, 2], "b"), "b": ([2, 3], "c"), "c": ([3, 4], None)})
    assert ids(fetch_all(api)) == [1, 2, 3, 4]


def test_a_looping_cursor_is_an_error():
    api = FakeApi({None: ([1], "b"), "b": ([2], "c"), "c": ([3], "b")})
    with pytest.raises(RuntimeError):
        fetch_all(api)
