"""The checkout date must be one the warehouse and carrier can keep.

Orders at 15:00 sharp have missed the cutoff. Nothing ships or moves on a
weekend or a holiday in holidays.csv.
"""

from datetime import date, datetime

from eta import estimated_delivery


def test_a_midweek_order():
    assert estimated_delivery(datetime(2026, 10, 6, 10, 0), 2) == date(2026, 10, 8)


def test_after_cutoff_on_friday_ships_monday():
    assert estimated_delivery(datetime(2026, 10, 9, 16, 0), 1) == date(2026, 10, 13)


def test_the_cutoff_itself_is_too_late():
    assert estimated_delivery(datetime(2026, 10, 6, 15, 0), 0) == date(2026, 10, 7)


def test_a_weekend_order_ships_monday():
    assert estimated_delivery(datetime(2026, 10, 10, 9, 0), 0) == date(2026, 10, 12)


def test_transit_skips_a_holiday_and_the_weekend():
    assert estimated_delivery(datetime(2026, 12, 24, 10, 0), 1) == date(2026, 12, 28)


def test_an_order_on_a_holiday():
    assert estimated_delivery(datetime(2027, 1, 1, 9, 0), 1) == date(2027, 1, 5)
