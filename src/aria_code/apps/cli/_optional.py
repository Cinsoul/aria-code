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

__all__ = [
    "MarketDataClient", "get_mdc", "HAS_MDC",
    "HAS_BROKERS", "get_registry", "list_broker_configs", "get_broker_config",
    "add_broker_config", "remove_broker_config", "set_default_broker",
    "validate_broker_config", "supported_broker_types", "get_config_template",
    "BROKERS_CONFIG_PATH",
    "HAS_MODEL_CAP", "get_model_capability",
]

try:
    from market_data_client import MarketDataClient, get_mdc  # noqa: F401

    HAS_MDC = True
except ImportError:  # pragma: no cover - exercised only without the client installed
    MarketDataClient = None  # type: ignore[assignment]
    get_mdc = None  # type: ignore[assignment]
    HAS_MDC = False


# ── Brokers ──────────────────────────────────────────────────────────────────
# Same reasoning as above, and the stakes are higher: brokers.registry keeps a
# module-level BrokerRegistry singleton holding *live broker connections*, and
# `brokers` / `aria_code.brokers` are distinct module objects with separate
# singletons. Connecting through one and querying the other would report "not
# connected" for a session that is. All 37 call sites in the tree use the bare
# form, so there is one registry today; this module uses the same form to keep
# it that way.
try:
    from brokers import (  # noqa: F401
        BROKERS_CONFIG_PATH,
        add_broker_config,
        get_broker_config,
        get_config_template,
        get_registry,
        list_broker_configs,
        remove_broker_config,
        set_default_broker,
        supported_broker_types,
        validate_broker_config,
    )

    HAS_BROKERS = True
except ImportError:  # pragma: no cover - exercised only without the broker stack
    HAS_BROKERS = False
    BROKERS_CONFIG_PATH = None  # type: ignore[assignment]

    # aria_cli's version of this block only supplied three of the ten fallbacks,
    # so a build without the broker stack would raise NameError rather than
    # degrade — on add/remove/validate/template, i.e. exactly the paths a user
    # hits while trying to set a broker up. All ten are covered here.
    def get_registry():  # type: ignore[misc]
        return None

    def list_broker_configs():  # type: ignore[misc]
        return []

    def get_broker_config(broker_id: str):  # type: ignore[misc]
        return None

    def add_broker_config(cfg):  # type: ignore[misc]
        raise RuntimeError("Broker support is not installed")

    def remove_broker_config(broker_id: str):  # type: ignore[misc]
        raise RuntimeError("Broker support is not installed")

    def set_default_broker(broker_id: str):  # type: ignore[misc]
        raise RuntimeError("Broker support is not installed")

    def validate_broker_config(cfg):  # type: ignore[misc]
        return ["Broker support is not installed"]

    def supported_broker_types():  # type: ignore[misc]
        return []

    def get_config_template(broker_type: str):  # type: ignore[misc]
        return None


# ── Model capability registry ────────────────────────────────────────────────
# Another guarded import that happened to live in aria_cli. Used by the model
# and UI commands to describe a community Ollama model that is not in the
# MODELS table.
try:
    from model_capability import get_model_capability  # noqa: F401

    HAS_MODEL_CAP = True
except ImportError:  # pragma: no cover - exercised only without model_capability
    get_model_capability = None  # type: ignore[assignment]
    HAS_MODEL_CAP = False
