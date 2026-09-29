"""Owns the tool registries that aria_cli populates at import.

LOCAL_TOOLS, LOCAL_TOOL_SCHEMAS and ARIA_TOOLS were declared in aria_cli.py, so
five command mixins reached into a 6800-line module to ask what tools exist —
every one of them read-only: len(), `in`, .items(), one lookup. Registration
still happens in aria_cli, which is where the tool functions and their optional
imports live; what moved is *ownership of the containers*.

They are populated in place (update/extend), never rebound. That matters: a
`LOCAL_TOOLS = {...}` anywhere would leave this module's dict empty while the
CLI filled a different one, and every reader here would silently see no tools.
The same failure the response cache and the tool-result cache each had.

This is also the first piece the durable runtime needs. A registry that exists
only as a global in whichever process imported aria_cli cannot be reconstructed
by a worker resuming a task somewhere else. Giving it its own module does not
make it per-session — that decision is still open — but it stops the CLI module
from being the only place it can live.
"""

from __future__ import annotations

from typing import Any, Callable

__all__ = ["LOCAL_TOOLS", "LOCAL_TOOL_SCHEMAS", "ARIA_TOOLS"]

# name -> (callable, human description)
LOCAL_TOOLS: dict[str, tuple[Callable[..., Any], str]] = {}

# OpenAI-style function schemas for the local tools above.
LOCAL_TOOL_SCHEMAS: list[dict[str, Any]] = []

# (name, description) for tools served by the Arthera backend.
ARIA_TOOLS: list[tuple[str, str]] = []
