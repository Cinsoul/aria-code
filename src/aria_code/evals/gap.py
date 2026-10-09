"""In-sample minus out-of-sample: public tasks against their private twins.

A public task can end up in a model's training data, and a tuned model can
learn the public bank instead of the skill. Either way it scores well on the
public task and worse on a twin it has never seen: the same skill, with
different data, numbers and wording, kept in a private repository. SWE-bench
Pro reads leakage the same way, from the gap between its public and held-out
splits; a quant reads overfitting from the gap between in-sample and
out-of-sample returns.

A holdout suite names each twin's public task with ``twin_of``. This pairs
them, takes each side's pass rate over its repeats, and reports the mean gap
(public minus twin) with a bootstrap 95% interval. An interval above zero is
a warning that the public score overstates the skill.

    python -m aria_code.evals.gap --public evals-*.json --holdout holdout.json --suites holdout/suites/*.yaml

``--markdown`` prints counts and rates only, never a private task id, so the
section can go into a public job summary.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

from aria_code.training.compare import bootstrap_ci, rates


def twins(suite_files: Iterable[Path]) -> dict[str, str]:
    """Holdout task id -> the public task it is a twin of."""
    import yaml

    pairs = {}
    for suite_file in suite_files:
        doc = yaml.safe_load(Path(suite_file).read_text(encoding="utf-8")) or {}
        pairs.update({str(t["id"]): str(t["twin_of"]) for t in doc.get("tasks") or [] if t.get("twin_of")})
    return pairs


def gap(public_reports: Iterable[Path], holdout_reports: Iterable[Path], pairs: dict[str, str]) -> dict:
    public, _, _ = rates(public_reports)
    holdout, _, _ = rates(holdout_reports)
    rows = {h: (public[p], holdout[h]) for h, p in pairs.items() if p in public and h in holdout}
    diffs = [pub - twin for pub, twin in rows.values()]
    lo, hi = bootstrap_ci(diffs)
    mean = sum(diffs) / len(diffs) if diffs else 0.0
    return {
        "pairs": len(rows),
        "public_pass_rate": round(sum(p for p, _ in rows.values()) / len(rows), 4) if rows else None,
        "twin_pass_rate": round(sum(t for _, t in rows.values()) / len(rows), 4) if rows else None,
        "mean_gap": round(mean, 4),
        "ci95": [round(lo, 4), round(hi, 4)],
        "public_overstates": lo > 0,
        "unpaired": sorted(h for h in pairs if h not in rows),
    }


def markdown(result: dict) -> str:
    """The gap for a public summary: rates and the interval, no task ids."""
    if not result["pairs"]:
        return "### Public vs holdout\nNo twin pairs were scored on both sides.\n"
    lo, hi = result["ci95"]
    verdict = ("The public score overstates the skill: the interval is above 0." if result["public_overstates"]
               else "No significant gap: the interval includes 0 or is below it.")
    return "\n".join([
        "### Public vs holdout",
        f"{result['pairs']} twin pairs. Public {result['public_pass_rate']:.0%}, "
        f"holdout {result['twin_pass_rate']:.0%}; gap {result['mean_gap']:+.0%} "
        f"(95% CI {lo:+.0%} to {hi:+.0%}).",
        verdict,
        *([f"{len(result['unpaired'])} twins had no scored pair."] if result["unpaired"] else []),
        "",
    ])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gap between public tasks and their private twins.")
    ap.add_argument("--public", nargs="+", type=Path, required=True)
    ap.add_argument("--holdout", nargs="+", type=Path, required=True)
    ap.add_argument("--suites", nargs="+", type=Path, required=True,
                    help="the holdout suite YAML files (their tasks carry twin_of)")
    ap.add_argument("--markdown", action="store_true", help="counts and rates only, safe for a public summary")
    args = ap.parse_args(argv)
    result = gap(args.public, args.holdout, twins(args.suites))
    print(markdown(result) if args.markdown else json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
