"""Business-workflow renderers, taking the context instead of aria_cli's globals.

These three drew through aria_cli's module-level ``console`` and ``HAS_RICH``,
so business_workflow_cmds reached into a 7000-line module for three functions
totalling 56 lines. The state they need is on ``self.context`` already — the
same move print_error made in _ui.py.

Names lost their leading underscore on the way over: they are this module's
public surface now, not aria_cli privates borrowed by bare name.
"""

from __future__ import annotations

from typing import Any

__all__ = ["p", "print_realty_result", "print_risk_scan"]


def p(context, msg: str, style: str = ""):
    """快速打印辅助（rich 可用时带样式）"""
    if context.has_rich:
        tag = {"dim": "dim", "error": "red", "ok": "green"}.get(style, style)
        context.console.print(f"[{tag}]{msg}[/{tag}]" if tag else msg)
    else:
        print(msg)


def print_realty_result(context, result, agent_name: str):
    """格式化打印 realty Agent 结果（地产健康度词汇，见 agents/signal_scheme.py::REALTY_SCHEME）"""
    _SIGNAL_LABELS = {
        "GOOD": "[green]正常/推荐[/green]",
        "WATCH": "[yellow]需观察[/yellow]",
        "CONCERN": "[red]警示[/red]",
        "SEVERE": "[bold red]极高风险[/bold red]",
    }
    if not context.has_rich:
        print(f"\n[{agent_name}] Signal: {result.signal}  Confidence: {result.confidence:.0%}")
        print(result.analysis)
        return

    context.console.print()
    context.console.print(f"  [bold]{agent_name.upper().replace('_',' ')}[/bold]"
                  f"  {_SIGNAL_LABELS.get(result.signal, result.signal)}"
                  f"  [dim]置信度 {result.confidence:.0%}[/dim]")
    context.console.print()
    for pt in (result.key_points or []):
        context.console.print(f"    • {pt}")
    if result.analysis:
        context.console.print()
        text = result.analysis[:1200] + ("…" if len(result.analysis) > 1200 else "")
        context.console.print(f"  [dim]{text}[/dim]")
    context.console.print()


def print_risk_scan(context, data: dict):
    """格式化打印风险扫描结果"""
    if not context.has_rich:
        print(f"Risk scan: {data.get('overall_level','?')} "
              f"(score={data.get('risk_score',0)})")
        for alert in data.get("alerts", []):
            print(f"  [{alert['level']}] {alert['desc']}")
        return

    level = data.get("overall_level", "未知")
    score = data.get("risk_score", 0)
    color = {"低": "green", "中": "yellow", "高": "red", "极高": "bold red"}.get(level, "white")
    context.console.print()
    context.console.print(f"  风险等级: [{color}]{level}[/{color}]  "
                  f"风险分值: {score}  "
                  f"预警项: {data.get('alert_count',0)}")
    context.console.print()
    for alert in data.get("alerts", []):
        ac = {"低": "dim", "中": "yellow", "高": "red", "极高": "bold red"}.get(
            alert["level"], "white")
        context.console.print(f"    [{ac}][{alert['level']}][/{ac}] {alert['desc']}")
    if data.get("suggestion"):
        context.console.print(f"\n  [dim]建议: {data['suggestion']}[/dim]")
    context.console.print()
