"""First in, first out — the method the tax pack is filed under.

Average cost gives the same answer only once a position is fully closed.
AAA is not: 10 shares bought at 16.00 are still held. The broker export is
not in date order either: CCC's buy is listed after its sale.
"""

import pytest

from lots import realized_gains


def test_aaa_matches_the_oldest_lots_first():
    # 3 Mar: 100 @ 10 + 20 @ 16 sold at 20  -> +1080
    # 5 May: 20 @ 16 sold at 12             ->   -80
    assert realized_gains()["AAA"] == pytest.approx(1000.00)


def test_a_partial_sale():
    assert realized_gains()["BBB"] == pytest.approx(-20.00)


def test_trades_are_matched_in_date_order():
    assert realized_gains()["CCC"] == pytest.approx(30.00)


def test_a_sale_can_span_lots():
    trades = [
        {"date": "2025-01-01", "side": "buy", "symbol": "X", "qty": "10", "price": "1"},
        {"date": "2025-01-02", "side": "buy", "symbol": "X", "qty": "10", "price": "2"},
        {"date": "2025-01-03", "side": "sell", "symbol": "X", "qty": "5", "price": "3"},
        {"date": "2025-01-04", "side": "sell", "symbol": "X", "qty": "10", "price": "3"},
    ]
    assert realized_gains(trades)["X"] == pytest.approx(25.00)


def test_selling_more_than_is_held_is_an_error():
    trades = [
        {"date": "2025-01-01", "side": "buy", "symbol": "X", "qty": "5", "price": "1"},
        {"date": "2025-01-02", "side": "sell", "symbol": "X", "qty": "6", "price": "2"},
    ]
    with pytest.raises(ValueError):
        realized_gains(trades)
