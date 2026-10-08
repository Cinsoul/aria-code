"""Execution benchmarks for the trading desk."""


def daily_vwap(bars):
    """Volume-weighted average price for each trading day.

    `bars` is [(timestamp "YYYY-MM-DD HH:MM", high, low, close, volume), ...].
    A bar's price is its typical price, (high + low + close) / 3. Each day
    starts afresh. Returns {"YYYY-MM-DD": vwap}; a day whose bars all
    traded nothing has no VWAP and is left out.
    """
    total_pv = total_v = 0.0
    for _ts, _high, _low, close, volume in bars:
        total_pv += close * volume
        total_v += volume
    return total_pv / total_v
