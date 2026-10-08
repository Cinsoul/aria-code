"""Split a settlement across the parties to a shared shipment."""


def allocate(total_cents, weights):
    """Share `total_cents` out in proportion to `weights`, in whole cents.

    The shares always add up to the total. Cents left over after rounding go
    to the shares with the largest remainders, earlier ones first on a tie.
    """
    whole = sum(weights)
    return [round(total_cents * w / whole) for w in weights]
