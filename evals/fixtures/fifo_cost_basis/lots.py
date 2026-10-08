"""Realized gains for the year-end tax pack."""

import csv
from pathlib import Path


def load(name="trades.csv"):
    with open(Path(__file__).parent / name, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def realized_gains(trades=None):
    """Realized gain or loss per symbol, matching sales to lots first in, first out."""
    trades = trades if trades is not None else load()
    qty, cost, gains = {}, {}, {}
    for t in trades:
        sym, q, price = t["symbol"], float(t["qty"]), float(t["price"])
        if t["side"] == "buy":
            qty[sym] = qty.get(sym, 0) + q
            cost[sym] = cost.get(sym, 0) + q * price
        else:
            avg = cost[sym] / qty[sym] if qty.get(sym) else 0
            gains[sym] = gains.get(sym, 0) + q * (price - avg)
            qty[sym] = qty.get(sym, 0) - q
            cost[sym] = cost.get(sym, 0) - q * avg
    return {sym: round(g, 2) for sym, g in gains.items()}
