"""Unified permission and command-risk policy for Aria Code."""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


SAFE_POLICIES = {"safe", "balanced", "full"}


class PermissionMode(str, Enum):
    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    normalized_command: str
    policy: str
    risk: str
    reason: str = ""
    requires_approval: bool = False
    network: bool = False


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    requires_approval: bool
    risk: str
    reason: str
    normalized_command: str = ""
    network: bool = False


_ALIASES = {"python": "python3", "pip": "pip3"}


def normalize_command(command) -> str:
    """Rewrite a leading `python`/`pip` to `python3`/`pip3`; leave the rest exactly as written.

    This split the whole command with shlex and joined it again, which
    quotes every shell operator: `cd src && ls` ran as `cd src '&&' ls`,
    `a | b` passed "|" to a as an argument, `> out.txt` wrote nothing, and
    `ls *.py` and `echo $HOME` lost their expansion. Any command with a pipe,
    redirect, chain, glob or variable did something other than what it said.
    """
    if isinstance(command, list):
        import shlex as _shlex
        command = _shlex.join(str(c) for c in command)
    raw = (command or "").strip()
    head, sep, rest = raw.partition(" ")
    alias = _ALIASES.get(head)
    return f"{alias}{sep}{rest}" if alias else raw


# Shell operators that chain, pipe, redirect or substitute. A command holding
# one is more than its first word: `cat notes > ~/.zshrc` starts like a read,
# `pytest && curl … | sh` like a test run.
_SHELL_CONTROL = re.compile(r"[|;&<>`\n]|\$\(")
_SEGMENT_SPLIT = re.compile(r"\|\||&&|[|;&\n]|\$\(|`")
# Output trimming a test run may carry and still count as one.
_TRIM_SUFFIX = re.compile(r"(\s+2>&1)?(\s*\|\s*(tail|head)(\s+-n)?\s+-?\d+)?\s*$")


_DEVICE_WRITE = re.compile(r">\s*/dev/(?!null\b|stdout\b|stderr\b|tty\b|fd/)")


def writes_a_device(command: str) -> bool:
    """`> /dev/disk0`, not `> /dev/null` or `2>/dev/null`."""
    return bool(_DEVICE_WRITE.search(command or ""))


def has_shell_control(command: str) -> bool:
    return bool(_SHELL_CONTROL.search(command or ""))


def _segments(command: str) -> list[str]:
    return [part.strip() for part in _SEGMENT_SPLIT.split(command) if part.strip()]


def command_uses_network(command: str) -> bool:
    """True if any part of the command, not only the first, reaches the network."""
    return any(_segment_uses_network(part) for part in _segments(command.lower()))


def _segment_uses_network(stripped: str) -> bool:
    network_prefixes = (
        "curl ", "wget ", "http ", "https ", "gh ", "git fetch", "git pull",
        "git push", "pip3 install", "pip install", "npm install", "npm i ",
        "pnpm install", "yarn install", "brew install",
    )
    return any(stripped.startswith(prefix) for prefix in network_prefixes)


def is_verification_command(command: str) -> bool:
    stripped = _TRIM_SUFFIX.sub("", command.lower().strip(), count=1)
    if has_shell_control(stripped):
        return False
    prefixes = (
        "python3 -m py_compile",
        "python -m py_compile",
        "python3 -m pytest",
        "python -m pytest",
        "pytest",
        # The standard library's runner. Missing here, so `safe` blocked the
        # plainest way to test a Python project and the agent reported "blocked
        # by a security policy" instead of a test result.
        "python3 -m unittest",
        "python -m unittest",
        "npm test",
        "npm run test",
        "yarn test",
        "pnpm test",
        "npm run build",
        "npx tsc --noemit",
        "npx tsc --noEmit".lower(),
        "tsc --noemit",
        "go test",
        "cargo test",
        "mypy",
        "ruff check",
    )
    return any(stripped.startswith(prefix) for prefix in prefixes)


