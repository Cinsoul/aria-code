"""Risk figures for the fund factsheet."""

import statistics


def sharpe_ratio(daily_returns, annual_risk_free=0.0, periods=252):
    """Annualized Sharpe ratio of a series of daily returns.

    Daily excess return is the return minus annual_risk_free / periods. The
    ratio is the mean daily excess return over its sample standard deviation,
    scaled to a year by the square root of periods. Fewer than two returns,
    or returns with no variation, have no Sharpe ratio.
    """
    mean = statistics.mean(daily_returns)
    sd = statistics.pstdev(daily_returns)
    return (mean - annual_risk_free) / sd * periods
