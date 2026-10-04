import io
from contextlib import redirect_stdout

from rich import box
from rich.console import Console

import aria_code.ui.robot as robot
from aria_code.ui.banner import control_status_label, render_startup_dashboard
from aria_code.ui.startup_dashboard import StartupDashboardViewModel, select_dashboard_layout


def _view(**overrides):
    values = {
        "version": "4.1.1",
        "runtime_label": "GPT-OSS 120B  [dim]cloud[/dim]",
        "cwd": "~/Desktop/aria-code",
        "control_status": "workspace-write · network on · privacy local-only",
        "health_status": "Ollama online · 3 models",
        "tool_count": 71,
        "skill_count": 14,
        "lang": "en",
    }
    values.update(overrides)
    return StartupDashboardViewModel(**values)


def _render(width, **overrides):
    robot._theme_cache = "dark"
    stream = io.StringIO()
    console = Console(file=stream, record=True, width=width, force_terminal=False)
    render_startup_dashboard(
        _view(**overrides),
        console=console,
        has_rich=True,
        rich_box=box,
        terminal_width=width,
    )
    robot._theme_cache = None
    return console.export_text()


def test_layout_breakpoints_are_stable():
    # Kept for callers of select_dashboard_layout; the banner itself has one layout.
    assert select_dashboard_layout(55) == "minimal"
    assert select_dashboard_layout(70) == "stacked"
    assert select_dashboard_layout(70, height=24) == "minimal"
    assert select_dashboard_layout(80, height=24) == "minimal"
    assert select_dashboard_layout(80, height=40) == "stacked"
    assert select_dashboard_layout(120) == "wide"


def test_one_compact_block_at_every_width():
    """The robot beside four lines — Claude Code's shape — with no frame, at any width."""
    for width in (120, 80, 55):
        lines = _render(width).rstrip("\n").splitlines()
        assert len(lines) == 4, (width, lines)
        assert all(len(line) <= width for line in lines), width
        assert not any(ch in "\n".join(lines) for ch in "╭╰│")
        assert lines[0].startswith("▗▛▀▀▀▀▀▜▖")


def test_the_four_lines_say_what_and_where():
    lines = _render(100, git_branch="main", git_dirty=True, mcp_server_count=1).splitlines()

    assert "Aria Code" in lines[0] and "v4.1.1" in lines[0]
    assert "GPT-OSS 120B" in lines[1] and "Local: Ollama 3" in lines[1]
    assert "~/Desktop/aria-code" in lines[2] and "main · dirty" in lines[2]
    assert "MCP 1 · 71 tools · 14 skills" in lines[3] and "workspace-write · network on" in lines[3]


def test_a_narrow_terminal_cuts_lines_instead_of_wrapping():
    lines = _render(50).rstrip("\n").splitlines()

    assert len(lines) == 4
    assert all(len(line) <= 50 for line in lines)


def test_notes_go_under_the_robot_only_when_needed():
    plain = _render(100).rstrip("\n").splitlines()
    first = _render(100, first_run=True, update_notice="Update available v4.1.1 → v4.2.0").rstrip("\n").splitlines()

    assert len(plain) == 4
    assert "Describe the task naturally" in first[4]
    assert "Update available" in first[5]


def test_narrow_terminal_keeps_update_reminder_visible():
    rendered = _render(55, update_notice="Update available: aria update")

    assert "Update available: aria update" in rendered


def test_plain_terminal_also_shows_robot():
    output = io.StringIO()
    with redirect_stdout(output):
        render_startup_dashboard(
            _view(), console=None, has_rich=False, rich_box=None,
        )
    text = output.getvalue()
    assert "▗▛▀▀▀▀▀▜▖  Aria Code v4.1.1" in text
    assert "[dim]" not in text


def test_chinese_view_model_localizes_sections():
    view = _view(lang="zh", first_run=True)

    assert view.getting_started_title == "快速开始"
    assert view.runtime_title == "运行状态"
    assert view.whats_new_title == "版本更新"
    assert view.capabilities == "71 个工具 · 14 个技能"


def test_capabilities_include_configured_mcp_servers():
    view = _view(mcp_server_count=2)

    assert view.capabilities == "MCP 2 · 71 tools · 14 skills"


def test_control_status_uses_retention_wording_and_localizes_permission():
    config = {
        "permission_mode": "workspace-write",
        "network_enabled": True,
        "data_sharing": False,
        "feedback_upload": False,
    }

    assert control_status_label(config, lang="en") == (
        "workspace-write · network on · local retention"
    )
    assert control_status_label(config, lang="zh") == (
        "工作区可写 · 网络开 · 本地留存"
    )
