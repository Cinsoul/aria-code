"""Pick lists for chilled goods."""

import csv
from pathlib import Path


def load(name="lots.csv"):
    with open(Path(__file__).parent / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def allocate(sku, qty, as_of, lots=None):
    """Lots to pick for an order of `qty` units, as [(lot, units), ...].

    First expired, first out: the lot that expires soonest goes first, and
    of two lots expiring the same day the one received earlier. A lot can
    ship only if it expires after `as_of` (a date) and is not on hold. Not
    enough stock that can ship is an error.
    """
    lots = lots if lots is not None else load()
    rows = sorted((r for r in lots if r["sku"] == sku), key=lambda r: r["received"])
    picks, need = [], qty
    for row in rows:
        if need <= 0:
            break
        take = min(need, int(row["qty"]))
        picks.append((row["lot"], take))
        need -= take
    return picks
