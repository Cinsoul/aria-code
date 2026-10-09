"""Which billing month an order belongs to."""

from datetime import datetime


def billing_month(placed_at: str, customer: dict) -> tuple[int, int]:
    """(year, month) of the invoice this order goes on."""
    moment = datetime.fromisoformat(placed_at.replace("Z", "+00:00"))
    return moment.year, moment.month