def classify_command_risk(command) -> str:
    """Classify command risk into low/medium/high."""
    if isinstance(command, list):
        import shlex as _shlex
        command = _shlex.join(str(c) for c in command)
    normalized = f" {str(command).lower().strip()} "
    stripped = normalized.strip()

    high_risk_patterns = (
        " rm ", " rm -", "chmod ", "chown ", "mkfs", "dd if=", "docker ", "kubectl ",
        "shutdown", "reboot", "systemctl ", "launchctl ", "passwd", "sudo ",
        "git push", "git reset --hard", "git checkout --", "mv ",
        ":(){ :", "fork bomb",
    )
    low_risk_prefixes = (
        "ls", "pwd", "echo", "cat ", "head ", "tail ", "rg ", "find ", "git status",
        "git diff", "git log", "which ", "whoami", "date", "uname ", "env",
        "python3 --version", "node --version", "npm --version",
    )
    medium_risk_prefixes = (
        "pip ", "pip3 ", "npm install", "npm i ", "npm run ", "python ", "python3 ",
        "pytest", "make ", "go test", "cargo test", "git commit", "git pull", "git merge",
        "gh ", "curl ", "wget ",
    )

    if any(pattern in normalized for pattern in high_risk_patterns) or writes_a_device(normalized):
        return "high"
    if has_shell_control(stripped):
        return "medium"
    if stripped.startswith(low_risk_prefixes):
        return "low"
    if stripped.startswith(medium_risk_prefixes) or is_verification_command(stripped):
        return "medium"
    return "medium"


class PermissionService:
    """Central policy for tools and shell-command execution."""

    READ_TOOLS = {"read_file", "list_files", "search_code", "project_context", "git_status", "git_diff"}
    WRITE_TOOLS = {"write_file", "edit_file", "apply_change", "apply_patch", "reject_change"}

    def __init__(
        self,
        mode: PermissionMode | str = PermissionMode.WORKSPACE_WRITE,
        command_policy: str = "safe",
        network_enabled: bool = True,
    ) -> None:
        try:
            self.mode = PermissionMode(mode)
        except ValueError:
            self.mode = PermissionMode.WORKSPACE_WRITE
        self.command_policy = command_policy if command_policy in SAFE_POLICIES else "safe"
        self.network_enabled = network_enabled

    def evaluate_tool(self, tool_name: str, params: Dict[str, Any] | None = None) -> PermissionDecision:
        name = (tool_name or "").strip()
        if name in self.READ_TOOLS:
            return PermissionDecision(True, False, "low", "Read-only tool allowed.")
        if name in self.WRITE_TOOLS:
            if self.mode == PermissionMode.READ_ONLY:
                return PermissionDecision(False, False, "medium", "Writes are blocked in read-only mode.")
            return PermissionDecision(
                True,
                self.mode != PermissionMode.FULL_ACCESS,
                "medium",
                "Write requires review or explicit approval before disk mutation.",
            )
        if name == "run_command":
            return self.evaluate_command(str((params or {}).get("command", "")))
        return PermissionDecision(False, False, "unknown", f"Unknown tool '{name}' is blocked.")

    def evaluate_command(self, command: str, policy: str | None = None) -> PermissionDecision:
        decision = evaluate_command_policy(
            command,
            policy or self.command_policy,
            mode=self.mode.value,
            network_enabled=self.network_enabled,
        )
        return PermissionDecision(
            allowed=decision.allowed,
            requires_approval=decision.requires_approval,
            risk=decision.risk,
            reason=decision.reason or "Command allowed.",
            normalized_command=decision.normalized_command,
            network=decision.network,
        )


