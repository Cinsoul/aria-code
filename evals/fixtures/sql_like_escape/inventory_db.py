"""Lookups against the warehouse item master."""

import sqlite3


def connect(rows):
    con = sqlite3.connect(":memory:")
    con.execute("CREATE TABLE items (sku TEXT, name TEXT, qty INTEGER)")
    con.executemany("INSERT INTO items VALUES (?, ?, ?)", rows)
    return con


def find_by_name(con, name):
    """SKUs of items named exactly `name`."""
    sql = f"SELECT sku FROM items WHERE name = '{name}' ORDER BY sku"
    return [row[0] for row in con.execute(sql)]


def search(con, text):
    """SKUs of items whose name contains `text` (any case).

    The text is what the operator typed: '%' and '_' in it are those
    characters, not wildcards.
    """
    sql = f"SELECT sku FROM items WHERE name LIKE '%{text}%' ORDER BY sku"
    return [row[0] for row in con.execute(sql)]
