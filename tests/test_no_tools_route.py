"""A task about this folder, on a model that cannot open it.

With backend_chat on, the model gets no local tools. Asked to run a function
in a folder, it said it had no filesystem access and gave the output as 5
(the function subtracts: -1), and `-p` reported success, exit 0.
"""

from __future__ import annotations

import asyncio

import pytest

from aria_code.apps.cli.workspace_route import needs_workspace, no_tools_message, route_has_tools


@pytest.fixture
def folder(tmp_path):
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.ts").write_text("")
    return tmp_path


@pytest.mark.parametrize("message", [
    "Run python3 -c 'import calc; print(calc.add(2,3))' and tell me the output",
    "what does calc.py do",
    "fix the bug in src/app.ts",
    "Fix the failing tests",
    "summarise this repo",
    "检查这个项目，修复失败的测试",
    "explain @file:notes.md",
])
def test_a_message_about_this_folder_needs_it(folder, message):
    assert needs_workspace(message, folder)


@pytest.mark.parametrize("message", [
    "Explain Python decorators in two sentences",
    "write a function that reverses a string",
    "AAPL price",
    "what is in config.yaml usually",   # no such file here
    "解释一下什么是闭包",
    "what is the project management triangle",
])
def test_a_question_about_code_in_general_does_not(folder, message):
    assert not needs_workspace(message, folder)


def test_the_backend_route_has_no_tools():
    config = {"backend_chat": True}
    assert not route_has_tools("gemini-2.5-pro", config, "https://api.example")
    assert route_has_tools("google/gemini-2.5-pro", {"backend_chat": False}, "https://api.example")


def test_the_message_names_the_route_and_the_way_out():
    english = no_tools_message({"backend_chat": True})
    assert "Arthera cloud chat" in english and "/model" in english and "--local" in english
    assert "backend_chat" in no_tools_message({"backend_chat": True}, lang="zh")
    assert "cannot call tools" in no_tools_message({})


def test_headless_fails_before_sending_a_folder_task(folder, monkeypatch, capsys):
    import aria_code.aria_cli as cli
    import aria_code.apps.cli.providers.runtime_bridge as bridge

    monkeypatch.chdir(folder)
    sent = []

    async def never(**kwargs):
        sent.append(kwargs)
        raise AssertionError("the model should not be asked")

    monkeypatch.setattr(bridge, "run_chat_via_runtime", never)
    monkeypatch.setattr(cli, "_run_deterministic_chain", lambda *a, **k: {"success": False})

    class Terminal:
        config = {"backend_chat": True, "model": "gemini-2.5-pro", "ui_lang": "en"}
        api_url = "https://api.example"
        commands = type("C", (), {"is_command": staticmethod(lambda text: False)})()
        _reference_service = None

        def _maybe_show_intent_preflight(self, *a, **k):
            pass

        async def _try_football_nl_intercept(self, prompt):
            return False

    turn = cli.ArtheraTerminal._run_prompt_turn.__get__(Terminal())
    result = asyncio.run(turn("Run calc.py and tell me the output", quiet=True, events=None))
    assert result["success"] is False and result["error"] == "model_cannot_use_tools"
    assert not sent
    assert "Arthera cloud chat" in capsys.readouterr().err


@pytest.mark.parametrize("message", ["run pytest -q", "execute `ls -la`", "运行 python 脚本看看结果",
                                     "How do I run a marathon?"])
def test_asking_for_a_command_to_run(folder, message):
    assert needs_workspace(message, folder) is (message != "How do I run a marathon?")
