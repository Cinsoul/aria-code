"""Shared CLI command metadata.

This module is intentionally UI-free so future channel adapters such as Feishu
or a local gateway can reuse the same command categories without importing the
large terminal implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple


@dataclass(frozen=True)
class DirectCommandSpec:
    name: str
    method_name: str
    async_method: bool = False
    watchable: bool = False
    aliases: Tuple[str, ...] = ()

    @property
    def names(self) -> Tuple[str, ...]:
        return (self.name, *self.aliases)


DIRECT_COMMANDS: Tuple[DirectCommandSpec, ...] = (
    DirectCommandSpec("quote", "cmd_quote", async_method=True, watchable=True),
    DirectCommandSpec("backtest", "cmd_backtest", async_method=True),
    DirectCommandSpec("health", "cmd_health", async_method=True, watchable=True),
    DirectCommandSpec("doctor", "cmd_doctor"),
    DirectCommandSpec("tools", "cmd_tools"),
    DirectCommandSpec("skills", "cmd_skills"),
    DirectCommandSpec("sessions", "cmd_sessions"),
    DirectCommandSpec("watch", "cmd_watch", aliases=("watchlist",)),
    DirectCommandSpec("export", "cmd_export", async_method=True),
    DirectCommandSpec("tv", "cmd_tv", async_method=True),
    DirectCommandSpec("ashare", "cmd_ashare", async_method=True, aliases=("a-share",)),
    DirectCommandSpec("markets", "cmd_markets"),
    DirectCommandSpec("orchestrate", "cmd_orchestrate"),
)


DIRECT_COMMAND_MAP = {
    alias: spec
    for spec in DIRECT_COMMANDS
    for alias in spec.names
}


WATCHABLE_DIRECT_COMMANDS: FrozenSet[str] = frozenset(
    alias
    for spec in DIRECT_COMMANDS
    if spec.watchable
    for alias in spec.names
)


# Commands shown by default in /help. Other slash commands remain executable but
# are hidden to keep the startup surface compact.
VISIBLE_SLASH_COMMANDS: FrozenSet[str] = frozenset({
    # Session
    "/help", "/clear", "/compact", "/cost", "/status", "/health",
    "/regen", "/undo", "/rewind", "/copy", "/recap", "/btw",
    # Sessions
    "/save", "/load", "/sessions", "/recall", "/export",
    # Config
    "/model", "/thinking", "/config", "/permissions", "/privacy",
    # Setup & discovery
    "/setup", "/apikey", "/doctor", "/architecture", "/mcp", "/skills", "/tools", "/packages", "/markets",
    # Auth
    "/login", "/logout", "/whoami",
    # Persistent data (direct writes)
    "/alert", "/journal", "/watch", "/note", "/todo", "/memory",
    # Broker
    "/broker", "/account", "/positions", "/orders", "/paper", "/trade",
    # Code & project
    "/project", "/init", "/review", "/code", "/plan", "/orchestrate", "/run", "/tasks", "/delegate", "/canva", "/completions", "/lsp",
    # Research
    "/team", "/warehouse", "/deep",
    # Quant
    "/backtest", "/wf", "/tv", "/ashare",
    # UI generation
    "/ui",
    # Other
    "/artifacts", "/vision", "/upload-image", "/file", "/strategy", "/accuracy",
})


# ── What "/" shows ────────────────────────────────────────────────────────────
# The "/" popup listed every command — 167 of them plus 14 skills, 92 without
# a category — and /help printed about 90 lines. Codex lists only session
# controls under "/", shows eight rows, and takes tasks in plain language.
# Aria keeps every command runnable by name; the popup opens on these two
# tiers, and typing narrows it over everything.

# Session and setup controls, in popup order.
CORE_SLASH_COMMANDS: Tuple[str, ...] = (
    "/help", "/model", "/review", "/plan", "/init", "/status", "/sessions", "/clear",
    "/compact", "/copy", "/rewind", "/permissions", "/config", "/doctor", "/login",
)

# One way into each capability: building code, financial analysis, logistics.
ENTRY_SLASH_COMMANDS: Tuple[str, ...] = (
    "/code", "/ta", "/backtest", "/team", "/report", "/portfolio", "/inventory", "/carriers",
)

# Second names for a command; the popup lists the command once.
COMMAND_ALIASES = {"/upload-image": "/vision"}


@dataclass(frozen=True)
class HelpTopic:
    key: str
    title_en: str
    title_zh: str
    commands: Tuple[str, ...]


HELP_TOPICS: Tuple[HelpTopic, ...] = (
    HelpTopic("code", "Code and projects", "代码与项目", (
        "/code", "/project", "/init", "/review", "/plan", "/run", "/read", "/write", "/edit", "/ls",
        "/search", "/verify", "/scaffold", "/apply", "/changes", "/git")),
    HelpTopic("market", "Market research", "市场研究", (
        "/quote", "/analyze", "/ta", "/chart", "/tv", "/deep", "/team", "/report", "/news", "/markets",
        "/watch", "/alert")),
    HelpTopic("quant", "Quant and portfolios", "量化与组合", (
        "/backtest", "/wf", "/compare", "/auto-strategy", "/execution", "/portfolio", "/risk",
        "/optimize", "/stress", "/factors")),
    HelpTopic("logistics", "Logistics", "物流", ("/inventory", "/carriers", "/warehouse")),
    HelpTopic("data", "Notes, files and artifacts", "笔记、文件与产物", (
        "/journal", "/note", "/todo", "/memory", "/artifacts", "/strategy", "/accuracy", "/file",
        "/vision", "/ui")),
    HelpTopic("broker", "Broker and trading", "券商与交易", (
        "/broker", "/paper", "/trade", "/account", "/positions", "/orders")),
    HelpTopic("session", "Session", "会话", (
        "/clear", "/compact", "/cost", "/status", "/health", "/regen", "/undo", "/rewind", "/copy",
        "/recap", "/btw", "/save", "/load", "/sessions", "/export", "/export-pdf")),
    HelpTopic("config", "Setup", "设置", (
        "/model", "/thinking", "/config", "/permissions", "/privacy", "/local", "/update", "/setup",
        "/apikey", "/doctor", "/mcp", "/login", "/logout", "/skills", "/tools", "/packages")),
)

HELP_TOPIC_MAP = {topic.key: topic for topic in HELP_TOPICS}


def popup_rank(name: str) -> int:
    """0 for a core command, 1 for an entry point, 2 for everything else."""
    if name in CORE_SLASH_COMMANDS:
        return 0
    if name in ENTRY_SLASH_COMMANDS:
        return 1
    return 2


def short_description(description: str) -> str:
    """The description without its usage tail: "Technical indicators: /ta AAPL …" → "Technical indicators"."""
    text = str(description or "")
    cut = text.find(": /")
    return (text[:cut] if cut > 0 else text).strip()
