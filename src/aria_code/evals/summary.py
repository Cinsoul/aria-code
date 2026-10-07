"""Turn eval reports into a Markdown scoreboard, and decide whether the run is healthy.

    python3 -m aria_code.evals.summary evals-core.json evals-operations.json

The suites ran in CI only with ``--check``: every fixture still starts red,
but no model ever attempted them, so nothing measured whether Aria can fix
code. The weekly workflow (.github/workflows/evals.yml) runs them with a real
model and writes this summary.

A task the model gets wrong is a result, not a broken build: the exit code is
1 only when a task could not run (ERROR) or no longer measures anything
(INVALID), the two outcomes that mean the harness, not the model, needs work.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def summarise(reports: list[dict], model: str = "") -> tuple[str, int]:
    """Markdown for the reports, and the exit code the run should have."""
    lines = [f"## Aria eval scoreboard{f' · {model}' if model else ''}", ""]
    unhealthy = 0
    for report in reports:
        suite = report.get("suite", "?")
        lines.append(f"### {suite}: {report.get('passed', 0)}/{report.get('scored', 0)} "
                     f"({report.get('pass_rate', 0):.0%})")
        extras = [f"{report[k]} {k}" for k in ("errored", "invalid") if report.get(k)]
        if extras:
            lines.append(f"Not scored: {', '.join(extras)}.")
        unhealthy += int(report.get("errored", 0)) + int(report.get("invalid", 0))
        lines += ["", "| Task | Outcome | Seconds | Detail |", "|---|---|---:|---|"]
        for result in report.get("results", []):
            detail = str(result.get("detail") or "").replace("|", "\\|")[:120]
            lines.append(f"| {result.get('task_id')} | {result.get('outcome')} | "
                         f"{result.get('seconds', 0):.0f} | {detail} |")
        by_tag = report.get("by_tag") or {}
        if by_tag:
            tags = ", ".join(f"{tag} {s['passed']}/{s['scored']}" for tag, s in by_tag.items() if s.get("scored"))
            if tags:
                lines += ["", f"By tag: {tags}"]
        lines.append("")
    return "\n".join(lines), (1 if unhealthy else 0)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    model = ""
    if args[:1] == ["--model"] and len(args) > 1:
        model, args = args[1], args[2:]
    reports = []
    for name in args:
        path = Path(name)
        if path.exists():
            reports.append(json.loads(path.read_text(encoding="utf-8")))
        else:
            print(f"(no report at {name})", file=sys.stderr)
    if not reports:
        print("no eval reports to summarise", file=sys.stderr)
        return 1
    text, code = summarise(reports, model)
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
