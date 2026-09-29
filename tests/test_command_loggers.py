"""守卫：命令模块的 logger 必须是真的 Logger。

2026-09-29：五个命令模块里的 `logger` 是这样定义的——

    def logger(*args, **kwargs):
        from aria_cli import logger as fn
        return fn(*args, **kwargs)

这是一个**函数**，而所有用法都是 `logger.debug(...)`，于是每一次都抛
``AttributeError: 'function' object has no attribute 'debug'``。

13 处调用里有 12 处在 except 块内，也就是说：某件事失败 → 错误处理器试图记录
→ **记录本身崩掉** → 原始错误被一个无关的 AttributeError 顶替。定位一个
"/report 的 PDF 导出为什么失败"时，看到的会是 logging 的报错。

测试没抓到，是因为这些分支需要先制造一次真实失败才会走到。这条守卫不需要：
它直接检查每个模块的 logger 是什么，并且真的调用一次。
"""

from __future__ import annotations

import importlib
import logging
import pathlib
import pkgutil

import pytest

PACKAGE = "aria_code.apps.cli.commands"
PACKAGE_DIR = pathlib.Path(__file__).resolve().parents[1] / "src" / "aria_code" / "apps" / "cli" / "commands"


def _command_modules() -> list[str]:
    return sorted(
        f"{PACKAGE}.{m.name}"
        for m in pkgutil.iter_modules([str(PACKAGE_DIR)])
        if not m.ispkg and not m.name.startswith("_")
    )


@pytest.mark.parametrize("module_name", _command_modules())
def test_logger_is_a_logger_and_can_log(module_name: str):
    module = importlib.import_module(module_name)
    logger = getattr(module, "logger", None)
    if logger is None:
        pytest.skip(f"{module_name} defines no module-level logger")

    assert isinstance(logger, logging.Logger), (
        f"{module_name}.logger is {type(logger).__name__}, not a Logger. "
        "Every `logger.debug(...)` in this module raises AttributeError, and most "
        "of those calls sit in except blocks where they replace the error being "
        "reported. Use `logging.getLogger(__name__)`."
    )
    # 断言类型还不够：真调用一次，才证明它确实能记录。
    logger.debug("guard probe from %s", module_name)


def test_at_least_one_module_has_one():
    """守卫本身别因为全部 skip 而变成空转。"""
    found = [
        name for name in _command_modules()
        if isinstance(getattr(importlib.import_module(name), "logger", None), logging.Logger)
    ]
    assert found, "no command module exposes a real logger — the guard is vacuous"
