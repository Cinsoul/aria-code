"""守卫：存凭据的文件必须是 0600。

这三个文件此前都按进程 umask 写出——通常 0644，同机器上任何账号可读：

  ~/.arthera/brokers.json    券商密码 / api_secret / access_token
  ~/.arthera/providers.json  各 LLM provider 的 API key
  <config_dir>/config.json   /login 存下的 auth_token / refresh_token

而同一个仓库对生成的 .env 是做了 chmod 0600 的（model_cmds.py）——也就是说
它知道该怎么做，唯独对**能动钱的那个**没做。

这条守卫测的是行为而不是"有没有调用 chmod"：真的写一遍，再读文件模式。
Windows 上 POSIX 位没有意义，由用户目录继承的 ACL 决定，所以那里跳过。
"""

from __future__ import annotations

import json
import os
import sys

import pytest

from aria_code.packages.aria_core.secure_file import (
    harden_existing,
    write_secret_json,
    write_secret_text,
)

pytestmark = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX permission bits do not govern on Windows"
)


def _mode(path) -> int:
    return path.stat().st_mode & 0o777


def test_new_file_is_created_owner_only(tmp_path):
    target = tmp_path / "nested" / "providers.json"
    write_secret_json(target, {"data": {"openai": {"api_key": "sk-test"}}})

    assert _mode(target) == 0o600
    assert json.loads(target.read_text())["data"]["openai"]["api_key"] == "sk-test"


def test_existing_world_readable_file_is_tightened(tmp_path):
    """升级路径：已经存在的 0644 文件，下次写入时必须被收紧。"""
    target = tmp_path / "brokers.json"
    target.write_text("{}")
    os.chmod(target, 0o644)

    write_secret_json(target, {"brokers": [{"id": "x", "password": "hunter2"}]})

    assert _mode(target) == 0o600


def test_text_writer_matches(tmp_path):
    target = tmp_path / "token"
    write_secret_text(target, "refresh-token")
    assert _mode(target) == 0o600
    assert target.read_text() == "refresh-token"


def test_harden_existing_never_raises_on_a_missing_file(tmp_path):
    """凭据加固失败绝不能把调用方带崩——丢权限比丢功能好处理。"""
    harden_existing(tmp_path / "does-not-exist")


def test_broker_config_writer_uses_it(tmp_path, monkeypatch):
    """端到端：走真正的 save_config，而不是只测辅助函数。"""
    import brokers.config as config_mod

    target = tmp_path / "brokers.json"
    monkeypatch.setattr(config_mod, "BROKERS_CONFIG_PATH", target)
    config_mod.save_config({"brokers": [{"id": "ths1", "password": "secret"}]})

    assert _mode(target) == 0o600
