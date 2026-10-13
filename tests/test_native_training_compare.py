"""Compare the Go training evaluator with the existing Python business rules."""
import json
import os
import random
import subprocess

import pytest

from aria_code.training.compare import compare
from test_native_runtime_domain import same_result


@pytest.mark.parametrize("seed", range(12))
def test_native_training_statistics_match_existing_reports(tmp_path, seed):
    binary = os.environ.get("ARIA_GO_RUNTIME_BINARY")
    if not binary:
        pytest.skip("Native Go runtime is built in the native-runtime CI job")
    rng = random.Random(seed)
    paths = []
    for name in ("baseline", "candidate"):
        results = []
        for task in range(8):
            if seed == 0:
                continue
            for attempt in range(4):
                outcome = rng.choice(("pass", "fail", "error", "invalid"))
                results.append(dict(task_id=f"task-{task}", outcome=outcome, seconds=10 + attempt))
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(dict(results=results)), encoding="utf-8")
        paths.append(path)
    process = subprocess.run([binary, "training", "compare", "--baseline", str(paths[0]), "--candidate", str(paths[1])], capture_output=True, text=True, timeout=10)
    assert process.returncode == 0, process.stderr
    same_result(json.loads(process.stdout), compare(paths[:1], paths[1:]))
