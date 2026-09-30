"""Short-TTL response cache shared by the CLI and the extracted Ollama stream.

These four names used to live in aria_cli.py and reach stream_ollama only
through the module-global rebind in that file (see
``_rebind_module_function_globals`` and the stream_ollama rebind site). Any
caller that had not imported aria_cli first — the SDK and the daemon — got the
un-rebound function instead and died on the first cache-eligible turn with
``NameError: name '_cache_key' is not defined``.

Keeping them here means both callers share one cache dict rather than each
growing its own, and removes four of the borrowed globals that
packages/aria_core/architecture.py tracks as debt.
"""

from __future__ import annotations

import hashlib
import time

__all__ = ["RESPONSE_CACHE", "RESPONSE_CACHE_TTL", "RESPONSE_CACHE_MAX_ENTRIES",
           "cache_get", "cache_set", "cache_clear", "cache_key"]

RESPONSE_CACHE: dict = {}   # key → (response_text, expire_ts)
RESPONSE_CACHE_TTL = 60.0   # seconds
RESPONSE_CACHE_MAX_ENTRIES = 200


def cache_get(key: str) -> str | None:
    """Return cached response text if still valid, else None."""
    entry = RESPONSE_CACHE.get(key)
    if entry and time.time() < entry[1]:
        return entry[0]
    return None


def cache_set(key: str, value: str) -> None:
    """Store response in cache with TTL expiry."""
    RESPONSE_CACHE[key] = (value, time.time() + RESPONSE_CACHE_TTL)
    # Keep cache small — evict expired entries when it grows large
    if len(RESPONSE_CACHE) > RESPONSE_CACHE_MAX_ENTRIES:
        now = time.time()
        for k in list(RESPONSE_CACHE.keys()):
            if RESPONSE_CACHE[k][1] < now:
                del RESPONSE_CACHE[k]


def cache_clear() -> None:
    """Drop every cached response — for /clear and for test isolation.

    v4.4.2 grew a second copy of this module at apps/cli/response_cache.py.
    That copy is not taken: this one is already where the two callers share it,
    and duplicating it would put two cache dicts behind one name. Only the
    parts this one lacked came across.
    """
    RESPONSE_CACHE.clear()


def cache_key(model: str, message: str) -> str:
    raw = f"{model}::{message.strip().lower()}"
    return hashlib.md5(raw.encode()).hexdigest()
