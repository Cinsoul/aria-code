"""The daemon must analyse alerts with the user's configured model.

aria_daemon built the gateway's config as a dict literal pinned to Ollama, so
it never saw the user's configuration at all: a Vertex/Gemini user had every
alert analysed by a local qwen2.5:7b, and a user with no Ollama had the
gateway raise on every alert and fall back to the legacy summary.

The gateway was never the problem — analyze_alert_via_gateway passes
model/api_url/ollama_url straight through from whatever config it is handed.
These tests pin the daemon's end of that contract.
"""

from __future__ import annotations

import json
import os
import pathlib
import tempfile
import unittest

ENV_KEYS = ("ARIA_HOME", "ARIA_DAEMON_MODEL", "OLLAMA_URL")


class DaemonGatewayConfigComesFromSettings(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ENV_KEYS}
        self._home = tempfile.mkdtemp()
        os.environ["ARIA_HOME"] = self._home
        for k in ("ARIA_DAEMON_MODEL", "OLLAMA_URL"):
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _write_config(self, cfg: dict) -> None:
        pathlib.Path(self._home).mkdir(parents=True, exist_ok=True)
        (pathlib.Path(self._home) / "config.json").write_text(
            json.dumps(cfg), encoding="utf-8"
        )

    def _config(self) -> dict:
        import aria_daemon
        return aria_daemon.gateway_config()

    def test_configured_model_is_used(self):
        """The regression: a non-Ollama model must survive to the gateway."""
        self._write_config({
            "model": "gemini-2.5-pro",
            "local_provider": "vertex",
            "api_url": "https://gateway.example",
        })
        cfg = self._config()
        self.assertEqual(cfg["model"], "gemini-2.5-pro")
        self.assertEqual(cfg["local_provider"], "vertex")
        self.assertEqual(cfg["api_url"], "https://gateway.example")

    def test_env_overrides_still_win_for_operators(self):
        self._write_config({"model": "gemini-2.5-pro"})
        os.environ["ARIA_DAEMON_MODEL"] = "qwen2.5:7b"
        os.environ["OLLAMA_URL"] = "http://box:11434"
        cfg = self._config()
        self.assertEqual(cfg["model"], "qwen2.5:7b")
        self.assertEqual(cfg["ollama_url"], "http://box:11434")

    def test_a_config_change_reaches_the_next_alert(self):
        """Loaded per call, not cached — the daemon is long-lived."""
        self._write_config({"model": "model-one"})
        self.assertEqual(self._config()["model"], "model-one")
        self._write_config({"model": "model-two"})
        self.assertEqual(self._config()["model"], "model-two")

    def test_no_config_file_still_yields_a_usable_config(self):
        cfg = self._config()
        for key in ("model", "local_provider", "ollama_url", "api_url"):
            self.assertIn(key, cfg)
            self.assertTrue(cfg[key], f"{key} came back empty")


class DaemonDoesNotFabricateAModel(unittest.TestCase):
    """A literal model name in the daemon means someone rebuilt the dict."""

    def test_no_hardcoded_model_literal(self):
        src = (pathlib.Path(__file__).resolve().parents[1]
               / "src" / "aria_code" / "aria_daemon.py").read_text(encoding="utf-8")
        import ast
        tree = ast.parse(src)
        docstrings = {
            id(n.body[0].value)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                              ast.ClassDef))
            and n.body and isinstance(n.body[0], ast.Expr)
            and isinstance(n.body[0].value, ast.Constant)
            and isinstance(n.body[0].value.value, str)
        }
        offenders = [
            n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings
            and (":" in n.value and any(
                n.value.startswith(p) for p in ("qwen", "llama", "gemini", "gpt",
                                                "claude", "deepseek", "mistral")))
        ]
        self.assertEqual(
            offenders, [],
            "the daemon names a model directly; it should take the user's "
            f"configured one via gateway_config(): {offenders}",
        )


if __name__ == "__main__":
    unittest.main()
