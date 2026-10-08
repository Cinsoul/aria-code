"""The desk's VWAP benchmark: typical price, one figure per day."""

import pytest

from vwap import daily_vwap

BARS = [
    ("2026-10-05 09:30", 10.20, 10.00, 10.10, 1000),
    ("2026-10-05 10:00", 10.40, 10.10, 10.30, 3000),
    ("2026-10-05 10:30", 10.35, 10.15, 10.20, 0),
    ("2026-10-06 09:30", 11.00, 10.60, 10.90, 2000),
    ("2026-10-06 10:00", 11.10, 10.80, 11.00, 2000),
    ("2026-10-07 09:30", 11.20, 11.00, 11.10, 0),
]


def test_one_figure_per_day():
    assert set(daily_vwap(BARS)) == {"2026-10-05", "2026-10-06"}


def test_typical_price_weighted_by_volume():
    got = daily_vwap(BARS)
    assert got["2026-10-05"] == pytest.approx((10.10 * 1000 + 10.2666666667 * 3000) / 4000, abs=1e-6)
    assert got["2026-10-06"] == pytest.approx((10.8333333333 + 10.9666666667) / 2, abs=1e-6)


def test_a_day_with_no_volume_is_left_out():
    assert "2026-10-07" not in daily_vwap(BARS)
    assert daily_vwap([("2026-10-07 09:30", 11.2, 11.0, 11.1, 0)]) == {}
