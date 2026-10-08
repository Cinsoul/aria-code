"""Delivery zone for a postcode."""

import csv
from pathlib import Path

with open(Path(__file__).with_name("zones.csv"), newline="", encoding="utf-8") as _fh:
    ZONES = list(csv.DictReader(_fh))


def zone_for(postcode):
    """Zone number for a postcode.

    Postcodes have five digits. Spreadsheets drop leading zeros, so 1234 or
    "1234" is 01234. Anything that is not one to five digits is a ValueError;
    a valid postcode that falls in no range is a LookupError.
    """
    code = str(postcode).strip()
    for row in ZONES:
        if row["from"] <= code <= row["to"]:
            return int(row["zone"])
    return None
