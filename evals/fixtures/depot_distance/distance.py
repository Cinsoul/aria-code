"""Which depot serves a delivery address."""

import csv
from math import asin, cos, sin, sqrt
from pathlib import Path

EARTH_RADIUS_KM = 6371.0


def load(name="depots.csv"):
    """Depots as {name: (lat, lon)} in degrees."""
    with open(Path(__file__).parent / name, newline="", encoding="utf-8") as fh:
        rows = csv.reader(fh)
        next(rows)
        return {r[0]: (float(r[1]), float(r[2])) for r in rows}


def distance_km(a, b):
    """Great-circle distance between two (lat, lon) points given in degrees.

    Haversine formula, Earth radius 6371 km.
    """
    lat1, lon1 = a
    lat2, lon2 = b
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def nearest_depot(point):
    """Name of the depot closest to a (lat, lon) point."""
    depots = load()
    return min(depots, key=lambda name: distance_km(point, depots[name]))
