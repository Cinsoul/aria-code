"""守卫：架构账本里可机械核对的说法，必须是真的。

packages/aria_core/architecture.py 自称 "one source of truth"，而 /architecture、
/doctor 和 /export bundle 都在消费它。一份失真的事实来源比没有更糟：读它的人
（包括 agent）会据此做决定。

2026-09-29 核对时它已经在四处失真：

  · settings 层标着 planned，而 packages/aria_services/settings.py 早已存在、
    apps/cli/config_store.py 也在用——真正缺的是 daemon/brokers/MCP 的采纳，
    这跟"还没写"是完全不同的下一步
  · safety 层说策略"还没统一成一个服务"，而 SafetyService 已经统一了
    evaluate_tool / evaluate_command / classify_risk / privacy / trading，
    只是**零个调用方**——同样地，要做的是采纳而不是构建
  · runtime 层写着 stream_ollama 借用 47 个全局名，实测 45
  · 四条 source_paths 指向不存在的文件，settings 层的三条全都不存在

这条守卫只核对能机械验证的部分：路径是否存在、数字是否对得上。文字描述核对
不了，但路径与数字一旦开始腐烂，通常整条描述也已经过期了。
"""

from __future__ import annotations

import ast
import builtins
import pathlib
import re

import pytest

from aria_code.packages.aria_core.architecture import _ARCHITECTURE_LAYERS

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "aria_code"


def _exists(rel: str) -> bool:
    """source_paths 混用两种基准：包内相对与仓库根相对。两种都认。"""
    return (PACKAGE_ROOT / rel).exists() or (REPO_ROOT / rel).exists()


@pytest.mark.parametrize(
    "layer_name, path",
    [(layer.name, path) for layer in _ARCHITECTURE_LAYERS for path in layer.source_paths],
    ids=lambda v: v if isinstance(v, str) else str(v),
)
def test_source_paths_point_at_something_real(layer_name: str, path: str):
    assert _exists(path), (
        f"架构账本的 {layer_name} 层指向 {path}，但它不存在。\n"
        "文件被搬走或删掉时，账本没跟上——而 /architecture 和 /export bundle "
        "都在把它当事实来源输出。"
    )


def test_every_layer_has_paths_and_a_state():
    for layer in _ARCHITECTURE_LAYERS:
        assert layer.source_paths, f"{layer.name} 没有 source_paths，无从核对"
        assert layer.current_state.strip(), f"{layer.name} 没有 current_state"


def _borrowed_global_count() -> int:
    """stream_ollama 从 aria_cli 借用的名字数——账本里写了这个数字。"""
    src = PACKAGE_ROOT / "apps" / "cli" / "providers" / "llm" / "ollama_stream.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))

    own: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            own.update((a.asname or a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            own.add(node.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            own.update(t.id for t in targets if isinstance(t, ast.Name))

    fn = next(
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "stream_ollama"
    )
    bound: set[str] = set()
    used: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.Name):
            (bound if isinstance(node.ctx, (ast.Store, ast.Del)) else used).add(node.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            bound.update((a.asname or a.name.split(".")[0]) for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return len(used - bound - set(dir(builtins)) - own)


def test_the_borrowed_global_count_the_ledger_quotes_is_current():
    """账本引用了一个具体数字，所以这个数字可以核对。

    它是衡量 stream_ollama 解耦进度的刻度。写在那里却不再更新，读的人会以为
    工作没有进展。
    """
    runtime = next(l for l in _ARCHITECTURE_LAYERS if l.name == "runtime")
    quoted = [
        int(m.group(1))
        for step in runtime.next_steps
        for m in [re.search(r"(\d+) aria_cli module-global borrowings", step)]
        if m
    ]
    assert quoted, "runtime 层不再引用借用数——若是有意移除，请一并删掉这条测试"

    actual = _borrowed_global_count()
    assert quoted[0] == actual, (
        f"账本写着 stream_ollama 借用 {quoted[0]} 个 aria_cli 全局名，实测 {actual}。\n"
        "把账本里的数字更新为实测值；它是这项解耦的进度刻度。"
    )
