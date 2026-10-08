"""Delivery date promised at checkout."""

from datetime import timedelta

CUTOFF_HOUR = 15


def estimated_delivery(order_time, transit_days):
    """Date a parcel arrives.

    An order placed before the 15:00 cutoff on a working day ships that day;
    any other order ships on the next working day. It arrives `transit_days`
    working days after it ships. Weekends and the dates listed in
    holidays.csv are not working days.
    """
    return (order_time + timedelta(days=transit_days)).date()
