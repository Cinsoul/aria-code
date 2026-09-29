"""Reading API keys from the environment and providers.json.

Both functions lived in aria_cli.py, so five mixins reached into it for them.
Neither touches CLI state — they read two constant maps and one file.

The file path is resolved on each call rather than snapshotted at import, and
that is deliberate. resolve_config_dir() reads ARIA_CONFIG_DIR when it runs, so
a module-level snapshot taken while this module is imported would be taken
before initialize_cli_environment() — these mixins are imported at aria_cli.py
line 31, that call happens at 106. config_paths.py records what that class of
mistake cost before: config landing in ~/.aria-code while credentials went to
~/.arthera. Resolving at call time is always after the environment is set up.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict

from aria_code.apps.cli.constants import _DATA_KEY_MAP, _PROVIDER_KEY_MAP

__all__ = ["get_provider_key", "load_data_keys", "providers_file"]


def providers_file() -> Path:
    """Where providers.json lives, resolved now rather than at import."""
    from apps.cli.bootstrap import runtime_paths

    return runtime_paths().providers_file


def get_provider_key(provider: str) -> str:
    """Return the configured API key for a provider (env var takes priority)."""
    env_var = (_PROVIDER_KEY_MAP.get(provider.lower())
               or _DATA_KEY_MAP.get(provider.lower(), ""))
    if env_var:
        val = os.getenv(env_var, "")
        if val:
            return val
    # Check providers.json under both "llm" and "data" sections
    try:
        if providers_file().exists():
            raw = json.loads(providers_file().read_text(encoding="utf-8"))
            for section in ("llm", "data"):
                entry = raw.get(section, {}).get(provider.lower(), {})
                if entry.get("api_key"):
                    return entry["api_key"]
    except Exception:
        pass
    return ""


def load_data_keys() -> Dict[str, str]:
    """Return a dict of {service: api_key} for all configured data services.
    Merges environment variables (priority) and providers.json."""
    result: Dict[str, str] = {}
    # 1. Environment variables
    for svc, env_var in _DATA_KEY_MAP.items():
        val = os.getenv(env_var, "")
        if val:
            result[svc] = val
    # 2. providers.json "data" section
    try:
        if providers_file().exists():
            raw = json.loads(providers_file().read_text(encoding="utf-8"))
            for svc, entry in raw.get("data", {}).items():
                if svc not in result and entry.get("api_key"):
                    result[svc] = entry["api_key"]
    except Exception:
        pass
    return result
