"""Orders as the web shop records them: `placed_at` is UTC, ISO 8601."""

ORDERS = [
    {"order_id": "O-1001", "customer_id": "C-PACIFIC", "placed_at": "2026-09-30T18:00:00Z"},
    {"order_id": "O-1002", "customer_id": "C-PACIFIC", "placed_at": "2026-10-01T05:40:00Z"},
    {"order_id": "O-1003", "customer_id": "C-PACIFIC", "placed_at": "2026-10-15T20:00:00Z"},
    {"order_id": "O-2001", "customer_id": "C-LONDON", "placed_at": "2026-09-30T23:30:00Z"},
    {"order_id": "O-2002", "customer_id": "C-LONDON", "placed_at": "2026-10-10T12:00:00Z"},
    {"order_id": "O-3001", "customer_id": "C-SHANGHAI", "placed_at": "2026-09-30T17:00:00Z"},
]


def orders_for(customer_id: str) -> list[dict]:
    return [o for o in ORDERS if o["customer_id"] == customer_id]
