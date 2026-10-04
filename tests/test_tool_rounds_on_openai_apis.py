"""A coding task must get past its first tool round on OpenAI-style APIs.

Driving "write fx.py and test_fx.py, then run the tests" on Gemini (Vertex AI,
OpenAI-compatible endpoint): round two was refused with "Expected input to
contain field: 'id'" because the agent loop records tool calls the Ollama way
(no ids, dict arguments, tool results with no tool_call_id). A 429 or a dropped
connection then ended the turn outright, and write_file put the files in
~/Documents/Aria Code/generated while the tests ran in the project.
"""

from __future__ import annotations

import asyncio
import json
import os
import pathlib

from aria_code.providers.tool_messages import flatten_tool_turns, to_openai_tool_protocol

LOOP_HISTORY = [
    {"role": "system", "content": "rules"},
    {"role": "user", "content": "write fx.py and its tests"},
    {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "write_file", "arguments": {"path": "fx.py"}}},
        {"function": {"name": "write_file", "arguments": {"path": "test_fx.py"}}},
    ]},
    {"role": "tool", "name": "write_file", "content": "Created fx.py"},
    {"role": "tool", "name": "write_file", "content": "Created test_fx.py"},
    {"role": "user", "content": "continue"},
]


class TestNativeProtocol:
    def test_every_call_has_an_id_and_every_answer_points_at_one(self):
        out = to_openai_tool_protocol(LOOP_HISTORY)
        calls = out[2]["tool_calls"]
        assert [c["id"] for c in calls] == ["call_1", "call_2"]
        assert all(c["type"] == "function" for c in calls)
        assert json.loads(calls[0]["function"]["arguments"]) == {"path": "fx.py"}
        assert [m.get("tool_call_id") for m in out[3:5]] == ["call_1", "call_2"]
        assert "name" not in out[3]

    def test_an_unanswered_call_is_answered_and_a_stray_answer_kept_as_text(self):
        history = [
            {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "run_command", "arguments": "{}"}}]},
            {"role": "user", "content": "next"},
            {"role": "tool", "name": "read_file", "content": "orphan"},
        ]
        out = to_openai_tool_protocol(history)
        assert out[1] == {"role": "tool", "tool_call_id": "call_1", "content": "(run_command returned no result)"}
        assert out[-1]["role"] == "user" and "orphan" in out[-1]["content"]

    def test_existing_ids_are_kept(self):
        history = [{"role": "assistant", "content": None, "tool_calls": [
            {"id": "abc", "function": {"name": "x", "arguments": {}}}]},
            {"role": "tool", "tool_call_id": "abc", "content": "ok"}]
        out = to_openai_tool_protocol(history)
        assert out[0]["tool_calls"][0]["id"] == "abc" and out[1]["tool_call_id"] == "abc"
        assert out[0]["content"] == ""


class TestPlainConversation:
    def test_no_tool_roles_and_roles_alternate(self):
        out = flatten_tool_turns(LOOP_HISTORY)
        assert all(m["role"] != "tool" and "tool_calls" not in m for m in out)
        assert [m["role"] for m in out] == ["system", "user", "assistant", "user"]
        assert "[called write_file with" in out[2]["content"]
        assert "Result of write_file:\nCreated fx.py" in out[3]["content"] and "continue" in out[3]["content"]


class _Response:
    def __init__(self, status, lines=(), headers=None):
        self.status, self._lines, self.headers = status, list(lines), headers or {}

    async def text(self):
        return "Resource exhausted"

    @property
    def content(self):
        async def gen():
            for line in self._lines:
                yield line
        return gen()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class _Session:
    def __init__(self, responses, seen):
        self.responses, self.seen = responses, seen

    def post(self, url, json=None, timeout=None):
        self.seen.append(json)
        return self.responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def test_a_rate_limit_is_retried_and_nothing_is_delivered_twice(monkeypatch):
    import aria_code.local_llm_provider as llp

    sse = [b'data: {"choices":[{"delta":{"content":"ready"}}]}\n',
           b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n']
    responses = [_Response(429, headers={"Retry-After": "0"}), _Response(200, sse)]
    seen, sleeps = [], []
    monkeypatch.setattr(llp.aiohttp, "ClientSession", lambda **kw: _Session(responses, seen))

    async def no_sleep(delay):
        sleeps.append(delay)
    monkeypatch.setattr(llp.asyncio, "sleep", no_sleep)

    provider = llp.LocalLLMProvider.from_config({"local_provider": "custom", "custom_endpoint": "https://x/v1",
                                                 "custom_model": "m", "local_api_key": "k"})

    async def run():
        return [e async for e in provider.stream(LOOP_HISTORY, tools=[])]

    events = asyncio.run(run())
    assert [e["text"] for e in events if e["type"] == "token"] == ["ready"]
    assert not [e for e in events if e["type"] == "error"]
    assert len(seen) == 2 and len(sleeps) == 1
    assert seen[0]["messages"][3]["tool_call_id"] == "call_1", "the request carries the repaired protocol"


def test_written_files_land_where_the_tests_run(tmp_path, monkeypatch):
    from aria_code.apps.cli.tools.write_tools import _relative_write_base

    monkeypatch.chdir(tmp_path)
    assert _relative_write_base() == tmp_path.resolve()
    monkeypatch.chdir(pathlib.Path.home())
    assert _relative_write_base() != pathlib.Path.home().resolve()
    assert os.path.basename(str(_relative_write_base())) == "generated"