def evaluate_command_policy(
    command: str,
    policy: str = "safe",
    *,
    mode: str = PermissionMode.WORKSPACE_WRITE.value,
    network_enabled: bool = True,
) -> PolicyDecision:
    """Return policy decision for command execution."""
    normalized = normalize_command(command)
    selected_policy = (policy or "safe").strip().lower()
    if selected_policy not in SAFE_POLICIES:
        selected_policy = "safe"
    try:
        selected_mode = PermissionMode(mode)
    except ValueError:
        # Fail closed. An unrecognised mode used to resolve to WORKSPACE_WRITE,
        # which is more permissive than READ_ONLY, not less: under read-only a
        # write command is a hard block, while under workspace-write it is a
        # block the user can unlock by approving. Resolving an invalid value to
        # the laxer of the two turns a typo — or a caller passing a *policy*
        # name into the *mode* slot — into an approval prompt that should never
        # have been offered.
        selected_mode = PermissionMode.READ_ONLY

    risk = classify_command_risk(normalized)
    network = command_uses_network(normalized)
    if network and not network_enabled:
        return PolicyDecision(
            allowed=False,
            normalized_command=normalized,
            policy=selected_policy,
            risk=risk,
            reason=f"Network command blocked by policy: {normalized}",
            requires_approval=False,
            network=True,
        )
    if selected_mode == PermissionMode.READ_ONLY and risk != "low":
        return PolicyDecision(
            allowed=False,
            normalized_command=normalized,
            policy=selected_policy,
            risk=risk,
            reason=f"Command blocked by read-only mode (risk={risk}): {normalized}",
            requires_approval=False,
            network=network,
        )
    if risk == "high" and selected_policy != "full":
        return PolicyDecision(
            allowed=False,
            normalized_command=normalized,
            policy=selected_policy,
            risk=risk,
            reason=(
                f"Command blocked by policy '{selected_policy}' (risk={risk}): {normalized}. "
                "Use /config set command_policy=full only if you understand the risk."
            ),
            requires_approval=selected_policy == "balanced",
            network=network,
        )
    # Verification is the one class of command the agent must be able to run
    # under the default policy. `safe` blocked pytest, py_compile, npm test and
    # tsc --noEmit, so the loop could write a fix and then had no way to find
    # out whether it worked — and the model said so out loud: "由于安全策略的
    # 限制，我无法执行 pytest ... 但我相信测试应该能够通过". An agent that
    # cannot check its own work is guessing, and the whole acceptance gate rests
    # on being able to run exactly these commands.
    #
    # The exposure is small and bounded by what `is_verification_command`
    # matches: test and type-check runners, anchored at the start of the
    # command. It stays subject to read-only mode and to the network rule
    # above, and `high` risk was already rejected before this point — so a
    # command like `pytest && rm -rf /` never reaches here.
    if selected_policy == "safe" and risk != "low" and is_verification_command(normalized):
        return PolicyDecision(
            allowed=True,
            normalized_command=normalized,
            policy=selected_policy,
            risk=risk,
            reason="",
            requires_approval=False,
            network=network,
        )

    if selected_policy == "safe" and risk != "low":
        extra = ""
        norm_low = normalized.lower()
        if "pip3" in norm_low or "pip " in norm_low or norm_low.startswith("pip"):
            extra = (
                "\n\n💡 依赖安装提示：运行 `/config set command_policy=balanced` 后重试，"
                "或手动在终端执行该命令。不要重试相同命令！"
            )
        elif "python" in norm_low and ("~/" in normalized or "/Desktop/" in normalized):
            extra = (
                "\n\n💡 脚本执行提示：运行 `/config set command_policy=balanced` 后重试。"
                "不要重试相同命令！"
            )
        return PolicyDecision(
            allowed=False,
            normalized_command=normalized,
            policy=selected_policy,
            risk=risk,
            reason=(
                f"Command blocked by policy '{selected_policy}' (risk={risk}): {normalized}. "
                "Use /config set command_policy=balanced or /run --dry-run <cmd> first."
                + extra
            ),
            requires_approval=True,
            network=network,
        )
    return PolicyDecision(
        allowed=True,
        normalized_command=normalized,
        policy=selected_policy,
        risk=risk,
        reason="",
        requires_approval=False,
        network=network,
    )
