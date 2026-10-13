"""Native SFT preparation must retain the existing eligibility and provenance."""
import json
import os
import subprocess

import pytest

from aria_code.training.sft_dataset import build
from test_native_runtime_domain import same_result
from test_training_pipeline import _examples, _suites, _traj


def make_data(root):
    suites = _suites(root)
    _traj(root, "core", "fix-a", 1, "pass")
    _traj(root, "core", "fix-a", 2, "pass", response="Second verified answer.")
    _traj(root, "core", "rec-b", 1, "pass")
    _traj(root, "core", "rec-b", 2, "fail")
    _traj(root, "core", "fin-c", 1, "pass", path_read="test_grade.py")
    _traj(root, "core", "fin-c", 2, "pass", acceptance={"verified": False})
    _traj(root, "hard", "hard-x", 1, "pass")
    # This duplicate has different attempt metadata, which must not make an
    # otherwise identical task trajectory into a second training example.
    _traj(root, "core", "rec-b", 3, "pass")
    _traj(root, "core", "unknown", 1, "pass")
    return suites


def native_dataset(root, suites, out, share):
    binary = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not binary:
        pytest.skip("Native Go runtime is built in the native-runtime CI job")
    return subprocess.run([binary, "training", "dataset", str(root / "traj"), "--suites", str(suites), "--out", str(out), "--validation-share", str(share)], text=True, capture_output=True, timeout=10)


@pytest.mark.parametrize("share", (0.0, 0.2, 0.5, 1.0))
def test_native_training_dataset_keeps_holdout_rules_dedup_and_provenance(tmp_path, share):
    suites = make_data(tmp_path)
    reference = build(tmp_path / "traj", suites, tmp_path / "python-out", validation_share=share)
    actual = native_dataset(tmp_path, suites, tmp_path / "go-out", share)
    assert actual.returncode == 0, actual.stderr
    same_result(json.loads(actual.stdout), reference)
    same_result(_examples(tmp_path / "go-out"), _examples(tmp_path / "python-out"))
    assert not set(reference["tasks"].get("train", [])) & set(reference["tasks"].get("validation", []))


def test_native_dataset_keeps_unicode_truncation_and_tool_result_types(tmp_path):
    suites = make_data(tmp_path)
    file = tmp_path / "traj/core/fix-a-1.jsonl"
    events = [json.loads(line) for line in file.read_text().splitlines()]
    result = events[3]["result"]
    result.update(content="中文😀" * 2200 + "<>&\\u2028\u2028", score=1.0)
    file.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")
    reference = build(tmp_path / "traj", suites, tmp_path / "python-out")
    actual = native_dataset(tmp_path, suites, tmp_path / "go-out", 0.2)
    assert actual.returncode == 0, actual.stderr
    same_result(json.loads(actual.stdout), reference)
    same_result(_examples(tmp_path / "go-out"), _examples(tmp_path / "python-out"))


def test_failed_native_dataset_build_preserves_existing_outputs(tmp_path):
    suites = make_data(tmp_path)
    out = tmp_path / "go-out"
    assert native_dataset(tmp_path, suites, out, 0.2).returncode == 0
    prior = {name: (out / name).read_bytes() for name in ("train.jsonl", "validation.jsonl", "manifest.json")}
    (tmp_path / "traj/core/broken.jsonl").write_text('{"type":"eval.task"}\n{broken}\n')
    actual = native_dataset(tmp_path, suites, out, 0.2)
    assert actual.returncode != 0
    assert all((out / name).read_bytes() == value for name, value in prior.items())
    assert not list(out.glob(".aria-sft-*"))
