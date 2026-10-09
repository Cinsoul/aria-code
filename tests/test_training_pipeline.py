"""The training set obeys its rules in code: no look-ahead, no leakage, no lucky runs.

docs/training-protocol.md treats a fine-tune like a strategy under test: the
locked holdout is never seen, a task never sits in two splits, only verified
passes are examples, and an improvement is claimed only when its interval
excludes zero.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from aria_code.training.compare import bootstrap_ci, compare, sign_test
from aria_code.training.sft_dataset import build, load_trajectories, split_of, to_example


def _suites(root: Path) -> Path:
    d = root / "suites"
    d.mkdir()
    (d / "core.yaml").write_text(textwrap.dedent("""
        suite: core
        tasks:
          - {id: fix-a, prompt: p, verify: v, tags: [software]}
          - {id: rec-b, prompt: p, verify: v, tags: [logistics]}
          - {id: fin-c, prompt: p, verify: v, tags: [finance], hidden: [test_grade.py]}
    """))
    (d / "hard.yaml").write_text(textwrap.dedent("""
        suite: hard
        tasks:
          - {id: hard-x, prompt: p, verify: v, tags: [finance, hard], hidden: [test_x.py]}
    """))
    return d


def _traj(root: Path, suite: str, task: str, attempt: int, outcome: str, *, path_read="calc.py",
          acceptance=None, response="Fixed; tests pass."):
    d = root / "traj" / suite
    d.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "eval.task", "task_id": task, "attempt": attempt, "model": "google/gemini-3.5-flash",
         "prompt": f"fix {task}"},
        {"type": "turn.started", "prompt": f"fix {task}"},
        {"type": "tool.started", "tool": "read_file", "params": {"path": path_read}},
        {"type": "tool.completed", "tool": "read_file", "success": True, "result": {"content": "x = 1"}},
        {"type": "tool.started", "tool": "run_command", "params": {"command": "pytest -q"}},
        {"type": "tool.completed", "tool": "run_command", "success": True, "result": {"exit_code": 0}},
        {"type": "turn.completed", "success": True, "response": response, "acceptance": acceptance},
        {"type": "eval.outcome", "outcome": outcome, "detail": "", "changed": ["calc.py"], "seconds": 30.0},
    ]
    (d / f"{task}-{attempt}.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


@pytest.fixture
def data(tmp_path):
    suites = _suites(tmp_path)
    _traj(tmp_path, "core", "fix-a", 1, "pass")
    _traj(tmp_path, "core", "fix-a", 2, "pass", response="Done: tests pass now.")
    _traj(tmp_path, "core", "rec-b", 1, "pass")
    _traj(tmp_path, "core", "rec-b", 2, "fail")
    _traj(tmp_path, "core", "fin-c", 1, "pass", path_read="test_grade.py")
    _traj(tmp_path, "core", "fin-c", 2, "pass", acceptance={"verified": False})
    _traj(tmp_path, "hard", "hard-x", 1, "pass")
    return tmp_path, suites


def _examples(out: Path) -> list[dict]:
    rows = []
    for name in ("train.jsonl", "validation.jsonl"):
        p = out / name
        rows += [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    return rows


def test_only_verified_passes_outside_the_holdout_become_examples(data):
    root, suites = data
    m = build(root / "traj", suites, root / "out")
    assert sum(m["examples"].values()) == 3                     # fix-a x2, rec-b x1
    assert m["excluded"] == {"outcome fail": 1, "touched a grader": 1,
                             "its own checks failed": 1, "locked holdout": 1}
    prompts = {e["contents"][0]["parts"][0]["text"] for e in _examples(root / "out")}
    assert prompts == {"fix fix-a", "fix rec-b"}


def test_the_holdout_never_reaches_a_file(data):
    root, suites = data
    m = build(root / "traj", suites, root / "out")
    assert m["holdout_tasks"] == ["hard-x"]
    blob = (root / "out" / "train.jsonl").read_text() + (root / "out" / "validation.jsonl").read_text()
    assert "hard-x" not in blob


def test_a_task_never_sits_in_two_splits(data):
    root, suites = data
    m = build(root / "traj", suites, root / "out", validation_share=0.5)
    assert not set(m["tasks"].get("train", [])) & set(m["tasks"].get("validation", []))
    assert split_of("fix-a") == split_of("fix-a")


def test_the_example_is_gemini_tuning_format(data):
    root, _ = data
    t = [t for t in load_trajectories(root / "traj") if t.task_id == "fix-a"][0]
    ex = to_example(t, "system text")
    assert ex["systemInstruction"]["parts"][0]["text"] == "system text"
    roles = [c["role"] for c in ex["contents"]]
    assert roles == ["user", "model", "user", "model", "user", "model"]
    assert ex["contents"][1]["parts"][0]["functionCall"] == {"name": "read_file", "args": {"path": "calc.py"}}
    assert ex["contents"][2]["parts"][0]["functionResponse"]["name"] == "read_file"
    assert ex["contents"][-1]["parts"][0]["text"] == "Fixed; tests pass."


def test_the_manifest_records_provenance_and_exposure(data):
    root, suites = data
    m = build(root / "traj", suites, root / "out")
    saved = json.loads((root / "out" / "manifest.json").read_text())
    assert saved["inputs"] and all(len(h) == 64 for h in saved["inputs"].values())
    assert saved["models"] == ["google/gemini-3.5-flash"]
    domains = {d for c in m["exposure_by_domain"].values() for d in c}
    assert domains <= {"software", "logistics", "finance", "other"}


def test_an_identical_trajectory_counts_once(data):
    root, suites = data
    src = root / "traj" / "core" / "rec-b-1.jsonl"
    (root / "traj" / "core" / "rec-b-3.jsonl").write_text(src.read_text().replace('"attempt": 1', '"attempt": 3'))
    m = build(root / "traj", suites, root / "out")
    assert m["excluded"].get("duplicate") == 1


# --- compare -------------------------------------------------------------------


def _report(path: Path, outcomes: dict[str, list[str]], seconds=30.0):
    results = [{"task_id": t, "outcome": o, "seconds": seconds} for t, os_ in outcomes.items() for o in os_]
    path.write_text(json.dumps({"results": results}))
    return path


def test_a_real_improvement_has_an_interval_above_zero(tmp_path):
    tasks = [f"t{i}" for i in range(20)]
    base = _report(tmp_path / "b.json", {t: ["fail", "fail", "pass"] for t in tasks})
    cand = _report(tmp_path / "c.json", {t: ["pass", "pass", "pass"] for t in tasks}, seconds=40.0)
    r = compare([base], [cand])
    assert r["tasks_compared"] == 20 and r["tasks_better"] == 20
    assert r["ci95"][0] > 0 and r["improved"] is True
    assert r["sign_test_p"] < 0.001
    assert r["mean_seconds"] == {"baseline": 30.0, "candidate": 40.0}


def test_noise_is_not_an_improvement(tmp_path):
    base = _report(tmp_path / "b.json", {"a": ["pass"], "b": ["fail"], "c": ["pass"], "d": ["fail"]})
    cand = _report(tmp_path / "c.json", {"a": ["fail"], "b": ["pass"], "c": ["pass"], "d": ["pass"]})
    r = compare([base], [cand])
    assert r["improved"] is False and r["ci95"][0] <= 0


def test_errors_are_not_counted_as_failures(tmp_path):
    base = _report(tmp_path / "b.json", {"a": ["pass", "error"], "b": ["pass"]})
    cand = _report(tmp_path / "c.json", {"a": ["pass"], "b": ["pass", "invalid"]})
    r = compare([base], [cand])
    assert r["per_task"]["a"] == {"baseline": 1.0, "candidate": 1.0}
    assert r["unscored"] == {"baseline": {"error": 1}, "candidate": {"invalid": 1}}


def test_statistics_helpers():
    assert sign_test(0, 0) == 1.0
    assert sign_test(10, 0) == pytest.approx(2 / 1024)
    lo, hi = bootstrap_ci([0.0] * 10)
    assert lo == hi == 0.0
