"""Change contracts — the bounds a coding task runs inside.

Permission modes say what the agent may do anywhere: read only, write the
workspace, or anything. A task needs narrower bounds than that, and different
ones per project: "fix the auth refresh bug" has no business touching billing,
running a migration or pushing to main, even under workspace-write. Telling the
model so in the prompt is a request; this module makes it a rule the runtime
enforces on every tool call, before the call runs.

A contract names:

- ``allow``    — path globs the task may change (empty: the whole workspace);
- ``restrict`` — path globs it must not change, even inside ``allow``;
- ``forbid``   — capabilities it may not use (``git.push``, ``cloud.deploy``,
  ``database.write`` …; see :data:`aria_code.safety.risk.CAPABILITIES`);
- ``max_level`` — the highest risk level an action may have (L0–L4);
- ``success``  — what "done" means, shown to the model and in the report.

Projects declare one in ``.aria/policy.yaml`` under ``contract:``. The runtime
fills in the goal from the request, shows the contract to the model before the
first round, and refuses any call that breaks it — the call does not run, and
the model gets the reason as the tool's result so it can stay inside the lines.

Reading is never restricted: a contract bounds what a task changes.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from aria_code.safety.risk import (
    CAPABILITIES,
    LEVEL_NAMES,
    RiskAssessment,
    assess_tool,
    tool_paths,
)

POLICY_FILE = Path(".aria") / "policy.yaml"

# Capabilities that change something. A contract's path rules apply to calls
# that use one of these; reads and verification are never path-restricted.
_MUTATING = frozenset({
    "filesystem.write", "filesystem.delete", "git.stage", "git.commit", "git.history",
})


class ContractError(ValueError):
    """A policy file whose contract cannot be enforced as written."""


@dataclass(frozen=True)
class ContractVerdict:
    allowed: bool
    reason: str = ""
    rule: str = ""
    assessment: Optional[RiskAssessment] = None

    def as_tool_result(self, tool: str) -> dict:
        """What the model sees instead of the call's output."""
        return {
            "success": False,
            "error": (
                f"Blocked by the change contract ({self.rule}): {self.reason}. "
                "The call was not run. Stay inside the contract, or tell the user "
                "what you need and why."
            ),
            "contract_violation": {
                "tool": tool,
                "rule": self.rule,
                "reason": self.reason,
                "level": self.assessment.level if self.assessment else None,
            },
        }


def _glob_regex(pattern: str) -> re.Pattern:
    """``src/**``, ``**/*.sql``, ``billing/*`` — matched against a POSIX relative path."""
    pattern = pattern.strip()
    while pattern.startswith("./"):
        pattern = pattern[2:]
    if pattern in {"", "."}:
        pattern = "**"
    if pattern.endswith("/"):
        pattern += "**"
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    # A directory pattern also covers what is inside it.
    return re.compile("^" + "".join(out) + "(?:/.*)?$")


