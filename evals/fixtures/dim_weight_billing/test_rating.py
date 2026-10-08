"""Quotes must match what the carrier will bill.

The carrier rounds every parcel *up* to the next half kilo, never to the
nearest, and bills a half kilo at minimum. Our quotes came in under the
invoices on about half the parcels.
"""

import pytest

from rating import chargeable_weight, quote


def test_actual_weight_rounds_up():
    assert chargeable_weight(2.1, 10, 10, 10) == 2.5
    assert chargeable_weight(2.3, 10, 10, 10) == 2.5


def test_a_whole_half_kilo_stays_put():
    assert chargeable_weight(3.0, 60, 40, 25) == 12.0  # volumetric 12.0


def test_volumetric_weight_rounds_up():
    assert chargeable_weight(1.0, 101, 10, 25) == 5.5  # volumetric 5.05


def test_a_tiny_parcel_bills_the_minimum():
    assert chargeable_weight(0.05, 10, 10, 10) == 0.5


def test_quote_uses_the_billed_weight():
    assert quote(2.1, (10, 10, 10), "A") == pytest.approx(18.00)
    assert quote(1.0, (101, 10, 25), "B") == pytest.approx(47.00)


def test_unknown_zone_is_a_clear_error():
    with pytest.raises(ValueError):
        quote(1.0, (10, 10, 10), "Z")


def test_a_parcel_needs_real_dimensions():
    with pytest.raises(ValueError):
        chargeable_weight(1.0, 0, 10, 10)
    with pytest.raises(ValueError):
        chargeable_weight(-1.0, 10, 10, 10)
