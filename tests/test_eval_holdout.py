"""Private holdout suites: scored beside the public ones, never published.

Twins in a private repository (the same skill as a public task, different
data) show whether the public score is inflated by leakage or by tuning on
the public bank. The run pages of this repository are public, so a holdout
suite may show up in them only as counts.
"""

from __future__ import annotations

import json

import yaml

from aria_code.evals.gap import gap, markdown, twins
from aria_code.evals.summary import main, mean_sem, summarise


def report(suite: str, outcomes: dict[str, list[str]]) -> dict:
    results = [{"task_id": t, "outcome": o, "seconds": 10, "detail": f"secret detail of {t}",
                "log_tail": [f"secret log of {t}"]} for t, os_ in outcomes.items() for o in os_]
    passed = sum(r["outcome"] == "pass" for r in results)
    return {"suite": suite, "passed": passed, "scored": len(results), "pass_rate": passed / len(results),
            "errored": 0, "invalid": 0, "results": results}


def write(tmp_path, name, data):
    path = tmp_path / name
    path.write_text(json.dumps(data) if not name.endswith(".yaml") else yaml.safe_dump(data))
    return path


def test_mean_and_standard_error_over_task_pass_rates():
    mean, sem, n = mean_sem(report("core", {"a": ["pass", "pass"], "b": ["pass", "fail"], "c": ["fail", "fail"]}))
    assert n == 3 and mean == 0.5
    assert abs(sem - 0.5 / 3 ** 0.5) < 1e-9          # sd of (1, .5, 0) is .5
    assert mean_sem({"results": [{"task_id": "a", "outcome": "error"}]}) is None


def test_the_scoreboard_carries_the_standard_error():
    text, _ = summarise([report("core", {"a": ["pass"], "b": ["fail"]})])
    assert "Mean task pass rate 50% ± 50% (SEM over 2 tasks)." in text


def test_a_private_report_shows_counts_and_nothing_else():
    private = report("holdout-ops", {"twin-secret-task": ["pass", "fail"]})
    text, code = summarise([report("core", {"a": ["pass"]})], "m", [private])
    assert code == 0
    assert "### holdout-ops (holdout): 1/2 (50%)" in text
    for leak in ("twin-secret-task", "detail of twin", "log of twin"):
        assert leak not in text
    assert "| a | pass |" in text                    # the public suite keeps its table


def test_the_cli_takes_private_reports_after_a_flag(tmp_path, capsys):
    pub = write(tmp_path, "evals-core.json", report("core", {"a": ["pass"]}))
    priv = write(tmp_path, "holdout.json", report("holdout", {"twin-x": ["fail"]}))
    assert main(["--model", "m", str(pub), "--private", str(priv)]) == 0
    out = capsys.readouterr().out
    assert "### holdout (holdout): 0/1" in out and "twin-x" not in out


def test_twins_pair_holdout_tasks_with_their_public_tasks(tmp_path):
    suite = write(tmp_path, "holdout.yaml", {"suite": "holdout", "tasks": [
        {"id": "h1", "twin_of": "a"}, {"id": "h2", "twin_of": "b"}, {"id": "h3"}]})
    assert twins([suite]) == {"h1": "a", "h2": "b"}


def test_a_public_score_that_does_not_carry_over_is_flagged(tmp_path):
    public = [write(tmp_path, "pub.json", report("core", {f"p{i}": ["pass"] * 3 for i in range(8)}))]
    holdout = [write(tmp_path, "hold.json", report("holdout", {f"h{i}": ["fail"] * 3 for i in range(8)}))]
    result = gap(public, holdout, {f"h{i}": f"p{i}" for i in range(8)})
    assert result["pairs"] == 8 and result["mean_gap"] == 1.0 and result["public_overstates"]
    text = markdown(result)
    assert "gap +100%" in text and "overstates" in text
    assert "h0" not in text and "p0" not in text


def test_equal_scores_are_not_called_a_gap(tmp_path):
    outcomes = {"x": ["pass", "fail"], "y": ["pass", "pass"], "z": ["fail", "fail"]}
    public = [write(tmp_path, "pub.json", report("core", outcomes))]
    holdout = [write(tmp_path, "hold.json", report("holdout", {f"h-{t}": o for t, o in outcomes.items()}))]
    result = gap(public, holdout, {f"h-{t}": t for t in outcomes} | {"h-missing": "nope"})
    assert result["mean_gap"] == 0 and not result["public_overstates"]
    assert result["unpaired"] == ["h-missing"]
    assert "No significant gap" in markdown(result) and "1 twins had no scored pair." in markdown(result)


def test_the_workflow_keeps_the_holdout_private():
    text = open(".github/workflows/evals.yml").read()
    job = yaml.safe_load(text)["jobs"]["evals"]
    steps = {s.get("name", s.get("uses")): s for s in job["steps"]}
    checkout = steps["Check out the holdout suites"]
    assert "env.HOLDOUT == 'true'" in checkout["if"]
    assert checkout["with"]["repository"] == "artheras/aria-evals-holdout"
    assert checkout["with"]["ssh-key"] == "${{ secrets.HOLDOUT_DEPLOY_KEY }}"
    assert checkout["with"]["persist-credentials"] is False
    run = steps["Run the holdout suites"]["run"]
    assert "--trajectories" not in run and "> /dev/null 2>&1" in run   # no task ids in the public log
    assert "--private" in steps["Scoreboard"]["run"] and "--markdown" in steps["Scoreboard"]["run"]
    upload = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/upload-artifact"))
    assert ".holdout" not in upload["with"]["path"]
