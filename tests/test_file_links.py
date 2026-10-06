"""Saved files are links a terminal can open.

They were linked as [link=/Users/…/chart.html]: terminal hyperlinks (OSC 8)
take a URI, so a terminal that supports them had nothing to open, and the
line showed only "232347_AAPL_chart.html".
"""

from __future__ import annotations

import io
import pathlib
import re

from rich.console import Console

from aria_code.ui.render.output import file_uri

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "aria_code"


def test_a_path_becomes_a_file_uri(tmp_path):
    target = tmp_path / "my charts" / "AAPL_chart.html"
    assert file_uri(str(target)) == target.resolve().as_uri()
    assert file_uri(str(target)).startswith("file:///") and "%20" in file_uri(str(target))
    assert file_uri("https://example.com/x") == "https://example.com/x"
    assert file_uri("") == ""


def test_the_terminal_receives_the_uri(tmp_path):
    target = tmp_path / "AAPL_chart.html"
    console = Console(file=io.StringIO(), force_terminal=True, color_system="truecolor")
    console.print(f"saved: [link={file_uri(target)}]AAPL_chart.html[/link]")
    assert f"\x1b]8;id=" in console.file.getvalue() and target.resolve().as_uri() in console.file.getvalue()


def test_every_file_link_goes_through_file_uri():
    raw = []
    for path in SRC.rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for target in re.findall(r"\[link=\{([^}]+)\}\]", line):
                if not target.startswith("_file_uri(") and "url" not in target.lower():
                    raw.append(f"{path.relative_to(SRC)}:{number}: {target}")
    assert not raw, raw
