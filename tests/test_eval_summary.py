"""The weekly eval scoreboard, and when a run counts as broken.

A task the model gets wrong is a measurement; the run is unhealthy only when a
task could not run (ERROR) or no longer measures anything (INVALID).
"""

from __future__ import annotations

import json

import yaml

from aria_code.evals.summary import main, summarise

REPORT = {
    "suite": "core", "pass_rate": 0.6667, "passed": 2, "failed": 1, "invalid": 0, "errored": 0, "scored": 3,
    "by_tag": {"python": {"passed": 2, "scored": 3, "pass_rate": 0.6667}},
    "results": [
        {"task_id": "fix-failing-test", "outcome": "PASS", "seconds": 81.2, "detail": ""},
        {"task_id": "off-by-one", "outcome": "PASS", "seconds": 64.0, "detail": ""},
        {"task_id": "reconcile-waybills", "outcome": "FAIL", "seconds": 140.5, "detail": "edited a | protected file"},
    ],
}


def test_a_wrong_answer_is_a_result_not_a_broken_run():
    text, code = summarise([REPORT], "google/gemini-2.5-flash")
    assert code == 0
    assert "## Aria eval scoreboard · google/gemini-2.5-flash" in text
    assert "### core: 2/3 (67%)" in text
    assert "| reconcile-waybills | FAIL | 140 | edited a \\| protected file |" in text
    assert "By tag: python 2/3" in text


def test_errored_or_invalid_tasks_fail_the_run():
    for key in ("errored", "invalid"):
        text, code = summarise([dict(REPORT, **{key: 1})])
        assert code == 1 and f"Not scored: 1 {key}." in text


def test_the_cli_reads_report_files(tmp_path, capsys):
    path = tmp_path / "evals-core.json"
    path.write_text(json.dumps(REPORT))
    assert main(["--model", "m", str(path), str(tmp_path / "missing.json")]) == 0
    assert "### core: 2/3" in capsys.readouterr().out
    assert main([str(tmp_path / "missing.json")]) == 1


def test_the_workflow_signs_in_without_a_key():
    workflow = yaml.safe_load(open(".github/workflows/evals.yml"))
    job = workflow["jobs"]["evals"]
    assert workflow["permissions"]["id-token"] == "write"
    uses = [step.get("uses", "") for step in job["steps"]]
    assert any(u.startswith("google-github-actions/auth@") for u in uses)
    assert "GEMINI_API_KEY" not in open(".github/workflows/evals.yml").read()
    assert job["env"]["GOOGLE_GENAI_USE_VERTEXAI"] == "true"


def test_the_reason_a_task_did_not_pass_reaches_the_summary():
    """The first CI run said only "the agent did not complete (exit 1)"; the reason was in the job log."""
    from aria_code.evals.harness import ERROR, PASS, TaskResult

    errored = TaskResult(task_id="stripe-refund-validation", outcome=ERROR, exit_code=1,
                         detail="the agent did not complete (exit 1); check still red",
                         log="starting\nAuthorization: Bearer abc.def\nVertex 400: INVALID_ARGUMENT")
    passed = TaskResult(task_id="off-by-one", outcome=PASS, log="12 passed")
    assert errored.to_dict()["log_tail"] == ["starting", "Authorization: ***", "Vertex 400: INVALID_ARGUMENT"]
    assert passed.to_dict()["log_tail"] == []

    report = dict(REPORT, results=[errored.to_dict(), passed.to_dict()], errored=1)
    text, code = summarise([report])
    assert code == 1
    assert "<details><summary>stripe-refund-validation: last lines of the log</summary>" in text
    assert "Vertex 400: INVALID_ARGUMENT" in text and "abc.def" not in text
    assert "off-by-one: last lines" not in text
