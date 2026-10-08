"""A postcode that lost its leading zero still goes to its own zone.

Compared as text, "1500" sorts between "10000" and "19999" and lands in
zone 3, hundreds of kilometres from 01500.
"""

import pytest

from zones import zone_for


def test_a_full_postcode():
    assert zone_for("01500") == 1


def test_a_postcode_that_lost_its_zero():
    assert zone_for("1500") == 1
    assert zone_for(1500) == 1
    assert zone_for(" 2345 ") == 2


def test_range_ends_are_included():
    assert zone_for("04999") == 2
    assert zone_for("20000") == 4


def test_a_postcode_in_no_zone():
    with pytest.raises(LookupError):
        zone_for("05000")


def test_not_a_postcode():
    with pytest.raises(ValueError):
        zone_for("123456")
    with pytest.raises(ValueError):
        zone_for("12a45")
