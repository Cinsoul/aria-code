"""Import order lines exported by the shop's admin panel."""


def parse_line(line):
    """Split one CSV line into its fields."""
    return [field.strip() for field in line.rstrip("\n").split(",")]


def load_orders(text):
    """Every order in an export, as dicts keyed by the header row."""
    lines = [line for line in text.splitlines() if line.strip()]
    header = parse_line(lines[0])
    return [dict(zip(header, parse_line(line))) for line in lines[1:]]
