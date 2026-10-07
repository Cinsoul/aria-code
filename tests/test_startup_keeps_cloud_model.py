"""Starting Aria does not swap a cloud model for whatever Ollama has installed.

With model "gemini-3.8-flash" (no provider prefix), local_provider "vertex"
and backend_chat on, startup saw the id missing from Ollama's list, replaced
it with the installed deepseek-r1:1.5b, and saved that to the config. The
banner then read "DeepSeek R1 1.5B · cloud · via Arthera API".
"""

from __future__ import annotations

import io
import sys

import pytest
from rich.console import Console


def _start(monkeypatch, config):
    sys.argv = ["aria-code"]
    import aria_code.aria_cli as cli

    saved = []
    monkeypatch.setattr(cli, "detect_ollama_models_rich",
                        lambda url: ([{"name": "deepseek-r1:1.5b"}], None))
    monkeypatch.setattr(cli, "save_config", lambda cfg: saved.append(dict(cfg)))
    monkeypatch.setattr(cli, "console", Console(file=io.StringIO(), width=100, color_system=None))
    terminal = cli.ArtheraTerminal(dict(cli.DEFAULT_CONFIG, **config))
    terminal.print_header()
    return terminal, saved


@pytest.mark.parametrize("config", [
    {"model": "gemini-3.8-flash", "local_provider": "vertex", "backend_chat": False},
    {"model": "gemini-3.8-flash", "local_provider": "vertex", "backend_chat": True,
     "api_url": "https://api.example"},
    {"model": "google/gemini-2.5-pro"},
])
def test_a_cloud_model_is_left_alone(monkeypatch, config):
    terminal, saved = _start(monkeypatch, config)
    assert terminal.config["model"] == config["model"]
    # Startup saves the config for other reasons; none of it may change the model.
    assert all(cfg["model"] == config["model"] for cfg in saved)
    assert terminal._auto_healed_from is None


def test_a_missing_local_model_is_still_paired(monkeypatch):
    terminal, saved = _start(monkeypatch, {"model": "qwen2.5:7b", "local_provider": "ollama",
                                           "backend_chat": False})
    assert terminal.config["model"] == "deepseek-r1:1.5b"
    assert terminal._auto_healed_from == "qwen2.5:7b"
