"""Operator input is data: quotes, '%' and '_' included."""

import pytest

from inventory_db import connect, find_by_name, search

ROWS = [
    ("A1", "O'Brien Mug", 5),
    ("A2", "50% off bundle", 1),
    ("A3", "500 units pallet", 2),
    ("A4", "tape_roll", 3),
    ("A5", "tapeXroll", 4),
    ("A6", "Mug", 9),
]


@pytest.fixture
def con():
    return connect(ROWS)


def test_exact_name(con):
    assert find_by_name(con, "Mug") == ["A6"]


def test_a_name_with_a_quote(con):
    assert find_by_name(con, "O'Brien Mug") == ["A1"]


def test_input_cannot_rewrite_the_query(con):
    assert find_by_name(con, "x' OR '1'='1") == []


def test_search_ignores_case(con):
    assert search(con, "o'b") == ["A1"]


def test_percent_is_a_percent(con):
    assert search(con, "50%") == ["A2"]


def test_underscore_is_an_underscore(con):
    assert search(con, "_") == ["A4"]
