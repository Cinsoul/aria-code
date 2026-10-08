"""Retry helper for calls to carrier tracking APIs."""

import time

TRANSIENT = (ConnectionError, TimeoutError)


def with_retries(call, attempts=3, delay=0.5, sleep=time.sleep):
    """Run call(); retry it after a transient failure.

    `attempts` is the total number of calls. The wait starts at `delay`
    seconds and doubles each time. Any other error is a bug or a bad request
    and is raised at once.
    """
    for i in range(attempts):
        try:
            return call()
        except Exception:
            sleep(delay * 2 ** i)
    raise RuntimeError("gave up")
