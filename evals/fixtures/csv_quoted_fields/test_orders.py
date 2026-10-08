"""The export is real CSV: customer names hold commas, product names hold
quotes, and delivery notes run over several lines. A row that comes out the
wrong width is a corrupt import, not something to trim to fit.
"""

import pytest

from orders import load_orders, parse_line


def test_plain_line():
    assert parse_line("1,A-100,3") == ["1", "A-100", "3"]


def test_a_quoted_field_keeps_its_comma():
    assert parse_line('2,"Acme, Inc.",5') == ["2", "Acme, Inc.", "5"]


def test_a_doubled_quote_is_one_quote():
    assert parse_line('3,"27"" monitor",1') == ["3", '27" monitor', "1"]


def test_a_note_can_span_lines():
    text = 'id,sku,note\n1,A-100,"leave at\nthe back door"\n2,B-200,\n'
    orders = load_orders(text)
    assert [o["id"] for o in orders] == ["1", "2"]
    assert orders[0]["note"] == "leave at\nthe back door"


def test_a_short_row_is_rejected_not_truncated():
    with pytest.raises(ValueError):
        load_orders("id,sku,qty\n1,A-100\n")
