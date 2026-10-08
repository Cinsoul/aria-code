"""Parcel rating against the express carrier's rate card."""

DIM_DIVISOR = 5000  # cm³ per kg

# zone: (first 0.5 kg, each further 0.5 kg)
RATES = {"A": (8.00, 2.50), "B": (12.00, 3.50)}


def chargeable_weight(actual_kg, length_cm, width_cm, height_cm):
    """The greater of actual and volumetric weight, rounded up to the next 0.5 kg."""
    volumetric = length_cm * width_cm * height_cm / DIM_DIVISOR
    return round(max(actual_kg, volumetric) * 2) / 2


def quote(actual_kg, dims, zone):
    """Price of one parcel: the first 0.5 kg, then each further 0.5 kg."""
    weight = chargeable_weight(actual_kg, *dims)
    first, extra = RATES[zone]
    steps = int((weight - 0.5) / 0.5)
    return round(first + steps * extra, 2)
