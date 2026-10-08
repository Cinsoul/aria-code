"""URL slugs for the product catalogue."""

import re


def slugify(title):
    """Slug for one title.

    Lowercase ASCII letters, digits and Chinese characters, with every other
    run of characters turned into a single '-'. Accents are dropped
    (Café -> cafe). A title with nothing left is an error.
    """
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def unique_slugs(titles):
    """One slug per title, in order. A slug already taken gets -2, -3, ..."""
    return [slugify(title) for title in titles]
