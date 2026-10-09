"""The transcript as actions, not tool calls.

Every call used to print two lines — "⏺ Read file  a.py" and "✓ read file
a.py 3ms" — so exploring a module before an edit was twenty lines of
bookkeeping the person had to scroll past to find the edit. What they want to
know is what Aria did: it explored these files, ran that command, edited this
file by so much. This module turns the stream of tool events into that, the way
the Codex terminal does:

    ⏺  Explored
       └ Read session.py, refresh.py
         Search "refresh_token"
    ⏺  Edit src/auth/session.py
       └ ✓ +12 -3
    ⏺  Ran python3 -m pytest -q
       └ ✓ 2.1s

Inspection calls (reads, searches, listings, git status) coalesce into one
*Explored* cell, printed when the next kind of action starts or the answer
begins — the spinner covers them while they run. Everything else is a header
when it starts (so an approval prompt sits under it) and one result line when
it ends.

``ActionView`` is pure: it takes events and returns ``(style, text)`` lines.
The terminal consumer prints them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

Line = tuple[str, str]

# Tool → the verb its line in an Explored cell starts with.
EXPLORE_TOOLS = {
    "read_file": "Read",
    "notebook_read": "Read",
    "analyze_file": "Read",
    "search_code": "Search",
    "grep": "Search",
    "glob": "List",
    "list_files": "List",
    "repo_map": "Map",
    "find_symbol": "Find",
    "project_context": "Read",
    "git_status": "Git",
    "git_diff": "Git",
}
EDIT_TOOLS = {"write_file": "Write", "edit_file": "Edit", "multi_edit": "Edit", "apply_patch": "Patch",
              "apply_change": "Edit", "notebook_edit": "Edit"}
# Commands that only look, shown as exploring rather than as a Ran cell.
_READ_COMMAND = re.compile(r"^\s*(ls|cat|head|tail|rg|grep|find|tree|wc|git (status|diff|log|show))\b")
_MAX_NAMES = 6
_SECRET = re.compile(r"(?i)\b([A-Z0-9_]*(TOKEN|KEY|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)=\S+")


def _short(text: Any, limit: int = 72) -> str:
    one = " ".join(str(text or "").split())
    one = _SECRET.sub(r"\1=***", one)
    return one if len(one) <= limit else one[: limit - 1] + "…"


def _name(path: Any) -> str:
    return Path(str(path)).name or str(path)


def _path_of(params: Mapping[str, Any]) -> str:
    for key in ("path", "file_path", "filename", "notebook_path", "file"):
        if params.get(key):
            return str(params[key])
    return ""


def _duration(seconds: Optional[float]) -> str:
    if seconds is None:
        return ""
    ms = int(seconds * 1000)
    return f"{ms}ms" if ms < 1000 else f"{seconds:.1f}s"


def _diff_counts(result: Any) -> Optional[tuple[int, int]]:
    data = result.get("data") if isinstance(result, Mapping) else None
    data = data if isinstance(data, Mapping) else (result if isinstance(result, Mapping) else {})
    diff = data.get("diff")
    if not isinstance(diff, str) or not diff:
        return None
    added = sum(1 for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in diff.splitlines() if l.startswith("-") and not l.startswith("---"))
    return added, removed


def _error(result: Any) -> str:
    if isinstance(result, Mapping):
        return _short(result.get("error") or "", 90)
    return ""


def _ok(result: Any) -> bool:
    return not (isinstance(result, Mapping) and (result.get("success") is False or result.get("error")))


def explore_item(tool: str, params: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    """(verb, object) when this call only looks; None when it acts."""
    canonical = str(tool).rsplit("__", 1)[-1]
    if canonical in EXPLORE_TOOLS:
        verb = EXPLORE_TOOLS[canonical]
        if verb == "Search":
            query = params.get("query") or params.get("pattern") or params.get("q") or ""
            return verb, f'"{_short(query, 48)}"' if query else ""
        if verb == "List":
            return verb, _short(params.get("pattern") or _path_of(params) or ".", 48)
        if verb == "Find":
            return verb, _short(params.get("name") or params.get("symbol") or "", 48)
        if verb == "Git":
            return verb, "diff" if canonical == "git_diff" else "status"
        if verb == "Map":
            return verb, "repository"
        return verb, _name(_path_of(params)) if _path_of(params) else ""
    if canonical == "run_command":
        command = str(params.get("command") or "")
        if _READ_COMMAND.match(command) and not re.search(r"[|;&>]", command):
            return "Run", _short(command, 48)
    return None


@dataclass
class _Explored:
    rows: list = field(default_factory=list)     # [verb, [objects]] in order
    failures: list = field(default_factory=list)

    def add(self, verb: str, obj: str) -> None:
        if self.rows and self.rows[-1][0] == verb:
            if obj and obj not in self.rows[-1][1]:
                self.rows[-1][1].append(obj)
            return
        self.rows.append([verb, [obj] if obj else []])

    def lines(self) -> list[Line]:
        out: list[Line] = [("bold", "⏺  Explored")]
        for index, (verb, objects) in enumerate(self.rows):
            shown = ", ".join(objects[:_MAX_NAMES])
            if len(objects) > _MAX_NAMES:
                shown += f" +{len(objects) - _MAX_NAMES}"
            branch = "   └ " if index == 0 else "     "
            out.append(("dim", f"{branch}{verb} {shown}".rstrip()))
        for failure in self.failures:
            out.append(("red", f"     ✗ {failure}"))
        return out


@dataclass
class ActionView:
    _explored: Optional[_Explored] = None

    def flush(self) -> list[Line]:
        """The pending Explored cell, if any. Call before printing anything else."""
        if self._explored is None or not (self._explored.rows or self._explored.failures):
            self._explored = None
            return []
        lines = self._explored.lines()
        self._explored = None
        return lines

    def start(self, tool: str, params: Mapping[str, Any] | None) -> list[Line]:
        params = params or {}
        if explore_item(tool, params) is not None:
            if self._explored is None:
                self._explored = _Explored()
            return []
        lines = self.flush()
        canonical = str(tool).rsplit("__", 1)[-1]
        if canonical == "run_command":
            header = f"⏺  Ran {_short(params.get('command'), 80)}"
        elif canonical in EDIT_TOOLS:
            header = f"⏺  {EDIT_TOOLS[canonical]} {_short(_path_of(params), 80)}".rstrip()
        else:
            hint = _path_of(params) or params.get("query") or params.get("symbol") or params.get("url") or ""
            label = canonical.replace("_", " ")
            if str(tool).startswith("mcp__"):
                parts = str(tool).split("__")
                label = f"{parts[1]} · {parts[-1].replace('_', ' ')}" if len(parts) >= 3 else label
            header = f"⏺  {label}" + (f"  {_short(hint, 60)}" if hint else "")
        return lines + [("bold", header)]

    def done(self, tool: str, params: Mapping[str, Any] | None, result: Any,
             seconds: Optional[float] = None) -> list[Line]:
        params = params or {}
        item = explore_item(tool, params)
        if item is not None:
            if self._explored is None:
                self._explored = _Explored()
            verb, obj = item
            if _ok(result):
                self._explored.add(verb, obj)
            else:
                self._explored.failures.append(f"{verb} {obj} — {_error(result) or 'failed'}".strip())
            return []
        ok = _ok(result)
        took = _duration(seconds)
        if not ok:
            detail = _error(result) or "failed"
            return [("red", f"   └ ✗ {detail}" + (f" · {took}" if took else ""))]
        canonical = str(tool).rsplit("__", 1)[-1]
        parts = []
        if canonical in EDIT_TOOLS:
            counts = _diff_counts(result)
            if counts:
                parts.append(f"+{counts[0]} -{counts[1]}")
        if took:
            parts.append(took)
        return [("green", "   └ ✓" + (f" {' · '.join(parts)}" if parts else ""))]


__all__ = ["ActionView", "EDIT_TOOLS", "EXPLORE_TOOLS", "explore_item"]
