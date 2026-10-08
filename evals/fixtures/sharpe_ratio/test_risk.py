"""The factsheet's Sharpe ratio, computed the way the auditors check it.

Volatility scales with the square root of time, not with time; the
risk-free rate is quoted per year; the standard deviation is the sample one.
"""

import pytest

from risk import sharpe_ratio

RETURNS = [0.004, -0.002, 0.006, 0.001, -0.003, 0.005, 0.002, -0.001, 0.003, 0.0015]


def test_without_a_risk_free_rate():
    assert sharpe_ratio(RETURNS) == pytest.approx(8.784006084, rel=1e-6)


def test_with_a_two_percent_risk_free_rate():
    assert sharpe_ratio(RETURNS, annual_risk_free=0.02) == pytest.approx(8.361494969, rel=1e-6)


def test_no_ratio_without_enough_data():
    with pytest.raises(ValueError):
        sharpe_ratio([0.01])
    with pytest.raises(ValueError):
        sharpe_ratio([0.01, 0.01, 0.01])
