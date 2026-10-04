"""Commands speak the UI language and use the model the user chose.

Recording an English session showed /ta printing "技术指标", "当前价格",
"中性", "死叉" and "技术图表已生成"; and /code switched every request to
qwen2.5:7b, whatever model was configured.
"""

from __future__ import annotations

import asyncio
import io
import re
from types import SimpleNamespace

from rich.console import Console

from aria_code.ui.render.market import print_ta_result, render_ta_plain

CJK = re.compile(r"[一-鿿]")


def _service_result():
    return SimpleNamespace(
        data={"price": 333.69, "rsi": 50.72, "macd": 3.816, "macd_signal": 4.83, "macd_hist": -1.02,
              "bb_upper": 346.6, "bb_mid": 331.9, "bb_lower": 317.2, "bb_position": 0.56, "ma5": 332.9},
        provider_chain=["yfinance"], quality={"status": "ok"}, missing_fields=[], stale=False)


def test_ta_in_english():
    buffer = io.StringIO()
    print_ta_result(console=Console(file=buffer, width=120), has_rich=True, symbol="AAPL", days=120,
                    service_result=_service_result(), formatter=lambda v, digits=2: f"{v:.{digits}f}", lang="en")
    out = buffer.getvalue()
    assert "AAPL technical indicators" in out and "neutral" in out and "below signal" in out
    assert "Bollinger" in out and not CJK.search(out), out
    plain = render_ta_plain("AAPL", 120, _service_result(), lambda v, digits=2: str(v), lang="en")
    assert not CJK.search(plain)


def test_ta_in_chinese_is_unchanged():
    plain = render_ta_plain("AAPL", 120, _service_result(), lambda v, digits=2: str(v), lang="zh")
    assert plain.startswith("AAPL 技术指标")


def test_code_uses_the_configured_model(monkeypatch, tmp_path):
    from aria_code.apps.cli.commands.core_cmds import CoreCommandsMixin

    seen = []

    class Terminal:
        config = {"model": "google/gemini-2.5-pro"}
        conversation: list = []

        async def send_message(self, prompt):
            seen.append(self.config["model"])

    class Cli(CoreCommandsMixin):
        context = SimpleNamespace(has_rich=False, console=None)
        terminal = Terminal()

    monkeypatch.setenv("HOME", str(tmp_path))
    try:
        asyncio.run(Cli().cmd_code("a CSV reconciler"))
    except Exception:
        pass   # whatever happens after the model call is not this test's concern
    assert seen == ["google/gemini-2.5-pro"]


def test_the_standard_test_runner_is_allowed_under_the_default_policy():
    """`safe` allowed pytest but blocked `python3 -m unittest`, so a coding task
    wrote its tests and then reported that it was not allowed to run them."""
    from aria_code.safety.permissions import evaluate_command_policy

    for command in ("python3 -m unittest -v", "python -m unittest discover", "pnpm test", "yarn test"):
        assert evaluate_command_policy(command, "safe").allowed, command
    assert not evaluate_command_policy("python3 -m unittest -v && rm -rf ~", "safe").allowed
