"""Make the agent loop's tool rounds acceptable to OpenAI-style and plain chat APIs.

The agent loop records a tool round the way Ollama takes it: an assistant
message whose ``tool_calls`` have no ``id`` and dict ``arguments``, then
``role: "tool"`` messages with no ``tool_call_id``. Ollama accepts that.
OpenAI-compatible APIs do not — Vertex AI answered "Expected input to contain
field: 'id'", OpenAI refuses a tool message that answers no call — and the
registry providers sent only role and content, so a ``tool`` message reached
OpenAI with no id and Anthropic with a role it does not have. Either way a
task stopped after its first tool round: the file was written, the tests were
never run.
"""

from __future__ import annotations

import json
from typing import Iterable


def _arguments(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {}, ensure_ascii=False)


def to_openai_tool_protocol(messages: Iterable[dict]) -> list[dict]:
    """Native tool turns with ids: every call answered, every answer tied to a call."""
    out: list[dict] = []
    pending: list[tuple[str, str]] = []          # (id, name) of calls not yet answered
    counter = 0

    def answer_the_rest() -> None:
        for call_id, name in pending:
            out.append({"role": "tool", "tool_call_id": call_id,
                        "content": f"({name} returned no result)"})
        pending.clear()

    for message in messages:
        message = dict(message)
        role = message.get("role")
        if role == "tool":
            name = str(message.pop("name", "") or "")
            call_id = message.get("tool_call_id")
            match = next((p for p in pending if p[0] == call_id), None) if call_id else None
            match = match or next((p for p in pending if p[1] == name), None) or (pending[0] if pending else None)
            if match is None:
                # An answer to no call: keep what it says, as ordinary text.
                out.append({"role": "user", "content": f"Result of {name or 'a tool'}:\n{message.get('content', '')}"})
                continue
            pending.remove(match)
            out.append({"role": "tool", "tool_call_id": match[0], "content": str(message.get("content", ""))})
            continue
        answer_the_rest()
        calls = message.get("tool_calls")
        if role == "assistant" and calls:
            fixed = []
            for call in calls:
                function = dict(call.get("function") or {})
                name = str(function.get("name") or call.get("name") or "")
                if not name:
                    continue
                counter += 1
                call_id = str(call.get("id") or f"call_{counter}")
                fixed.append({"id": call_id, "type": "function",
                              "function": {"name": name, "arguments": _arguments(function.get("arguments"))}})
                pending.append((call_id, name))
            message["tool_calls"] = fixed
            if not fixed:
                message.pop("tool_calls")
            if message.get("content") is None:
                message["content"] = ""
        out.append(message)
    answer_the_rest()
    return out


def flatten_tool_turns(messages: Iterable[dict]) -> list[dict]:
    """Tool rounds as plain conversation, for APIs reached without native tool history.

    Calls become a line in the assistant's message and results become user
    text; consecutive messages of one role are merged, since some APIs insist
    that user and assistant alternate.
    """
    out: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = str(message.get("content") or "")
        if role == "tool":
            role, content = "user", f"Result of {message.get('name') or 'a tool'}:\n{content}"
        elif role == "assistant" and message.get("tool_calls"):
            lines = [content] if content.strip() else []
            for call in message["tool_calls"]:
                function = call.get("function") or {}
                lines.append(f"[called {function.get('name', '?')} with {_arguments(function.get('arguments'))}]")
            content = "\n".join(lines)
        if out and out[-1]["role"] == role and role in ("user", "assistant"):
            out[-1]["content"] += "\n\n" + content
        else:
            out.append({"role": role, "content": content})
    return out
