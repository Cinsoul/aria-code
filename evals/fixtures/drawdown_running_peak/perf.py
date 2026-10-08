"""Performance figures for the monthly portfolio letter."""


def max_drawdown(values):
    """Largest peak-to-trough fall, as a positive fraction (0.25 is -25%)."""
    peak = max(values)
    trough = min(values)
    return (peak - trough) / peak


def annualized_return(closes, periods_per_year=252):
    """Compound annual growth rate of a series of daily closes."""
    total = closes[-1] / closes[0]
    return total ** (periods_per_year / len(closes)) - 1
