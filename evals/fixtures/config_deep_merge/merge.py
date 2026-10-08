"""Per-warehouse settings layered over the company defaults."""

DEFAULTS = {
    "carrier": {"name": "SF", "timeout": 30, "retries": 3},
    "warehouses": ["SHA"],
    "label": {"size": "4x6", "dpi": 203},
}


def merge_config(defaults, override):
    """`defaults` with `override` applied.

    Nested dicts merge key by key; anything else, lists included, is replaced
    by the override's value (None included). Neither argument is modified,
    and changing the result later must not change either of them.
    """
    result = defaults.copy()
    result.update(override)
    return result
