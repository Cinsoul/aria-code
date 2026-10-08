"""Chilled stock leaves in expiry order, and never past it.

Received order is not expiry order: L2 came in after L1 and L3 but expires
first. L3 expires on the ship date itself and L4 is on quality hold, so
neither can go.
"""

from datetime import date

import pytest

from picking import allocate

SHIP = date(2026, 10, 8)


def test_soonest_expiry_first_then_earliest_received():
    assert allocate("MILK", 60, SHIP) == [("L2", 30), ("L6", 5), ("L1", 25)]


def test_everything_that_can_ship():
    assert allocate("MILK", 125, SHIP) == [("L2", 30), ("L6", 5), ("L1", 40), ("L5", 50)]


def test_expired_and_held_stock_does_not_count():
    with pytest.raises(ValueError):
        allocate("MILK", 126, SHIP)


def test_a_lot_expiring_on_the_ship_date_cannot_go():
    with pytest.raises(ValueError):
        allocate("YOG", 5, date(2026, 10, 15))
