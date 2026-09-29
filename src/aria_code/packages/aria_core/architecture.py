"""Declarative agent architecture contract for Aria Code.

The contract keeps Codex/Claude Code style boundaries explicit while the legacy
CLI is extracted into smaller packages. It is intentionally pure data so tests,
doctor checks, docs, and future UI views can share one source of truth.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class LayerStatus(str, Enum):
    DONE = "done"
    PARTIAL = "partial"
    PLANNED = "planned"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ArchitectureLayer:
    name: str
    responsibility: str
    target_state: str
    current_state: str
    status: LayerStatus
    source_paths: Tuple[str, ...] = field(default_factory=tuple)
    depends_on: Tuple[str, ...] = field(default_factory=tuple)
    next_steps: Tuple[str, ...] = field(default_factory=tuple)
    blockers: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_complete(self) -> bool:
        return self.status == LayerStatus.DONE

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


ARCHITECTURE_SCHEMA_VERSION = "aria.agent-architecture.v1"


_ARCHITECTURE_LAYERS: Tuple[ArchitectureLayer, ...] = (
    ArchitectureLayer(
        name="launcher",
        responsibility="Stable executable entrypoint, runtime selection, and dependency bootstrap.",
        target_state="Shell entrypoints resolve the repo, use a controlled virtualenv, and never depend on the caller's random Python.",
        current_state="aria and aria-code bootstrap local dependencies. /doctor runs a python_venv drift check (pyvenv.cfg recorded version vs the running interpreter, and whether the venv's base interpreter still exists — the Homebrew-upgrade breakage); install.sh --rebuild and npm run repair both perform the drift-aware venv rebuild it suggests (repair auto-detects drift via npm/lib/venv.js before reusing an existing venv).",
        status=LayerStatus.PARTIAL,
        source_paths=("aria-code", "install.sh", "doctor.py"),
        next_steps=("Exercise the drift rebuild end-to-end on a real system-Python upgrade, then consider promoting launcher to ok.",),
    ),
    ArchitectureLayer(
        name="settings",
        responsibility="Configuration, secrets, model profiles, and permission policy resolution.",
        target_state="A single settings service resolves env, config files, CLI flags, and secrets without leaking credentials.",
        current_state=(
            "packages/aria_services/settings.py exists and apps/cli/config_store.py builds it, but "
            "aria_cli.py is its only caller — aria_daemon.py, brokers/config.py and "
            "packages/aria_mcp/server.py each read their own files directly. The service is written; "
            "adoption is what is missing, which is a different job from the one this layer used to "
            "describe."
        ),
        status=LayerStatus.PARTIAL,
        source_paths=(
            "packages/aria_services/settings.py",
            "apps/cli/config_store.py",
            "apps/cli/config_paths.py",
            "packages/aria_core/secure_file.py",
        ),
        next_steps=(
            "Route aria_daemon.py, brokers/config.py and packages/aria_mcp/server.py through the "
            "settings service instead of reading config files directly.",
        ),
    ),
    ArchitectureLayer(
        name="ui",
        responsibility="Terminal rendering, input UX, progress display, and artifact links.",
        target_state="A thin UI adapter renders compact, resumable, non-repetitive output with graceful plain-terminal fallback.",
        current_state="Terminal streaming and approval prompts now have a CLI runtime event consumer; Rich/prompt_toolkit remain optional and generated-file UX still needs hardening.",
        status=LayerStatus.PARTIAL,
        source_paths=("ui/", "apps/cli/commands/", "apps/cli/runtime_consumer.py"),
        next_steps=("Move generated-file open actions and remaining terminal panels behind a UI service.",),
    ),
    ArchitectureLayer(
        name="context",
        responsibility="Conversation memory, context compaction, task continuity, and artifact-backed summaries.",
        target_state="Context is automatically compacted before overflow, with recoverable task state and traceable artifacts.",
        current_state="ContextService owns pressure checks, local compaction, summary prompts, and resume envelopes; /doctor runs a context check and /export bundle carries context_health. Every compaction path (smart, hard, both fallbacks) first persists an aria.context_checkpoint.v1 full-snapshot record (2MB cap, keep-5 per session, 30-day expiry; config keys context_checkpoint_keep / context_checkpoint_max_age_days) via packages.aria_services.context_checkpoints under ~/.arthera/runtime/context_checkpoints/.",
        status=LayerStatus.PARTIAL,
        source_paths=("packages/aria_services/context.py", "packages/aria_services/context_checkpoints.py", "apps/cli/message_processing.py", "apps/cli/commands/session_ux_cmds.py"),
        next_steps=("Wire checkpoint restore into the conversation-rewind flow once cmd_rewind lands, so a compaction can be undone from the CLI.",),
    ),
    ArchitectureLayer(
        name="runtime",
        responsibility="Agent turn loop, planning, tool execution, retries, streaming, and interruption handling.",
        target_state="Runtime is separate from UI and business services, with typed tool calls, retries, cancellation, and traces.",
        current_state="A public packages.aria_sdk facade owns SDK-style query/result events, provider selection, streaming normalization, and the reusable runtime tool-turn loop; CLI rendering/approval is consumed through apps.cli.runtime_consumer. Every CLI chat turn runs through run_agent via apps.cli.providers.runtime_bridge and runtime.gateway (the inline send_message loop was retired 2026-07 after real-turn validation), with route-aware provider/fallback decisions in apps.cli.providers.chat_routing, per-tool approval and execution context threaded into run_agent's tool loop, and a single direct cloud rescue on runtime failure. Decoupling from aria_cli.py is measured rather than assumed: 23 modules still reach back into it through function-local imports, 137 references, down from 29/288 — figures the guards in tests/test_import_graph_budget.py freeze and only let shrink. The module-level import graph is acyclic, so those reverse edges are all deferred to call time, which is why the coupling was invisible rather than fatal.",
        status=LayerStatus.PARTIAL,
        source_paths=("aria_cli.py", "runtime/", "packages/aria_sdk/", "apps/cli/runtime_consumer.py", "apps/cli/deterministic.py", "apps/cli/providers/"),
        depends_on=("settings", "tools", "safety", "context"),
        next_steps=(
            "Fold send_message's remaining pre-turn (routing/decomposition/context injection) and post-turn (rendering/history/metrics) sections into testable modules, mirroring turn_planning/prompt_assembly.",
            "Untangle stream_ollama's 45 aria_cli module-global borrowings (AST-audited; was 47 before "
            "the response cache moved to apps/cli/providers/llm/response_cache.py). Still live: with "
            "aria_cli unloaded, _resolve_ollama_stream() falls back to the raw function, whose globals "
            "lack HAS_RICH, LOCAL_TOOL_SCHEMAS, _ACTIVE_COMMAND_POLICY and _CONFIRM_TOOLS.",
        ),
    ),
    ArchitectureLayer(
        name="tools",
        responsibility="Tool registry, schemas, permissions, local commands, and MCP adapters.",
        target_state="All tools are manifests with input schema, permission level, owner service, and deterministic output shape.",
        current_state="Legacy tools can be converted to manifests; some direct command paths still bypass the registry.",
        status=LayerStatus.PARTIAL,
        source_paths=("packages/aria_tools/", "tools/"),
        depends_on=("safety",),
        next_steps=("Route new slash commands through tool/service manifests instead of direct CLI functions.",),
    ),
    ArchitectureLayer(
        name="services",
        responsibility="Product service boundaries for data, reports, brokers, skills, channels, and gateway.",
        target_state="Business logic lives behind services; CLI, daemon, MCP, and webhooks are adapters.",
        current_state="Required service specs now cover gateway, runtime, settings, context, tools, data, reports, brokers, skills, MCP, safety, and observability; several implementations still sit in legacy modules.",
        status=LayerStatus.PARTIAL,
        source_paths=(
            "packages/aria_services/",
            "docs/architecture/service_boundaries.md",
        ),
        depends_on=("settings", "runtime", "tools"),
        next_steps=("Extract concrete SettingsService, SafetyService, ReportService, GatewayService, and ObservabilityService implementations behind the registered service manifests.",),
    ),
    ArchitectureLayer(
        name="mcp",
        responsibility="External package/tool integration through MCP and explicit adapters.",
        target_state="MCP servers expose typed tools, health, permissions, and connection status independent of CLI state.",
        current_state="Arthera Quant Engine bridge has manifests and doctor checks; lifecycle management still needs tightening.",
        status=LayerStatus.PARTIAL,
        source_paths=("packages/aria_mcp/",),
        depends_on=("tools", "services"),
        next_steps=("Add MCP reload/reconnect policy, tool provenance, and per-server failure isolation.",),
    ),
    ArchitectureLayer(
        name="safety",
        responsibility="Filesystem, shell, network, broker, and privacy guardrails.",
        target_state="Every risky action is classified, previewed when needed, audited, and blocked by default for live trading.",
        current_state=(
            "safety/service.py SafetyService already unifies evaluate_tool, evaluate_command, "
            "classify_risk, privacy and trading policy — but nothing constructs it. Callers still "
            "reach evaluate_command_policy and the broker helpers directly, so the unification "
            "exists on paper only. Broker preview/confirm and the two-gate chat-confirm gate are "
            "real and in use; credential files are written owner-only via "
            "packages/aria_core/secure_file.py."
        ),
        status=LayerStatus.PARTIAL,
        source_paths=("safety/", "brokers/", "apps/cli/commands/broker_cmds.py"),
        depends_on=("settings", "tools"),
        next_steps=(
            "Adopt SafetyService at its call sites — it is written and has zero callers. "
            "Constructing it is not the work; routing apps/cli/tools/system_tools.py, "
            "command_safety.py and the broker paths through it is.",
        ),
    ),
    ArchitectureLayer(
        name="channels",
        responsibility="Daemon, webhook, TradingView alerts, Feishu, Telegram, and future external entrypoints.",
        target_state="Channels submit structured tasks to gateway/runtime and never call CLI internals directly.",
        current_state="apps/channels now has the channel registry (six channels with direction/capabilities/enable resolution from config+env) and the TradingView adapter: alert payloads become aria.channel_task.v1 structured tasks (passphrase/HMAC verification reused from tradingview_bridge, fail-closed on mismatch, explicit verified/open_mode flags, stable dedup keys, gateway-facing prompt that forbids order placement). The daemon webhook endpoint now refuses open-mode intake from non-loopback clients and runs alert analysis through runtime.gateway.run_turn (tool-less turn; legacy quick summary kept as fallback).",
        status=LayerStatus.PARTIAL,
        source_paths=("aria_daemon.py", "apps/channels/", "apps/cli/tradingview_bridge.py"),
        depends_on=("settings", "runtime", "services", "safety"),
        next_steps=("Consider context-aware disambiguation for MA (Mastercard vs moving-average) in alert prompts; otherwise the channel flow is exercised end-to-end.",),
    ),
    ArchitectureLayer(
        name="observability",
        responsibility="Doctor checks, traces, provider health, audit logs, and user-visible diagnostics.",
        target_state="Health checks explain missing services, degraded providers, unsafe configs, and incomplete architecture layers.",
        current_state="Provider and package doctor checks exist; this contract represents architecture coverage. The /architecture command renders it (layers, status, gaps, per-layer next steps; --gaps for outstanding work) and /doctor prints a one-line coverage summary. /export bundle emits the support bundle: redacted config, runtime trace, provider health (+summary), artifact summary, the architecture contract, doctor checks, and MCP server/circuit status. Eight executable guards now hold architectural invariants that review alone had missed: the import graph stays acyclic and the aria_cli coupling only shrinks (test_import_graph_budget), rebound functions resolve every global they read (test_rebind_contract), no test file imports one module under both roots (test_single_import_root), command modules expose real Loggers (test_command_loggers), credential files are written owner-only (test_credential_file_permissions), and this contract's own paths and quoted figures stay true (test_architecture_ledger_is_true). Each was written after the defect it describes had already shipped undetected.",
        status=LayerStatus.PARTIAL,
        source_paths=("packages/aria_infra/doctor.py", "packages/aria_services/provider_health.py", "packages/aria_core/export.py", "apps/cli/commands/diagnostic_ops_cmds.py", "aria_cli.py"),
        depends_on=("services", "mcp", "safety"),
        next_steps=("Persist bundle/doctor history for trend diagnosis, and fold durable run summaries in once the run store lands on main.",),
    ),
)


def list_architecture_layers() -> List[ArchitectureLayer]:
    """Return the product architecture layers in dependency order."""

    return list(_ARCHITECTURE_LAYERS)


def architecture_layer_map() -> Dict[str, ArchitectureLayer]:
    return {layer.name: layer for layer in _ARCHITECTURE_LAYERS}


def required_architecture_layer_names() -> List[str]:
    return [layer.name for layer in _ARCHITECTURE_LAYERS]


def architecture_gaps() -> List[ArchitectureLayer]:
    return [layer for layer in _ARCHITECTURE_LAYERS if not layer.is_complete]


def architecture_status_counts() -> Dict[str, int]:
    counts = {status.value: 0 for status in LayerStatus}
    for layer in _ARCHITECTURE_LAYERS:
        counts[layer.status.value] += 1
    return counts


def architecture_contract() -> Dict[str, Any]:
    return {
        "schema_version": ARCHITECTURE_SCHEMA_VERSION,
        "layers": [layer.to_dict() for layer in _ARCHITECTURE_LAYERS],
        "status_counts": architecture_status_counts(),
    }
