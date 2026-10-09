"""The startup robot is always the compact 9 × 4 one, as in Claude Code.

A larger rendition (inline PNG, or the PNG resampled to half-blocks) took
18 columns × 8 rows or more beside four lines of text.
"""

import io
import re

from rich.console import Console

from aria_code.ui import banner


def _console(stream=None, **kwargs):
    return Console(file=stream or io.StringIO(), width=100, force_terminal=True,
                   color_system="truecolor", **kwargs)


def test_the_robot_is_compact_in_a_wide_colour_terminal(monkeypatch):
    monkeypatch.delenv("ARIA_ROBOT_RENDER", raising=False)
    face, columns = banner._mascot(_console())
    assert columns == 9
    assert [len(row) for row in face.plain.splitlines()] == [9, 9, 9, 9]


def test_off_hides_the_robot(monkeypatch):
    monkeypatch.setenv("ARIA_ROBOT_RENDER", "off")
    face, columns = banner._mascot(_console())
    assert columns == 0 and face.plain == ""


def test_no_inline_image_is_written_even_in_iterm(monkeypatch):
    from aria_code.ui.startup_dashboard import StartupDashboardViewModel

    class Terminal(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("ARIA_ROBOT_RENDER", raising=False)
    stream = Terminal()
    view = StartupDashboardViewModel(version="1", runtime_label="Google Cloud", cwd="~/project",
                                     control_status="workspace-write · network on", health_status="ready",
                                     tool_count=90, skill_count=14, update_notice="Update available: aria update")
    banner.render_startup_dashboard(view, console=_console(stream), has_rich=True)
    output = stream.getvalue()
    assert "\x1b]1337;" not in output and "\x1b_G" not in output
    text = re.sub(r"\x1b\[[0-9;]*m", "", output)
    assert "▗▛▀▀▀▀▀▜▖" in text and "Update available" in text
