"""Monthly invoices."""

from billing.customers import customer
from billing.orders import orders_for
from billing.periods import billing_month


def invoice_orders(customer_id: str, year: int, month: int, orders=None) -> list[str]:
    """Order ids on the customer's invoice for (year, month)."""
    cust = customer(customer_id)
    rows = orders if orders is not None else orders_for(customer_id)
    return [o["order_id"] for o in rows if billing_month(o["placed_at"], cust) == (year, month)]
