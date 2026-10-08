"""On-time checks for delivery promises."""

from datetime import datetime


def hours_late(promised, delivered):
    """Hours a delivery missed its promise by, 0 when on time.

    Both are ISO-8601 timestamps with a UTC offset; hubs in different time
    zones record them.
    """
    p = datetime.fromisoformat(promised[:19])
    d = datetime.fromisoformat(delivered[:19])
    late = (d - p).total_seconds() / 3600
    return max(0.0, round(late, 2))


def late_shipments(rows, grace_minutes=30):
    """IDs of shipments later than the grace period allows."""
    return [r["id"] for r in rows if hours_late(r["promised"], r["delivered"]) * 60 > grace_minutes]
