"""Guarded imports for optional dependencies.

These try/except blocks sat in aria_cli.py, so five command mixins reached into
a 7000-line module to ask "is the market-data client available?". Nothing about
that question is session state — it is a fact about the install.

Import form matters here and is not incidental. market_data_client keeps a
module-level singleton, and the package is reachable under two roots whose
module objects are distinct — so importing it as aria_code.clients.
market_data_client would build a *second* MarketDataClient with its own
connections and caches. Every caller in the tree currently uses the bare
`market_data_client` shim, so there is one client today; this module uses the
same form deliberately to keep it that way. Converging the two roots is a
separate, repo-wide job (26 root modules use the same sys.modules shim trick).
"""

from __future__ import annotations

__all__ = ["MarketDataClient", "get_mdc", "HAS_MDC"]

try:
    from market_data_client import MarketDataClient, get_mdc  # noqa: F401

    HAS_MDC = True
except ImportError:  # pragma: no cover - exercised only without the client installed
    MarketDataClient = None  # type: ignore[assignment]
    get_mdc = None  # type: ignore[assignment]
    HAS_MDC = False
