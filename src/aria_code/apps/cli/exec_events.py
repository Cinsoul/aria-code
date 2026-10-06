"""JSON events for `aria-code -p … --format jsonl`, one per line, as the turn runs.

`-p --json` printed one document at the end, so a CI job saw nothing until the
turn was over and could not tell which tool ran, how long it took or where
it failed. With jsonl each step is a line on stdout as it happens:

    {"type": "turn.started", "prompt": "...", "model": "...", "ts": ...}
    {"type": "tool.started", "tool": "run_command", "params": {...}, "ts": ...}
    {"type": "tool.completed", "tool": "run_command", "success": true, "elapsed_s": 1.2,
     "error": "", "ts": ...}
    {"type": "turn.completed", "success": true, "response": "...", "tools_used": [...], ...}

Tool parameters are shortened and secrets masked: a written file's contents
or a command's token have no place in a CI log.
"""

from __future__ import annotations

import json
import time
from typing import Any, TextIO

from aria_code.apps.cli.runtime_consumer import MEASURED_ELAPSED_KEY, _redact_activity_text

PARAM_CHARS = 300


def json_safe(value: Any) -> Any:
    """``value`` with anything json cannot write turned into text."""
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def _param_view(params: dict) -> dict:
    view = {}
    for key, value in (params or {}).items():
        if str(key).startswith("_"):
            continue                       # execution context the host added
        if isinstance(value, str):
            # A file's contents is not a parameter worth a log line; its size is.
            view[key] = (f"<{len(value)} chars>" if len(value) > 2000
                         else _redact_activity_text(value, limit=PARAM_CHARS))
        elif isinstance(value, (int, float, bool)) or value is None:
            view[key] = value
        else:
            view[key] = _redact_activity_text(json.dumps(value, ensure_ascii=False, default=str),
                                              limit=PARAM_CHARS)
    return view


class ExecEvents:
    """Writes events to ``out``; does nothing when ``out`` is None."""

    def __init__(self, out: TextIO | None):
        self.out = out

    def emit(self, event_type: str, **fields: Any) -> None:
        if self.out is None:
            return
        record = {"type": event_type, **json_safe(fields), "ts": round(time.time(), 3)}
        try:
            self.out.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.out.flush()
        except (OSError, ValueError):
            self.out = None                # the reader went away; stop writing

    def tool_started(self, tool: str, params: dict) -> None:
        self.emit("tool.started", tool=tool, params=_param_view(params))

    def tool_completed(self, tool: str, result: dict) -> None:
        result = result if isinstance(result, dict) else {"success": bool(result)}
        fields: dict[str, Any] = {"tool": tool, "success": bool(result.get("success", True))}
        if isinstance(result.get(MEASURED_ELAPSED_KEY), (int, float)):
            fields["elapsed_s"] = round(float(result[MEASURED_ELAPSED_KEY]), 3)
        if result.get("error"):
            fields["error"] = _redact_activity_text(result["error"], limit=PARAM_CHARS)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        for key in ("exit_code", "path", "process_id", "change_id"):
            if key in data:
                fields[key] = data[key]
        self.emit("tool.completed", **fields)


__all__ = ["ExecEvents", "json_safe"]
