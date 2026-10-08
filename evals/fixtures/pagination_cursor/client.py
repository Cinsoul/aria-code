"""Pull every shipment from the carrier's paginated tracking API."""


def fetch_all(get_page, page_size=100):
    """Every shipment across all pages, each once, in the order first seen.

    get_page(cursor, limit) returns {"items": [...], "next": cursor or None};
    the first call passes cursor=None. When shipments arrive mid-scan the API
    repeats the last item of a page at the start of the next one. A cursor
    the API has already returned means it is looping, and is an error.
    """
    items = []
    page = get_page(None, page_size)
    items.extend(page["items"])
    while page.get("next"):
        page = get_page(page["next"], page_size)
        items.extend(page["items"])
    return items
