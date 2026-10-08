"""A busy Vertex is waited out, not reported as the end of the task.

The 40-task eval run on google/gemini-3.5-flash lost inventory-reorder to one
"429 Resource exhausted" in the middle of the task: the turn ended, the agent
never wrote reorder.json, and the task scored ERROR. 429 and 5xx are about
load, not the request, and the same request usually succeeds a few seconds
later. The SDK only sends the request when the stream is first read, so the
error arrives from inside the read loop.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

pytest.importorskip("google.genai")
from google.genai.errors import APIError  # noqa: E402

from aria_code.apps.cli.providers import vertexai_stream  # noqa: E402
from aria_code.apps.cli.providers.vertexai_stream import VertexAIProvider  # noqa: E402


def _error(code: int, status: str) -> APIError:
    return APIError(code, {"error": {"code": code, "message": status.lower(), "status": status}})


def _chunk(text=None, reason="STOP"):
    parts = [SimpleNamespace(text=text, thought=False)] if text else []
    candidate = SimpleNamespace(content=SimpleNamespace(parts=parts),
                                finish_reason=SimpleNamespace(name=reason))
    return SimpleNamespace(candidates=[candidate], function_calls=None, usage_metadata=None)


class _Client:
    """Each round is a list: chunks to stream, or an APIError raised where the SDK raises it."""

    def __init__(self, rounds, *, raise_at_call=False):
        self.rounds = list(rounds)
        self.calls = 0
        outer = self

        class _Models:
            async def generate_content_stream(self, **kwargs):
                outer.calls += 1
                round_ = outer.rounds.pop(0)
                if isinstance(round_, APIError) and raise_at_call:
                    raise round_

                async def gen():
                    if isinstance(round_, APIError):
                        raise round_
                    for item in round_:
                        if isinstance(item, APIError):
                            raise item
                        yield item
                return gen()

        self.aio = SimpleNamespace(models=_Models())


@pytest.fixture
def waits(monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(vertexai_stream, "_sleep", fake_sleep)
    return slept


def _run(client, cancel_event=None):
    provider = VertexAIProvider(model="gemini-3.5-flash", config={})
    provider._client = client
    provider._get_client = lambda: client

    async def collect():
        return [e async for e in provider.stream([{"role": "user", "content": "go"}], tools=[],
                                                 cancel_event=cancel_event)]

    return asyncio.run(collect())


def test_a_429_on_first_read_is_waited_out(waits):
    client = _Client([_error(429, "RESOURCE_EXHAUSTED"), [_chunk("done")]])
    events = _run(client)
    assert client.calls == 2
    assert events[-1].success and events[-1].response == "done"
    assert waits == [2]


def test_a_429_from_the_call_itself_too(waits):
    client = _Client([_error(429, "RESOURCE_EXHAUSTED"), _error(503, "UNAVAILABLE"), [_chunk("ok")]],
                     raise_at_call=True)
    events = _run(client)
    assert client.calls == 3 and events[-1].success
    assert waits == [2, 5]


def test_busy_retries_do_not_use_up_the_empty_round_retries(waits):
    rounds = [_error(429, "RESOURCE_EXHAUSTED")] * 4 + [[_chunk("ok")]]
    events = _run(_Client(rounds))
    assert events[-1].success and events[-1].response == "ok"


def test_it_gives_up_after_the_last_wait_and_says_why(waits):
    client = _Client([_error(429, "RESOURCE_EXHAUSTED")] * 6)
    done = _run(client)[-1]
    assert client.calls == 6
    assert waits == [2, 5, 10, 20, 40]
    assert not done.success and "Vertex AI API Error" in done.error


def test_a_bad_request_is_not_retried(waits):
    client = _Client([_error(400, "INVALID_ARGUMENT"), [_chunk("never")]])
    done = _run(client)[-1]
    assert client.calls == 1 and waits == []
    assert not done.success


def test_nothing_is_sent_twice_once_text_has_streamed(waits):
    client = _Client([[_chunk("half of it "), _error(503, "UNAVAILABLE")], [_chunk("again")]])
    events = _run(client)
    assert client.calls == 1 and waits == []
    assert [e.text for e in events if hasattr(e, "text") and not hasattr(e, "success")] == ["half of it "]
    assert not events[-1].success


def test_the_user_can_cancel_during_the_wait(waits):
    cancel = asyncio.Event()
    cancel.set()
    client = _Client([_error(429, "RESOURCE_EXHAUSTED"), [_chunk("never")]])
    done = _run(client, cancel_event=cancel)[-1]
    assert done.cancelled and client.calls == 1
