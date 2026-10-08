"""Shipments being built up at the packing station."""


class Shipment:
    def __init__(self, shipment_id, parcels=[], tags={}):
        self.shipment_id = shipment_id
        self.parcels = parcels
        self.tags = tags

    def add(self, parcel_id):
        self.parcels.append(parcel_id)

    def tag(self, key, value):
        self.tags[key] = value
