"""A configured model must survive startup.

Two places used to replace the user's model selection without telling them.

`print_header()` asks whether `config["model"]` is in the set Ollama reports
installed, and heals the config when it is not -- then persists the result with
`save_config()`. A cloud id is never in that set, because Ollama only lists
local models, so for anyone running the shipped default
(`google/gemini-2.5-pro`) with Ollama installed the branch fired on every single
startup. Measured before the fix:

    configured google/gemini-2.5-pro, installed {qwen2.5:7b, llama3.2:3b}
        -> qwen2.5:7b
    configured google/gemini-2.5-pro, installed {aardvark-tiny:1b, zzz-exp:0.5b}
        -> aardvark-tiny:1b
    configured anthropic/claude-sonnet-4, installed {llama3.2:1b}
        -> llama3.2:1b

The second case is the one that shows what `sorted(installed)[0]` really was: a
0.5B model that happens to sort early becoming the agent's brain.

`SettingsService.load()` did the same thing on first run, overwriting the
caller's default with whatever Ollama had -- contradicting the comment above
DEFAULT_MODEL in apps/cli/bootstrap.py, which says provider configuration is the
user's to make.
"""

from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
for _p in (str(ROOT / "src"), str(ROOT / "src" / "aria_code"), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from apps.cli.model_catalog import (  # noqa: E402
    is_provider_qualified,
    pick_best_installed_model,
)


class ACloudModelIsNeverReplacedFromTheLocalList(unittest.TestCase):
    """The regression that motivated this file."""

    CLOUD_IDS = (
        "google/gemini-2.5-pro",
        "anthropic/claude-sonnet-4",
        "openai/gpt-4.5",
        "deepseek/deepseek-chat",
    )

    def test_a_configured_cloud_model_is_left_alone(self) -> None:
        for model in self.CLOUD_IDS:
            for installed in (
                {"qwen2.5:7b", "llama3.2:3b"},      # curated models present
                {"aardvark-tiny:1b", "zzz:0.5b"},   # only junk -- the old alphabetical case
                {"llama3.2:1b"},                    # only a nano model
            ):
                with self.subTest(model=model, installed=sorted(installed)):
                    self.assertIsNone(
                        pick_best_installed_model(installed, model),
                        f"{model} would be replaced from a local model list",
                    )

    def test_a_namespaced_ollama_model_is_still_treated_as_local(self) -> None:
        # Ollama serves community models such as hf.co/user/model, whose first
        # segment is a host, not a provider. A bare "/" check would read these
        # as cloud ids and stop healing them.
        self.assertFalse(is_provider_qualified("hf.co/someone/qwen-finetune"))
        self.assertTrue(is_provider_qualified("google/gemini-2.5-pro"))

    def test_the_namespaced_local_model_can_still_be_healed(self) -> None:
        chosen = pick_best_installed_model({"qwen2.5:7b"}, "hf.co/someone/gone")
        self.assertEqual(chosen, "qwen2.5:7b")


class NoAlphabeticalLastResort(unittest.TestCase):
    def test_nothing_curated_and_nothing_capable_declines(self) -> None:
        # The old code answered "aardvark-tiny:1b" here.
        self.assertIsNone(
            pick_best_installed_model({"aardvark-tiny:1b", "zzz-experimental:0.5b"},
                                      "qwen2.5:7b"),
        )

    def test_a_curated_model_is_still_chosen(self) -> None:
        self.assertEqual(
            pick_best_installed_model({"llama3.2:3b", "aardvark-tiny:1b"}, "qwen2.5:7b"),
            "llama3.2:3b",
        )

    def test_an_installed_preference_wins_outright(self) -> None:
        self.assertEqual(
            pick_best_installed_model({"qwen2.5:7b", "llama3.2:3b"}, "qwen2.5:7b"),
            "qwen2.5:7b",
        )

    def test_an_empty_set_declines(self) -> None:
        self.assertIsNone(pick_best_installed_model(set(), "qwen2.5:7b"))


class FirstRunKeepsTheDefault(unittest.TestCase):
    """SettingsService.load() must not consult Ollama to pick a model."""

    def test_load_returns_the_declared_default_model(self) -> None:
        import tempfile

        from aria_code.packages.aria_services.settings import SettingsService

        with tempfile.TemporaryDirectory() as tmp:
            base = pathlib.Path(tmp)
            service = SettingsService(
                config_dir=base / "cfg",
                config_file=base / "cfg" / "config.json",
                sessions_dir=base / "sessions",
                defaults={"model": "google/gemini-2.5-pro",
                          "ollama_url": "http://127.0.0.1:1"},
            )
            cfg = service.load()
        self.assertEqual(cfg["model"], "google/gemini-2.5-pro")

    def test_the_service_no_longer_accepts_a_model_selection_hook(self) -> None:
        # Asserted so the hook is not quietly reintroduced: it was the mechanism
        # by which first run overwrote the default.
        import dataclasses

        from aria_code.packages.aria_services.settings import SettingsService

        fields = {f.name for f in dataclasses.fields(SettingsService)}
        self.assertNotIn("auto_select_model", fields)


class TheCuratedHelperDoesNotGuess(unittest.TestCase):
    def test_preferred_installed_model_declines_when_nothing_is_curated(self) -> None:
        from apps.cli.i18n import preferred_installed_model

        self.assertIsNone(preferred_installed_model({"aardvark-tiny:1b"}))
        self.assertEqual(preferred_installed_model({"qwen2.5:7b", "x:1b"}), "qwen2.5:7b")


if __name__ == "__main__":
    unittest.main()
