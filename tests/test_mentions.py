""""@" searches files, folders, assets and saved resources together.

Attaching src/fx.py took "@", "file:", then the path: "@" listed only kinds,
and files appeared only after a path character. Codex's "@" goes straight to
results. The inserted text stays canonical (@file:…, @asset:…), so the
reference resolver is unchanged.
"""

from __future__ import annotations

import subprocess

import pytest

from aria_code.ui.mentions import Mention, MentionIndex


@pytest.fixture
def workspace(tmp_path):
    for path in ("src/fx.py", "tests/test_fx.py", "docs/fx notes.md", "node_modules/fx/index.js",
                 "strategies/momentum-v2.json", "reports/daily.md"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x", encoding="utf-8")
    return tmp_path


def test_one_word_finds_files_folders_and_resources(workspace):
    index = MentionIndex(workspace, symbols=["AAPL", "FXI"])
    found = [m.insert_text for m in index.search("fx")]
    assert found[0] == "file:src/fx.py"
    assert "file:tests/test_fx.py" in found and "asset:FXI" in found
    assert not any("node_modules" in text for text in found)        # skipped outside git too
    assert [m.insert_text for m in index.search("momentum")] == ["strategy:momentum-v2", "file:strategies/momentum-v2.json"]


def test_git_ignored_files_are_not_offered(workspace):
    subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
    (workspace / ".gitignore").write_text("reports/\n", encoding="utf-8")
    found = [m.insert_text for m in MentionIndex(workspace).search("daily")]
    assert "file:reports/daily.md" not in found
    assert "report:daily" in found                                  # still reachable as a report


def test_a_kind_narrows_and_a_typed_ticker_is_offered(workspace):
    index = MentionIndex(workspace, symbols=["AAPL"])
    assert {m.kind for m in index.search("fx", kind="file")} == {"file"}
    assert index.search("0700.HK")[0].insert_text == "asset:0700.HK"
    assert index.search("AAP")[0].insert_text == "asset:AAPL"
    assert "asset:NFLX" not in [m.insert_text for m in MentionIndex(workspace, symbols=["NFLX"]).search("fx")]


def test_paths_with_spaces_are_quoted():
    assert Mention("file", "docs/fx notes.md", 0).insert_text == 'file:"docs/fx notes.md"'


def test_recent_files_come_first(workspace):
    import os
    import time

    later = time.time() + 100
    os.utime(workspace / "tests/test_fx.py", (later, later))
    assert MentionIndex(workspace).recent_files(1) == ["tests/test_fx.py"]
