"""Client-side limit on calls to a carrier API."""

import time


class RateLimiter:
    """At most `limit` calls in any `window` seconds — a sliding window.

    A call made at time t counts until t + window. Calls that were refused
    do not count. limit and window must be positive.
    """

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit = limit
        self.window = window
        self.clock = clock
        self._start = None
        self._count = 0

    def allow(self):
        now = self.clock()
        if self._start is None or now - self._start >= self.window:
            self._start = now
            self._count = 0
        if self._count < self.limit:
            self._count += 1
            return True
        return False