@dataclass(frozen=True)
class ChangeContract:
    root: Path
    goal: str = ""
    allow: tuple = ()
    restrict: tuple = ()
    forbid: frozenset = frozenset()
    max_level: int = 4
    success: tuple = ()
    source: str = ""
    _allow_re: tuple = field(default=(), repr=False, compare=False)
    _restrict_re: tuple = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        unknown = sorted(set(self.forbid) - CAPABILITIES)
        if unknown:
            raise ContractError(
                f"unknown capabilit{'y' if len(unknown) == 1 else 'ies'} in forbid: {', '.join(unknown)}"
            )
        if not 0 <= int(self.max_level) <= 4:
            raise ContractError(f"max_level must be 0-4, not {self.max_level}")
        object.__setattr__(self, "root", Path(self.root).expanduser())
        object.__setattr__(self, "_allow_re", tuple(_glob_regex(p) for p in self.allow))
        object.__setattr__(self, "_restrict_re", tuple(_glob_regex(p) for p in self.restrict))

    # ── construction ──────────────────────────────────────────────────────

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], root: Path | str, *, source: str = "") -> "ChangeContract":
        def _strings(key: str) -> tuple:
            value = data.get(key) or ()
            if isinstance(value, str):
                value = [value]
            if not isinstance(value, Iterable):
                raise ContractError(f"{key} must be a list")
            return tuple(str(item).strip() for item in value if str(item).strip())

        try:
            max_level = int(data.get("max_level", 4))
        except (TypeError, ValueError):
            raise ContractError(f"max_level must be 0-4, not {data.get('max_level')!r}") from None
        return cls(
            root=Path(root),
            goal=str(data.get("goal") or "").strip(),
            allow=_strings("allow"),
            restrict=_strings("restrict"),
            forbid=frozenset(_strings("forbid")),
            max_level=max_level,
            success=_strings("success"),
            source=source,
        )

    @classmethod
    def load(cls, root: Path | str) -> Optional["ChangeContract"]:
        """The project's contract from ``.aria/policy.yaml``, or None if it declares none.

        A malformed file raises :class:`ContractError`: a contract that fails to
        load must not silently become no contract.
        """
        root = Path(root).expanduser()
        path = root / POLICY_FILE
        if not path.is_file():
            return None
        import yaml

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise ContractError(f"{path}: not valid YAML ({exc})") from None
        if not isinstance(data, Mapping):
            raise ContractError(f"{path}: expected a mapping at the top level")
        section = data.get("contract")
        if section is None:
            return None
        if not isinstance(section, Mapping):
            raise ContractError(f"{path}: 'contract' must be a mapping")
        return cls.from_mapping(section, root, source=str(path))

    @classmethod
    def fail_closed(cls, root: Path | str, error: str) -> "ChangeContract":
        """The contract to run under when the project's could not be read.

        A broken policy file means someone meant to bound this project; running
        unbounded would drop exactly the limits they wrote. Reading and
        verification still work, so the model can find and report the problem.
        """
        return cls(root=Path(root), max_level=0, source=f"error: {error}")

    @property
    def load_error(self) -> str:
        return self.source[len("error: "):] if self.source.startswith("error: ") else ""

    def with_goal(self, goal: str) -> "ChangeContract":
        line = " ".join(str(goal or "").split())
        return replace(self, goal=line[:200] + ("…" if len(line) > 200 else ""))

    # ── enforcement ───────────────────────────────────────────────────────

    def _relative(self, path: str) -> Optional[str]:
        candidate = Path(os.path.expanduser(path))
        if not candidate.is_absolute():
            candidate = self.root / candidate
        try:
            return candidate.resolve().relative_to(self.root.resolve()).as_posix()
        except (ValueError, OSError):
            return None

    def _check_path(self, path: str) -> Optional[tuple[str, str]]:
        relative = self._relative(path)
        if relative is None:
            return ("outside-workspace", f"{path} is outside the workspace")
        for pattern, regex in zip(self.restrict, self._restrict_re):
            if regex.match(relative):
                return ("restrict", f"{relative} is restricted ({pattern})")
        if self.allow and not any(regex.match(relative) for regex in self._allow_re):
            return ("allow", f"{relative} is outside the allowed paths ({', '.join(self.allow)})")
        return None

    def check(self, tool: str, params: Mapping[str, Any] | None = None) -> ContractVerdict:
        assessment = assess_tool(tool, params or {}, root=self.root)
        used = assessment.capabilities & self.forbid
        if used:
            return ContractVerdict(False, f"uses {', '.join(sorted(used))}", "forbid", assessment)
        if assessment.level > self.max_level:
            return ContractVerdict(
                False,
                f"{assessment.summary or tool} is L{assessment.level} ({assessment.name}); "
                f"this task allows up to L{self.max_level} ({LEVEL_NAMES[self.max_level]})",
                "max_level",
                assessment,
            )
        if assessment.capabilities & _MUTATING:
            paths = tool_paths(params or {}) if tool != "run_command" else list(assessment.files)
            for path in paths:
                problem = self._check_path(path)
                if problem:
                    return ContractVerdict(False, problem[1], problem[0], assessment)
        return ContractVerdict(True, assessment=assessment)

    # ── presentation ──────────────────────────────────────────────────────

    def render(self) -> str:
        """The contract as the model and the user read it."""
        lines = ["CHANGE CONTRACT"]
        if self.load_error:
            lines += ["", f"⚠ {POLICY_FILE} could not be read: {self.load_error}",
                      "  Nothing may be changed until it is fixed; reading and verifying still work."]
        if self.goal:
            lines += ["", "Goal", f"  {self.goal}"]
        lines += ["", "Allowed"]
        lines += [f"  ✓ modify {p}" for p in self.allow] or ["  ✓ modify files in the workspace"]
        restricted = [f"  × modify {p}" for p in self.restrict]
        restricted += [f"  × {cap}" for cap in sorted(self.forbid)]
        if self.max_level < 4:
            restricted.append(f"  × actions above L{self.max_level} ({LEVEL_NAMES[self.max_level]} risk)")
        if restricted:
            lines += ["", "Restricted"] + restricted
        if self.success:
            lines += ["", "Success criteria"] + [f"  ✓ {item}" for item in self.success]
        return "\n".join(lines)

    def prompt_block(self) -> str:
        return (
            "[Change contract]\n"
            "This task runs under the contract below. The runtime refuses any tool call "
            "that breaks it, so plan inside it; if the task cannot be done within it, "
            "stop and say which rule is in the way.\n\n"
            + self.render()
        )


__all__ = ["ChangeContract", "ContractError", "ContractVerdict", "POLICY_FILE"]
