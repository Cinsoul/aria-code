""""/" opens on what a session needs; /help fits on one screen.

The popup listed 181 entries — 167 commands and 14 skills — and /help ran to
about 90 lines. Codex lists only session controls under "/" and shows eight
rows. Every command still runs when typed; this only changes what is offered.
"""

from __future__ import annotations

import io

import pytest

pytest.importorskip("prompt_toolkit")
from prompt_toolkit.document import Document
from rich.console import Console

from aria_code.apps.cli.commands.catalog import (
    COMMAND_ALIASES,
    CORE_SLASH_COMMANDS,
    ENTRY_SLASH_COMMANDS,
    HELP_TOPICS,
    popup_rank,
    short_description,
)
from aria_code.ui.completer import AriaPTCompleter


def _noop(_args):
    return None


COMMANDS = {name: (_noop, f"{name[1:]} things: {name} ARG") for name in (
    *CORE_SLASH_COMMANDS, *ENTRY_SLASH_COMMANDS, "/realty", "/read", "/risk", "/providers", "/services",
    "/vision", "/upload-image", "/stat-arb", "/regen", "/recap", "/recall", "/rename", "/reject-change")}


def _popup(text, commands=COMMANDS, skills=()):
    completer = AriaPTCompleter(commands, list(skills), [], lang="en")
    return [item.text for item in completer.get_completions(Document(text), None)]


def test_a_bare_slash_offers_the_core_then_the_entry_points():
    assert _popup("/") == [*CORE_SLASH_COMMANDS, *ENTRY_SLASH_COMMANDS]
    assert len(_popup("/")) <= 24


def test_typing_reaches_every_command_and_ranks_the_tiers_first():
    assert _popup("/ris")[0] == "/risk"
    assert _popup("/stat")[:2] == ["/status", "/stat-arb"]
    re = _popup("/re")
    assert re[0] == "/review" and re.index("/report") < re.index("/realty")


def test_an_alias_shows_only_when_typed():
    assert "/upload-image" not in _popup("/")
    assert "/upload-image" not in _popup("/i")
    assert _popup("/upl") == ["/upload-image"]
    assert COMMAND_ALIASES["/upload-image"] == "/vision"


def test_scattered_matches_drop_out_once_there_are_enough_close_ones():
    assert "/providers" not in _popup("/re")


def test_descriptions_lose_their_usage_tail():
    assert short_description("Technical indicators: /ta AAPL [days=120]") == "Technical indicators"
    assert short_description("Runtime: engine · model · tools · context") == "Runtime: engine · model · tools · context"
    completer = AriaPTCompleter(COMMANDS, [], [], lang="en")
    meta = str(next(completer.get_completions(Document("/ta"), None)).display_meta_text)
    assert "/ta ARG" not in meta


def test_tiers_and_topics_are_consistent():
    assert not set(CORE_SLASH_COMMANDS) & set(ENTRY_SLASH_COMMANDS)
    assert popup_rank("/help") == 0 and popup_rank("/ta") == 1 and popup_rank("/realty") == 2
    assert len({topic.key for topic in HELP_TOPICS}) == len(HELP_TOPICS)


def test_every_tiered_command_exists():
    import sys

    sys.argv = ["aria-code"]
    import aria_code.aria_cli as cli

    terminal = cli.ArtheraTerminal(dict(cli.DEFAULT_CONFIG))
    table = terminal.commands.commands
    missing = [name for name in (*CORE_SLASH_COMMANDS, *ENTRY_SLASH_COMMANDS) if name not in table]
    missing += [name for topic in HELP_TOPICS for name in topic.commands if name not in table]
    assert not missing, missing


@pytest.mark.parametrize("width, lang", [(100, "en"), (80, "en"), (100, "zh")])
def test_help_fits_on_one_screen(width, lang, monkeypatch):
    import sys

    sys.argv = ["aria-code"]
    import aria_code.aria_cli as cli

    terminal = cli.ArtheraTerminal(dict(cli.DEFAULT_CONFIG, ui_lang=lang))
    console = Console(file=io.StringIO(), width=width, color_system=None)
    monkeypatch.setattr(terminal.commands.context, "console", console)
    monkeypatch.setattr(terminal.commands.context, "has_rich", True)
    terminal.commands.cmd_help("")
    lines = console.file.getvalue().splitlines()
    assert len(lines) <= 40
    assert all(len(line.rstrip()) <= width for line in lines)
    text = "\n".join(lines)
    assert "/help" in text and "/inventory" in text and "/ta" in text
    assert "/gen-bot" not in text            # skills and the long tail are a topic away


def test_help_topics_and_all_still_list_everything(monkeypatch):
    import sys

    sys.argv = ["aria-code"]
    import aria_code.aria_cli as cli

    terminal = cli.ArtheraTerminal(dict(cli.DEFAULT_CONFIG))
    console = Console(file=io.StringIO(), width=120, color_system=None)
    monkeypatch.setattr(terminal.commands.context, "console", console)
    monkeypatch.setattr(terminal.commands.context, "has_rich", True)
    terminal.commands.cmd_help("market")
    market = console.file.getvalue()
    assert "/quote" in market and "/ta AAPL [days=120]" in market
    console.file = io.StringIO()
    terminal.commands.cmd_help("all")
    assert len(console.file.getvalue().splitlines()) > 60


def _containers(container):
    yield container
    for child in container.get_children():
        yield from _containers(child)


def test_the_menu_has_room_and_the_footer_leaves_with_the_prompt():
    """The inline panel is as tall as its layout: the menu was clipped to two
    rows under the input, and the rule and status line stayed in the
    scrollback after every question."""
    import asyncio

    from prompt_toolkit.application.current import set_app
    from prompt_toolkit.buffer import CompletionState
    from prompt_toolkit.completion import Completion
    from prompt_toolkit.layout import ConditionalContainer, Window

    from aria_code.ui.input_box import MENU_ROWS, PanelInputConfig, _build_panel_input_application

    app = _build_panel_input_application(config=PanelInputConfig())
    footer = next(c for c in _containers(app.layout.container) if isinstance(c, ConditionalContainer))
    spacer = [c for c in _containers(footer.content) if isinstance(c, Window)][-1]
    buffer = app.layout.current_buffer
    assert spacer.preferred_height(80, 40).preferred == 0
    buffer.complete_state = CompletionState(buffer.document, [Completion("/help")])
    assert spacer.preferred_height(80, 40).preferred == MENU_ROWS

    with set_app(app):
        assert footer.filter()                  # typing: rule, status line, menu room
        app.future = asyncio.get_event_loop_policy().new_event_loop().create_future()
        app.future.set_result("")
        assert not footer.filter()              # submitted: only "› prompt" remains
