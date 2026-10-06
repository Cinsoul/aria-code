"""The Chinese UI in an 80-column terminal reads as Chinese and stays short.

Recorded: /help and the "/" popup described commands in English under 命令,
and /inventory and /carriers put an English headline over Chinese detail
lines. (Narrow tables are covered in test_output_rendering.)
"""

from __future__ import annotations

import io
import sys

from rich.console import Console

from aria_code.apps.cli.commands.catalog import COMMAND_DESCRIPTIONS_ZH, CORE_SLASH_COMMANDS, ENTRY_SLASH_COMMANDS, describe


def test_every_command_help_shows_has_a_chinese_description():
    missing = [n for n in (*CORE_SLASH_COMMANDS, *ENTRY_SLASH_COMMANDS) if n not in COMMAND_DESCRIPTIONS_ZH]
    assert not missing, missing
    assert describe("/help", "Show commands and examples", "zh") == "命令与示例"
    assert describe("/help", "Show commands and examples", "en") == "Show commands and examples"
    assert describe("/realty", "Real-estate data: /realty X", "zh") == "Real-estate data"


def test_help_in_chinese_describes_in_chinese(monkeypatch):
    sys.argv = ["aria-code"]
    import aria_code.aria_cli as cli

    terminal = cli.ArtheraTerminal(dict(cli.DEFAULT_CONFIG, ui_lang="zh"))
    console = Console(file=io.StringIO(), width=80, color_system=None)
    monkeypatch.setattr(terminal.commands.context, "console", console)
    monkeypatch.setattr(terminal.commands.context, "has_rich", True)
    terminal.commands.cmd_help("")
    text = console.file.getvalue()
    assert "命令与示例" in text and "Show commands and examples" not in text


def test_the_popup_describes_in_chinese():
    from prompt_toolkit.document import Document

    from aria_code.ui.completer import AriaPTCompleter

    completer = AriaPTCompleter({"/help": (lambda a: None, "Show commands and examples")}, [], [], lang="zh")
    meta = str(next(completer.get_completions(Document("/he"), None)).display_meta_text)
    assert "命令与示例" in meta


def test_logistics_headlines_follow_the_ui_language():
    from aria_code.apps.cli.commands.warehouse_cmds import _carriers_headline, _inventory_headline

    inventory = {"summary": "7 SKUs analysed (file:skus.csv): 3 to reorder", "source": "file:skus.csv",
                 "data": {"items": [{}] * 7, "counts": {"reorder": 3, "insufficient_history": 1, "no_demand": 1},
                          "dead_stock": 0, "slow_stock": 0}}
    assert _inventory_headline(inventory, zh=True) == (
        "分析 7 个 SKU（file:skus.csv）：3 个需补货，1 个历史数据不足，1 个无需求；呆滞 0 个，慢动 0 个。")
    assert _inventory_headline(inventory, zh=False) == inventory["summary"]
    carriers = {"summary": "100 waybills across 3 lanes and 5 carriers", "source": "file:waybills.csv",
                "data": {"scorecard": [{"lane": "A", "carrier": "X"}, {"lane": "B", "carrier": "Y"}],
                         "anomalies": [1, 2], "savings": [1], "estimated_total_saving": 645.49}}
    assert _carriers_headline(carriers, zh=True) == (
        "100 张运单，2 条线路、2 家承运商（file:waybills.csv）；2 个异常待核实；1 个节省机会，预计共 645.49。")
