"""Code review as a service: target, isolated reviewer, structured findings, CI gate.

The old /review sent `git diff HEAD` (no untracked files, no way to review a
branch against main), cut it at 12,000 characters without saying so, asked
for free text in Chinese whatever the UI language, and ran inside the chat.
"""

from __future__ import annotations

import asyncio
import io
import json
import subprocess
from types import SimpleNamespace

import pytest

from aria_code import review_service as rs
from aria_code.apps.cli import review_runner


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / "calc.py").write_text("def add(a, b):\n    return a + b\n\n\ndef sub(a, b):\n    return a - b\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-q", "-m", "initial")
    return tmp_path


def reply(findings=(), correct=True, explanation="ok", confidence=0.9) -> str:
    return json.dumps({"findings": list(findings),
                       "overall_correctness": "patch is correct" if correct else "patch is incorrect",
                       "overall_explanation": explanation, "overall_confidence_score": confidence})


def finding(path="calc.py", start=6, end=6, priority=1, title="Subtracts the wrong way", confidence=0.8):
    return {"title": f"[P{priority}] {title}", "body": "b - a instead of a - b.", "confidence_score": confidence,
            "priority": priority, "code_location": {"file_path": path, "line_range": {"start": start, "end": end}}}


class TestTargets:
    def test_uncommitted_includes_new_files(self, repo):
        (repo / "calc.py").write_text((repo / "calc.py").read_text().replace("a - b", "b - a"))
        (repo / "fees.py").write_text("RATE = 0.2\n")
        inp = rs.collect(rs.ReviewTarget("uncommitted"), repo)
        assert inp.files == ["calc.py", "fees.py"]
        assert "+RATE = 0.2" in inp.diff and "+    return b - a" in inp.diff
        assert inp.hunks["fees.py"] == [(1, 1)]

    def test_staged_is_only_what_is_staged(self, repo):
        (repo / "calc.py").write_text("x = 1\n")
        (repo / "other.py").write_text("y = 2\n")
        git(repo, "add", "other.py")
        assert rs.collect(rs.ReviewTarget("staged"), repo).files == ["other.py"]

    def test_base_branch_is_reviewed_from_the_merge_base(self, repo):
        git(repo, "checkout", "-q", "-b", "feature")
        (repo / "feature.py").write_text("FLAG = True\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "feature")
        git(repo, "checkout", "-q", "main")
        (repo / "mainline.py").write_text("ONLY_ON_MAIN = 1\n")
        git(repo, "add", ".")
        git(repo, "commit", "-q", "-m", "main moves on")
        git(repo, "checkout", "-q", "feature")
        inp = rs.collect(rs.ReviewTarget("base", "main"), repo)
        assert inp.files == ["feature.py"], "main's own later commits are not part of this branch's change"
        assert inp.base_sha and "Merge base" in rs.build_messages(inp, rules="")[1]["content"]

    def test_commit_carries_its_title(self, repo):
        (repo / "calc.py").write_text("def add(a, b):\n    return a + b + 1\n")
        git(repo, "commit", "-qam", "off by one")
        inp = rs.collect(rs.ReviewTarget("commit", "HEAD"), repo)
        assert inp.commit_title == "off by one" and inp.files == ["calc.py"]

    def test_a_whole_file(self, repo):
        inp = rs.collect(rs.ReviewTarget("file", "calc.py"), repo)
        assert inp.files == ["calc.py"] and inp.hunks["calc.py"] == [(1, 6)]

    def test_outside_a_repository(self, tmp_path):
        with pytest.raises(rs.ReviewError, match="not inside a git repository"):
            rs.collect(rs.ReviewTarget("uncommitted"), tmp_path)

    def test_a_large_change_names_what_was_left_out(self, repo):
        for i in range(5):
            (repo / f"big{i}.py").write_text("x = 1\n" * 400)
        inp = rs.collect(rs.ReviewTarget("uncommitted"), repo, max_chars=4000)
        assert inp.truncated and inp.omitted_files
        prompt = rs.build_messages(inp, rules="")[1]["content"]
        assert "NOT shown" in prompt and all(name in prompt for name in inp.omitted_files)

    def test_arguments(self):
        assert rs.target_from_args([]) == rs.ReviewTarget("uncommitted")
        assert rs.target_from_args(["--base", "main"]) == rs.ReviewTarget("base", "main")
        assert rs.target_from_args(["--commit", "abc"]) == rs.ReviewTarget("commit", "abc")
        assert rs.target_from_args(["src/x.py"]) == rs.ReviewTarget("file", "src/x.py")
        with pytest.raises(rs.ReviewError):
            rs.target_from_args(["--base"])


class TestTheReviewerIsIsolated:
    def test_only_rubric_rules_and_change(self, repo):
        (repo / "AGENTS.md").write_text("Money is always Decimal, never float.\n")
        (repo / "calc.py").write_text("def add(a, b):\n    return float(a) + b\n")
        inp = rs.collect(rs.ReviewTarget("uncommitted"), repo)
        messages = rs.build_messages(inp, lang="zh")
        assert [m["role"] for m in messages] == ["system", "user"]
        assert "[P0]" in messages[0]["content"] and "Money is always Decimal" in messages[0]["content"]
        assert "简体中文" in messages[0]["content"]
        assert "float(a)" in messages[1]["content"]

    def test_nothing_to_review_never_calls_the_model(self, repo):
        async def model(messages):
            raise AssertionError("no change, no call")
        result = asyncio.run(rs.run_review(rs.collect(rs.ReviewTarget("uncommitted"), repo), model))
        assert result.correct is True and not result.findings

    def test_the_cli_adapter_offers_no_tools(self, monkeypatch):
        seen = {}

        class Provider:
            def __init__(self, config, model):
                seen["model"] = model

            async def stream(self, messages, tools):
                from aria_code.apps.cli.providers.base import LLMDone
                seen["tools"] = tools
                yield LLMDone(response=reply())

        monkeypatch.setattr("aria_code.apps.cli.providers.base.ConfiguredProvider", Provider)
        call = review_runner.make_model_call({"model": "google/gemini-2.5-pro", "review_model": "google/gemini-2.5-flash"})
        assert json.loads(asyncio.run(call([])))["overall_correctness"] == "patch is correct"
        assert seen == {"model": "google/gemini-2.5-flash", "tools": []}


class TestParsing:
    @pytest.mark.parametrize("wrap", [
        lambda s: s,
        lambda s: f"```json\n{s}\n```",
        lambda s: f"Here is my review:\n{s}\nThanks.",
    ])
    def test_json_in_any_wrapper(self, wrap):
        result = rs.parse_review(wrap(reply([finding()], correct=False)))
        assert result.structured and result.correct is False
        assert result.findings[0].label == "P1" and result.findings[0].title == "Subtracts the wrong way"

    def test_free_text_is_kept_not_lost(self):
        result = rs.parse_review("Looks fine to me overall.")
        assert not result.structured and result.explanation == "Looks fine to me overall."

    def test_priority_from_the_title_and_confidence_clamped(self):
        raw = finding(confidence=7)
        raw.pop("priority")
        f = rs.parse_review(reply([raw])).findings[0]
        assert f.priority == 1 and f.confidence == 1.0

    def test_findings_off_the_change_are_marked_and_sorted_last(self, repo):
        (repo / "calc.py").write_text((repo / "calc.py").read_text().replace("a - b", "b - a"))
        inp = rs.collect(rs.ReviewTarget("uncommitted"), repo)
        far = finding(start=40, end=41, priority=0, title="Something elsewhere")
        result = rs.parse_review(reply([far, finding(path=str(repo / "calc.py"))]), inp)
        assert [f.in_change for f in result.findings] == [True, False]
        assert result.findings[0].file_path == "calc.py", "absolute paths are made repo-relative"
        assert result.worst_priority() == 1, "a P0 outside the change does not gate the change"


class TestHeadless:
    def run(self, repo, argv, text):
        async def model(messages):
            return text
        out = io.StringIO()
        code = review_runner.run_headless(["--cwd", str(repo), *argv], model_call=model, config={}, out=out)
        return code, out.getvalue()

    def change(self, repo):
        (repo / "calc.py").write_text((repo / "calc.py").read_text().replace("a - b", "b - a"))

    def test_gate_fails_on_a_finding_at_the_threshold(self, repo):
        self.change(repo)
        assert self.run(repo, ["--fail-on", "P1"], reply([finding(priority=1)], correct=False))[0] == 1
        assert self.run(repo, ["--fail-on", "P0"], reply([finding(priority=1)], correct=False))[0] == 0

    def test_json_output(self, repo):
        self.change(repo)
        code, out = self.run(repo, ["--json"], reply([finding()], correct=False))
        data = json.loads(out)
        assert code == 0 and data["overall_correctness"] == "patch is incorrect"
        assert data["findings"][0]["priority_label"] == "P1" and data["findings"][0]["in_change"]

    def test_an_unstructured_reply_does_not_pass_a_gate(self, repo):
        self.change(repo)
        assert self.run(repo, ["--fail-on", "P1"], "LGTM")[0] == 2
        assert self.run(repo, [], "LGTM")[0] == 0

    def test_not_a_repository(self, tmp_path):
        assert self.run(tmp_path, [], reply())[0] == 2

    def test_the_entry_point_dispatches_before_loading_the_cli(self, monkeypatch):
        from aria_code.apps.cli import main as entry
        seen = {}
        monkeypatch.setattr("sys.argv", ["aria-code", "review", "--staged"])
        monkeypatch.setattr(review_runner, "run_headless", lambda argv: seen.setdefault("argv", argv) and 0)
        with pytest.raises(SystemExit):
            entry.main()
        assert seen["argv"] == ["--staged"]


class TestInteractiveCommand:
    def test_review_is_shown_and_remembered(self, repo, monkeypatch, capsys):
        from aria_code.apps.cli.commands.workflow_cmds import WorkflowCommandsMixin

        (repo / "calc.py").write_text((repo / "calc.py").read_text().replace("a - b", "b - a"))
        monkeypatch.chdir(repo)

        async def fake_model(messages):
            return reply([finding()], correct=False, explanation="One bug.")
        monkeypatch.setattr(review_runner, "make_model_call", lambda config, model=None: fake_model)
        monkeypatch.setattr("aria_code.apps.cli.commands.workflow_cmds._print_phase", lambda *a, **k: None)

        class Cli(WorkflowCommandsMixin):
            context = SimpleNamespace(has_rich=False, console=None)
            terminal = SimpleNamespace(config={"ui_lang": "en"}, conversation=[])

        cli = Cli()
        asyncio.run(cli.cmd_review(""))
        out = capsys.readouterr().out
        assert "Needs changes" in out and "1. [P1] Subtracts the wrong way  calc.py:6" in out
        assert cli.terminal.conversation[-1]["role"] == "assistant"
        assert "1. [P1] Subtracts the wrong way — calc.py:6" in cli.terminal.conversation[-1]["content"]
