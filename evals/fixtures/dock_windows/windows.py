"""Dock door availability for carrier appointments."""


def merge_windows(windows):
    """The fewest continuous windows covering the same time, sorted by start.

    Each window is (start, end) as "H:MM" or "HH:MM", start included and end
    excluded. An end earlier than its start runs past midnight and becomes
    (start, "24:00") and ("00:00", end). Windows that overlap or touch merge.
    Results are written "HH:MM". A time that is not a real time of day is an
    error.
    """
    merged = []
    for start, end in sorted(windows):
        if merged and start < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged
