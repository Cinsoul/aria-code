"""守卫：一个测试文件不能把同一个模块从两个根导入。

这个包在两个根下都可导入——``X``（经 src/aria_code）与 ``aria_code.X``（经
src）——而它们是**不同的模块对象，各有各的全局变量**。同一个文件混用两边，
就会出现"patch 打在没人调用的那一份上"，而且不报错、不失败，只是隔离静默失效。

2026-09-29 一次清掉的 24 处，全是这个：

  - test_subagent 隔离的是裸名模块的 _LEDGER，于是整组用例跑在开发者**真实的
    任务账本**上（``assert 89 == 1``）
  - test_broker_chat_confirm_gate 往**真实的 brokers.json** 里写，却对着临时
    文件断言——它的 config 层用例因此一直在空过
  - test_cli_app_split 与 test_artifacts_and_reports 真的**联网**抓了 NVDA /
    AAPL 行情
  - test_ui_input_box 让真的 prompt_toolkit 在无 tty 下跑，EOFError
  - test_aria_cli_core 的 "does not route" 用例一直在空过

哪个根才对，取决于**被测代码自己用哪个**：report_generator.py 写的是
``from data_cleaner import ...``，所以测它的文件也必须用裸名；而
stream_cloud_fallback 来自 ``aria_code.providers.llm.registry``，那就得用包名。
这条守卫不替你选，只要求一个文件对同一个模块**只选一次**。

根上的收敛（753 条裸名导入、105 个文件）是另一件独立的大工程；在那之前，
这条守卫把复发面挡住。
"""

from __future__ import annotations

import ast
import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "src" / "aria_code"


def _importable_roots() -> set[str]:
    """能被裸名导入的顶层名字——即 src/aria_code 直下的包与模块。"""
    names = {p.name for p in PACKAGE_ROOT.iterdir() if p.is_dir() and (p / "__init__.py").exists()}
    names |= {p.stem for p in PACKAGE_ROOT.glob("*.py") if p.stem != "__init__"}
    return names


def _imports(tree: ast.AST) -> list[str]:
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
    return out


def _mixed_roots(path: pathlib.Path, roots: set[str]) -> list[str]:
    """同时以两个根导入的模块名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    bare: set[str] = set()
    qualified: set[str] = set()
    for module in _imports(tree):
        top = module.split(".")[0]
        if top == "aria_code":
            qualified.add(module[len("aria_code."):])
        elif top in roots:
            bare.add(module)

    # 父子也算：`import runtime` 配 `from aria_code.runtime.agent_loop import …`
    # 同样是两个对象，patch 一样会落空。
    def clashes(name: str) -> bool:
        return any(name == q or name.startswith(q + ".") or q.startswith(name + ".")
                   for q in qualified)

    return sorted(name for name in bare if clashes(name))


def test_no_test_file_imports_one_module_under_both_roots():
    roots = _importable_roots()
    offenders = {}
    for path in sorted((REPO_ROOT / "tests").rglob("test_*.py")):
        mixed = _mixed_roots(path, roots)
        if mixed:
            offenders[str(path.relative_to(REPO_ROOT))] = mixed

    assert not offenders, (
        "以下测试文件把同一个模块从两个根导入了。两个根是不同的模块对象，"
        "patch 会打在没人调用的那一份上，而且不会报错：\n  "
        + "\n  ".join(f"{f}: {', '.join(m)}" for f, m in offenders.items())
        + "\n\n统一成一个根。选哪个看被测代码自己用的是哪个"
          "（production 写 `from X import …` 就用裸名，写 `from aria_code.X import …` 就用包名）。"
    )
