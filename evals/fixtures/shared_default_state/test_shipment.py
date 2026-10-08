"""Parcels packed into one shipment turn up in the next one.

Each shipment owns its parcel list and its tags. That includes a list the
caller passed in: the packing station keeps using its own list afterwards.
"""

from shipment import Shipment


def test_a_new_shipment_starts_empty():
    first = Shipment("S1")
    first.add("P1")
    second = Shipment("S2")
    assert second.parcels == []


def test_tags_belong_to_one_shipment():
    first = Shipment("S1")
    first.tag("hazmat", True)
    assert Shipment("S2").tags == {}


def test_the_callers_list_is_left_alone():
    scanned = ["P1"]
    shipment = Shipment("S3", scanned)
    shipment.add("P2")
    assert shipment.parcels == ["P1", "P2"]
    assert scanned == ["P1"]


def test_the_callers_tags_are_left_alone():
    defaults = {"service": "standard"}
    shipment = Shipment("S4", tags=defaults)
    shipment.tag("service", "express")
    assert shipment.tags == {"service": "express"}
    assert defaults == {"service": "standard"}
