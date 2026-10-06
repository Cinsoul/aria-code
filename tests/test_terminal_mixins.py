"""Blocks of ArtheraTerminal moved out of aria_cli.py, still running on aria_cli's names.

-p and --watch live in apps/cli/headless.py, the chat turn (send_message) in
apps/cli/chat_turn.py, the banner, status line, toolbar and keys in
apps/cli/terminal_chrome.py.

aria_cli loads under two names, aria_cli and aria_code.aria_cli, as two
module objects. Each binds its own copy of the headless methods; rebinding one
shared class would leave both terminals reading whichever module loaded last,
and a test patching one of them would patch nothing that runs.
"""

from __future__ import annotations

import inspect
import sys


def test_each_aria_cli_binds_its_own_copy():
    import importlib

    sys.argv = ["aria-code"]
    # Both roots on purpose: this test is about the two module objects.
    # test_single_import_root forbids it for ordinary tests, where it means a
    # patch lands on the copy nobody calls.
    bare = importlib.import_module("aria_cli")
    packaged = importlib.import_module("aria_code.aria_cli")

    for module in (bare, packaged):
        for name in ("run_prompt", "_run_prompt_turn", "_finish_prompt", "run_watch", "send_message",
                     "print_header", "_status_line", "_build_keybindings", "_workspace_git_state",
                     "_bottom_toolbar"):
            method = getattr(module.ArtheraTerminal, name)
            assert method.__globals__ is vars(module), (module.__name__, name)
    assert bare.ArtheraTerminal.run_prompt is not packaged.ArtheraTerminal.run_prompt
    assert bare.ArtheraTerminal.send_message is not packaged.ArtheraTerminal.send_message


def test_the_code_lives_in_its_own_modules():
    import aria_code.aria_cli as cli

    assert inspect.getsourcefile(cli.ArtheraTerminal.run_prompt).endswith("apps/cli/headless.py")
    assert inspect.getsourcefile(cli.ArtheraTerminal.send_message).endswith("apps/cli/chat_turn.py")
    assert inspect.getsourcefile(cli.ArtheraTerminal.print_header).endswith("apps/cli/terminal_chrome.py")
    source = inspect.getsource(cli)
    assert "async def run_prompt" not in source and "async def send_message" not in source


def test_binding_copies_and_leaves_the_mixin_alone():
    from aria_code.apps.cli.chat_turn import ChatTurnMixin
    from aria_code.apps.cli.mixin_binding import bind_mixin

    namespace = {"marker": 1}
    copy = bind_mixin(ChatTurnMixin, namespace)
    assert copy is not ChatTurnMixin
    assert copy.send_message.__globals__ is namespace
    assert ChatTurnMixin.send_message.__globals__ is not namespace


def test_keyword_only_defaults_survive_the_binding():
    import aria_code.aria_cli as cli
    from aria_code.apps.cli.headless import HeadlessMixin

    original = HeadlessMixin.run_prompt
    bound = cli.ArtheraTerminal.run_prompt
    assert bound.__defaults__ == original.__defaults__
    assert bound.__kwdefaults__ == original.__kwdefaults__
