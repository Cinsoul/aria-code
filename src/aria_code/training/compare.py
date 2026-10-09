"""Is a candidate model really better than the baseline? Paired, with uncertainty.

A single eval run is one draw: Text2WetLab measured single-attempt scores
moving by up to 0.70 on a task between two identical runs. So, as a strategy
is judged on its excess return with a confidence interval rather than one
good month:

- **Paired by task.** Only tasks both runs scored are compared; each task's
  difference is candidate pass rate minus baseline pass rate over its repeats.
- **Bootstrap interval.** The mean difference is resampled over tasks
  (10,000 draws, fixed seed) for a 95% interval. An interval that includes 0
  is not evidence of improvement.
- **Sign test.** How many tasks got better versus worse, with an exact
  two-sided binomial p-value.
- **Errors are not failures.** ERROR and INVALID attempts (quota, timeouts, a
  broken fixture) are left out of the rates, and counted.
- **Cost.** Mean seconds per attempt for each side: a score bought with
  twice the latency is reported as such.

    python -m aria_code.training.compare baseline/*.json --candidate tuned/*.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from typing import Iterable

SCORED = ("pass", "fail")


def rates(report_paths: Iterable[Path]) -> tuple[dict[str, float], dict[str, int], float]:
    """Per-task pass rate over scored attempts, unscored counts, mean seconds."""
    passed: dict[str, int] = defaultdict(int)
    scored: dict[str, int] = defaultdict(int)
    unscored: dict[str, int] = defaultdict(int)
    seconds: list[float] = []
    for path in report_paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for r in data.get("results") or []:
            tid, outcome = str(r["task_id"]), str(r["outcome"])
            if outcome in SCORED:
                scored[tid] += 1
                passed[tid] += outcome == "pass"
                seconds.append(float(r.get("seconds") or 0))
            else:
                unscored[outcome] += 1
    rate = {t: passed[t] / scored[t] for t in scored}
    return rate, dict(unscored), (sum(seconds) / len(seconds) if seconds else 0.0)


def bootstrap_ci(diffs: list[float], draws: int = 10_000, seed: int = 7, level: float = 0.95) -> tuple[float, float]:
    if not diffs:
        return (0.0, 0.0)
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(draws))
    lo = means[int((1 - level) / 2 * draws)]
    hi = means[min(draws - 1, int((1 + level) / 2 * draws))]
    return (lo, hi)


def sign_test(better: int, worse: int) -> float:
    """Exact two-sided binomial p-value under 'no difference' (ties dropped)."""
    n = better + worse
    if n == 0:
        return 1.0
    k = min(better, worse)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def compare(baseline: Iterable[Path], candidate: Iterable[Path]) -> dict:
    base, base_unscored, base_s = rates(baseline)
    cand, cand_unscored, cand_s = rates(candidate)
    common = sorted(set(base) & set(cand))
    diffs = [cand[t] - base[t] for t in common]
    better = sum(d > 0 for d in diffs)
    worse = sum(d < 0 for d in diffs)
    lo, hi = bootstrap_ci(diffs)
    mean = sum(diffs) / len(diffs) if diffs else 0.0
    return {
        "tasks_compared": len(common),
        "baseline_pass_rate": round(sum(base[t] for t in common) / len(common), 4) if common else None,
        "candidate_pass_rate": round(sum(cand[t] for t in common) / len(common), 4) if common else None,
        "mean_difference": round(mean, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "tasks_better": better,
        "tasks_worse": worse,
        "tasks_same": len(common) - better - worse,
        "sign_test_p": round(sign_test(better, worse), 4),
        "improved": lo > 0,
        "only_in_baseline": sorted(set(base) - set(cand)),
        "only_in_candidate": sorted(set(cand) - set(base)),
        "unscored": {"baseline": base_unscored, "candidate": cand_unscored},
        "mean_seconds": {"baseline": round(base_s, 1), "candidate": round(cand_s, 1)},
        "per_task": {t: {"baseline": round(base[t], 3), "candidate": round(cand[t], 3)} for t in common},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Paired comparison of two sets of eval reports.")
    ap.add_argument("baseline", nargs="+", type=Path)
    ap.add_argument("--candidate", nargs="+", type=Path, required=True)
    args = ap.parse_args(argv)
    result = compare(args.baseline, args.candidate)
    summary = {k: v for k, v in result.items() if k != "per_task"}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
