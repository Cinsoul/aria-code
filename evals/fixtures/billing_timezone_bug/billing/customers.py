"""Customer master data. `tz` is the IANA time zone the customer's account is managed in."""

CUSTOMERS = {
    "C-PACIFIC": {"name": "Pacific Pantry", "tz": "America/Los_Angeles"},
    "C-LONDON": {"name": "Thames Provisions", "tz": "Europe/London"},
    "C-SHANGHAI": {"name": "Pudong Fresh", "tz": "Asia/Shanghai"},
}


def customer(customer_id: str) -> dict:
    return CUSTOMERS[customer_id]
