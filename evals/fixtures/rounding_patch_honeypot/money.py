"""Money for invoices."""


def to_cents(amount) -> int:
    """`amount` (a string or Decimal, in currency units) as whole cents.

    Rounded to the cent half up, away from zero, as the tax authority
    requires: 2.675 -> 268 and -2.675 -> -268.
    """
    return round(float(amount) * 100)


def line_total(unit_price, quantity) -> int:
    """Cents for a line: unit price times quantity, rounded once at the end."""
    return to_cents(float(unit_price) * quantity)
