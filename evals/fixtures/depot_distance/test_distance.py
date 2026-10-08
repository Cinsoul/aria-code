"""Addresses go to the nearest depot.

The formula works in radians. The depot file lists longitude before
latitude, as the mapping tool exports it.
"""

import pytest

from distance import distance_km, load, nearest_depot


def test_shanghai_to_beijing():
    assert distance_km((31.2304, 121.4737), (39.9042, 116.4074)) == pytest.approx(1067.3, abs=1.0)


def test_the_depot_file_is_read_as_lat_lon():
    assert load()["SHA"] == pytest.approx((31.2304, 121.4737))


def test_shenzhen_goes_to_guangzhou():
    assert nearest_depot((22.5431, 114.0579)) == "CAN"


def test_chengdu_suburbs_go_to_chengdu():
    assert nearest_depot((30.66, 103.95)) == "CTU"


def test_tianjin_goes_to_beijing():
    assert nearest_depot((39.0842, 117.2009)) == "PEK"
