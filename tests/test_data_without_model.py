"""When no model can be reached, a market question still gets its data.

With no Google project set, "AAPL price" printed setup guidance and nothing
else, though the quote needs no model: the pre-fetch that serves tool-less
routes answers it. The model problem becomes a note under the data.
"""

from __future__ import annotations

import sys

import pytest

sys.argv = ["aria-code"]
import aria_code.aria_cli as cli  # noqa: E402


@pytest.mark.parametrize("error", [
    "vertex_needs_project: set GOOGLE_CLOUD_PROJECT …", "vertex_not_logged_in: run `gcloud auth login`",
    "missing_api_key:openai", "no_cloud_provider", "all_providers_failed", "HTTP 401 Unauthorized",
    "HTTP 429 rate limit",
])
def test_unreachable_models_are_recognised(error):
    assert cli._model_unavailable(error)


@pytest.mark.parametrize("error", ["ARIA-4223 evidence required", "empty_response", "tool crashed", ""])
def test_other_failures_are_not(error):
    assert not cli._model_unavailable(error)


def test_the_data_fallback_uses_the_tool_less_pre_fetch(monkeypatch):
    seen = {}

    def chain(message, *, model_has_tools, history):
        seen.update(message=message, tools=model_has_tools)
        return {"success": True, "response": "## Apple Inc.  `AAPL`", "tools_used": ["market_snapshot"]}

    monkeypatch.setattr(cli, "_run_deterministic_chain", chain)
    assert cli._data_without_model("AAPL price", [])["response"].startswith("## Apple")
    assert seen == {"message": "AAPL price", "tools": False}


def test_nothing_is_offered_when_the_data_has_no_answer(monkeypatch):
    monkeypatch.setattr(cli, "_run_deterministic_chain", lambda *a, **k: {"success": False})
    assert cli._data_without_model("write me a poem", []) == {}


def test_the_error_path_shows_the_data_first():
    import inspect

    source = inspect.getsource(cli.ArtheraTerminal.send_message)
    assert "_data_without_model(message" in source and "_model_unavailable(result.get(\"error\"))" in source
