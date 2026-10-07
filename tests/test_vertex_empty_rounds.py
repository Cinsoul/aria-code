"""An empty Gemini round is retried, and if it stays empty the reason is named.

On the first Vertex eval runs three of nine tasks ended in a few seconds with
"Error: empty_response": Gemini closed a round with no text and no function
call (finish_reason MALFORMED_FUNCTION_CALL, or an empty STOP after tool
results), a different task each run. Sent again, such a request usually works.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aria_code.apps.cli.providers.vertexai_stream import VertexAIProvider


def _chunk(text=None, call=None, reason=None):
    parts = []
    if text:
        parts.append(SimpleNamespace(text=text, thought=False))
    if call:
        parts.append(SimpleNamespace(text=None, thought=False))
    candidate = SimpleNamespace(content=SimpleNamespace(parts=parts),
                                finish_reason=SimpleNamespace(name=reason) if reason else None)

    chunk = SimpleNamespace(candidates=[candidate],
                            function_calls=[SimpleNamespace(name=call[0], args=call[1])] if call else None,
                            usage_metadata=None)
    return chunk


class _Client:
    def __init__(self, rounds):
        self.rounds = list(rounds)
        self.calls = 0
        outer = self

        class _Models:
            async def generate_content_stream(self, **kwargs):
                outer.calls += 1
                chunks = outer.rounds.pop(0)

                async def gen():
                    for c in chunks:
                        yield c
                return gen()

        self.aio = SimpleNamespace(models=_Models())


def _run(rounds):
    provider = VertexAIProvider(model="gemini-2.5-flash", config={})
    client = _Client(rounds)
    provider._client = client
    provider._get_client = lambda: client

    async def collect():
        return [event async for event in provider.stream([{"role": "user", "content": "fix it"}], tools=[])]

    return asyncio.run(collect()), client


def test_an_empty_round_is_sent_again():
    events, client = _run([[_chunk(reason="MALFORMED_FUNCTION_CALL")],
                           [_chunk(call=("read_file", {"path": "a.py"}), reason="STOP")]])
    assert client.calls == 2
    done = events[-1]
    assert done.success and done.tool_calls_pending == [{"tool": "read_file", "params": {"path": "a.py"}}]


def test_still_empty_after_retries_names_the_finish_reason():
    events, client = _run([[_chunk(reason="MALFORMED_FUNCTION_CALL")]] * 3)
    assert client.calls == 3
    done = events[-1]
    assert not done.success
    assert "empty_response" in done.error and "MALFORMED_FUNCTION_CALL" in done.error


def test_a_good_round_is_sent_once_and_text_is_read_from_parts():
    events, client = _run([[_chunk(text="Done: "), _chunk(text="fixed.", reason="STOP")]])
    assert client.calls == 1
    assert events[-1].success and events[-1].response == "Done: fixed."
