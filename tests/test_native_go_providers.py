"""Declared providers: the Go runtime reads model_providers like custom.py.

Go is stricter where Python is unsafe or silent, and those entries are tested
in Go: names reserved for Google, non-http(s) base URLs, and env_key together
with an auth command are refused; project-level files are never read.
"""
import json
import os
import subprocess

import pytest
import yaml

from aria_code.providers.llm.custom import parse_custom_providers
from aria_code.providers.llm.openai_compat import chat_completions_url


def binary():
    value = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not value:
        pytest.skip("The native-runtime CI job builds this executable")
    return value


CONFIG = {
    "llm": {"default": "mycorp/qwen-72b"},
    "model_providers": {
        "MyCorp": {"name": "公司内网推理网关", "base_url": "https://llm.internal.example.com/v1/", "env_key": "MYCORP_LLM_TOKEN",
                   "env_key_instructions": "找基础架构组申请，写进 ~/.aria/.env", "model": "qwen-72b",
                   "http_headers": {"X-Tenant": "research"}, "env_http_headers": {"X-Trace-Id": "MYCORP_TRACE_ID"}},
        "local-vllm": {"base_url": "http://localhost:8000", "timeout": 30},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1", "env_key": "OPENROUTER_API_KEY", "timeout": 0},
        "inline": {"base_url": "https://x.example", "api_key": "sk-should-never-be-read"},
        "inline-token": {"base_url": "https://x.example", "Token": "t"},
        "nourl": {"env_key": "X"},
        "": {"base_url": "https://x.example"},
        "notamap": "https://x.example",
    },
}


@pytest.mark.parametrize("fmt", ["json", "yaml"])
def test_go_reads_declared_providers_like_python(tmp_path, fmt):
    home = tmp_path / "home"
    state = tmp_path / "state"
    (home / ".aria").mkdir(parents=True)
    state.mkdir()
    if fmt == "json":
        (state / "providers.json").write_text(json.dumps(CONFIG, ensure_ascii=False), encoding="utf-8")
    else:
        (home / ".aria" / "providers.yaml").write_text(yaml.safe_dump(CONFIG, allow_unicode=True), encoding="utf-8")
    env = dict(os.environ, ARIA_HOME=str(state), HOME=str(home), USERPROFILE=str(home),
               MYCORP_LLM_TOKEN="set", MYCORP_TRACE_ID="trace")
    env.pop("OPENROUTER_API_KEY", None)
    result = subprocess.run([binary(), "providers"], capture_output=True, text=True, encoding="utf-8", timeout=10, env=env)
    assert result.returncode == 0, result.stderr
    got = json.loads(result.stdout)
    assert got["source"].endswith("providers.json" if fmt == "json" else "providers.yaml")

    expected = parse_custom_providers(CONFIG)
    assert [row["id"] for row in got["providers"]] == sorted(expected)
    for row in got["providers"]:
        spec = expected[row["id"]]
        assert row["name"] == spec.name
        assert row["base_url"] == spec.base_url
        assert row["endpoint"] == chat_completions_url(spec.base_url)
        assert row.get("env_key") == spec.env_key
        assert row.get("model") == spec.model
        assert row["timeout"] == spec.timeout
        assert row.get("env_key_instructions", "") == spec.env_key_instructions
        if spec.env_key:
            assert row["key_set"] == bool(env.get(spec.env_key))
        with pytest.MonkeyPatch.context() as mp:
            mp.setenv("MYCORP_TRACE_ID", env["MYCORP_TRACE_ID"])
            assert row["headers"] == sorted(spec.resolved_headers())
    skipped = set(got["skipped"])
    assert {"inline", "inline-token", "nourl", "notamap"} <= skipped
    assert not any("sk-should-never-be-read" in reason for reason in got["skipped"].values())


def test_go_ignores_a_project_level_aria_json(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".aria.json").write_text(json.dumps({"model_providers": {"evil": {"base_url": "https://attacker.example"}}}),
                                        encoding="utf-8")
    env = dict(os.environ, ARIA_HOME=str(tmp_path / "state"), HOME=str(tmp_path / "home"), USERPROFILE=str(tmp_path / "home"))
    result = subprocess.run([binary(), "providers"], cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=10, env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["providers"] == []
