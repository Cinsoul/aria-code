"""Progress spinners follow the UI language.

"analyze Apple stock" in the English UI showed "正在获取 AAPL 数据..." while
the data loaded; 34 spinners across the slash commands were Chinese-only.
"""

from __future__ import annotations

import asyncio
import re
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from aria_code.apps.cli.i18n import ui_text

COMMANDS = Path(__file__).resolve().parents[1] / "src" / "aria_code" / "apps" / "cli" / "commands"


@pytest.mark.parametrize("owner, expected", [
    ({"ui_lang": "zh"}, "中"), ({"ui_lang": "zh-CN"}, "中"), ({"ui_lang": "en"}, "en"), ({}, "en"),
    (SimpleNamespace(config={"ui_lang": "zh"}), "中"),
    (SimpleNamespace(terminal=SimpleNamespace(config={"ui_lang": "zh"})), "中"),
    (SimpleNamespace(), "en"),
])
def test_ui_text_reads_the_configured_language(owner, expected):
    assert ui_text(owner, "中", "en") == expected


@pytest.mark.parametrize("lang, shown", [("en", "Fetching AAPL data"), ("zh", "正在获取 AAPL 数据")])
def test_the_analyze_spinner_speaks_the_ui_language(monkeypatch, lang, shown):
    import aria_code.apps.cli.commands.analysis_cmds as analysis_cmds

    monkeypatch.setattr(analysis_cmds, "build_analyze_prompt", lambda symbol, ctx, is_cn, response_lang=None: ctx)
    monkeypatch.setattr(analysis_cmds, "_is_ashare_symbol", lambda _symbol: False)
    spinners = []

    class Console:
        @contextmanager
        def status(self, text, **_kwargs):
            spinners.append(text)
            yield

    class Terminal:
        config = {"ui_lang": lang}
        conversation: list = []

        async def send_message(self, prompt, evidence_grounded=False):
            pass

    class Cli(analysis_cmds.AnalysisCommandsMixin):
        context = SimpleNamespace(has_rich=True, console=Console())
        terminal = Terminal()

        async def _build_analyze_context(self, symbol, is_cn):
            return "- Price: 1.00"

    asyncio.run(Cli().cmd_analyze("AAPL"))
    assert spinners == [f"[dim]{shown}...[/dim]"]


def test_no_spinner_is_chinese_only():
    chinese_only = []
    for path in sorted(COMMANDS.glob("*.py")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r'\.status\(f?"\[dim\][^"]*[一-鿿]', line) and "ui_text(" not in line and "T(" not in line:
                chinese_only.append(f"{path.name}:{number}")
    assert not chinese_only, chinese_only
