"""Eval trajectories -> a supervised fine-tuning set, built the way a quant builds a backtest.

The rules (docs/training-protocol.md) are enforced here, in code, not by care:

- **No look-ahead.** Tasks in the locked holdout suites (``hard`` by default)
  never produce an example, and a trajectory that touched a grader file is
  dropped: a model trained on the answer key measures nothing.
- **Split by task, never by attempt.** Two attempts at one task are near
  copies; one in train and one in validation is leakage. The split is a
  stable hash of the task id, so it does not move when data is added.
- **No survivorship of lucky runs.** Only attempts the grader passed *and*
  whose own acceptance check did not fail become examples.
- **Exposure is reported.** Examples per domain and split, so a set that is
  90% one domain is visible before it trains a lopsided model.
- **Provenance.** The manifest records each input file's sha256, the rules
  and the counts, so a tuned model can be traced to exactly what it saw.

Output is the Vertex AI Gemini supervised-tuning format: one JSON object per
line with ``systemInstruction`` and ``contents``, tool use as
``functionCall`` / ``functionResponse`` parts.

    python -m aria_code.training.sft_dataset trajectories/ --suites evals/suites --out sft/
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

DEFAULT_HOLDOUT = ("hard",)
DOMAINS = ("software", "finance", "payments", "logistics")
RESULT_CHARS = 6_000          # one tool result in an example; long outputs are cut, not dropped


@dataclass
class Trajectory:
    path: Path
    suite: str
    task_id: str
    attempt: int
    model: str
    prompt: str
    events: list[dict] = field(default_factory=list)
    outcome: dict = field(default_factory=dict)

    @property
    def final(self) -> dict:
        return next((e for e in reversed(self.events) if e.get("type") == "turn.completed"), {})


@dataclass
class TaskInfo:
    suite: str
    tags: tuple[str, ...]
    hidden: tuple[str, ...]


def load_trajectories(root: Path) -> list[Trajectory]:
    out = []
    for path in sorted(Path(root).rglob("*.jsonl")):
        lines = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip().startswith("{")]
        if not lines or lines[0].get("type") != "eval.task":
            continue
        head = lines[0]
        outcome: dict = next((l for l in reversed(lines) if l.get("type") == "eval.outcome"), {})
        events = [l for l in lines[1:] if l.get("type") not in ("eval.task", "eval.outcome")]
        out.append(Trajectory(path=path, suite=path.parent.name, task_id=str(head.get("task_id")),
                              attempt=int(head.get("attempt") or 1), model=str(head.get("model") or ""),
                              prompt=str(head.get("prompt") or ""), events=events, outcome=outcome))
    return out


def load_tasks(suites_dir: Path) -> dict[str, TaskInfo]:
    import yaml

    tasks = {}
    for suite_file in sorted(Path(suites_dir).glob("*.yaml")):
        doc = yaml.safe_load(suite_file.read_text(encoding="utf-8")) or {}
        for t in doc.get("tasks") or []:
            tasks[str(t["id"])] = TaskInfo(suite=str(doc.get("suite") or suite_file.stem),
                                           tags=tuple(t.get("tags") or ()),
                                           hidden=tuple(t.get("hidden") or ()))
    return tasks


def split_of(task_id: str, validation_share: float = 0.2) -> str:
    """"train" or "validation", fixed by the task id alone."""
    bucket = int(hashlib.sha256(task_id.encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "validation" if bucket < validation_share else "train"


def domain_of(tags: Iterable[str]) -> str:
    tags = set(tags)
    for d in DOMAINS:
        if d in tags:
            return "finance" if d == "payments" else d
    return "other"


def why_excluded(t: Trajectory, info: TaskInfo | None, holdout: tuple[str, ...]) -> str | None:
    if info is None:
        return "task not in any suite"
    if info.suite in holdout or t.suite in holdout:
        return "locked holdout"
    if t.outcome.get("outcome") != "pass":
        return f"outcome {t.outcome.get('outcome') or 'missing'}"
    final = t.final
    if not final:
        return "no turn.completed"
    acceptance = final.get("acceptance") or {}
    if isinstance(acceptance, dict) and acceptance.get("verified") is False:
        return "its own checks failed"
    text = json.dumps(t.events, ensure_ascii=False)
    graders = set(info.hidden) | {"test_*_hidden.py"}
    for event in t.events:
        for value in (event.get("params") or {}).values():
            name = Path(str(value)).name
            if any(fnmatch.fnmatch(name, g) for g in graders):
                return "touched a grader"
    if "eval.outcome" in text or "reward.json" in text:
        return "grader output in the trajectory"
    return None


def to_example(t: Trajectory, system: str) -> dict:
    """One Vertex Gemini SFT record from one trajectory."""
    contents: list[dict] = [{"role": "user", "parts": [{"text": t.prompt}]}]
    pending: list[dict] = []
    for event in t.events:
        kind = event.get("type")
        if kind == "tool.started":
            call = {"functionCall": {"name": event.get("tool"), "args": event.get("params") or {}}}
            if contents[-1]["role"] == "model" and not pending:
                contents[-1]["parts"].append(call)
            else:
                contents.append({"role": "model", "parts": [call]})
            pending.append(event)
        elif kind == "tool.completed" and pending:
            pending.pop(0)
            result = event.get("result")
            if result is None:
                result = {"success": event.get("success"), "error": event.get("error", "")}
            body = json.dumps(result, ensure_ascii=False)
            if len(body) > RESULT_CHARS:
                result = {"truncated": True, "head": body[:RESULT_CHARS]}
            part = {"functionResponse": {"name": event.get("tool"), "response": result}}
            if contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][0]:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
    final = str(t.final.get("response") or "").strip()
    if final:
        contents.append({"role": "model", "parts": [{"text": final}]})
    return {"systemInstruction": {"role": "system", "parts": [{"text": system}]}, "contents": contents}


def build(trajectories: Path, suites: Path, out: Path, *, holdout=DEFAULT_HOLDOUT,
          validation_share: float = 0.2, system: str = "") -> dict:
    tasks = load_tasks(suites)
    trajs = load_trajectories(trajectories)
    out.mkdir(parents=True, exist_ok=True)
    system = system or ("You are Aria, an AI agent for coding, financial analysis and logistics "
                        "operations. Read the workspace first, compute every number with code from "
                        "named data, keep each client's data apart, and check your work before you finish.")
    split_files = {s: (out / f"{s}.jsonl").open("w", encoding="utf-8") for s in ("train", "validation")}
    excluded: Counter = Counter()
    exposure: dict[str, Counter] = defaultdict(Counter)
    seen_tasks: dict[str, set[str]] = defaultdict(set)
    fingerprints: set[str] = set()
    try:
        for t in trajs:
            info = tasks.get(t.task_id)
            reason = why_excluded(t, info, tuple(holdout))
            if reason:
                excluded[reason] += 1
                continue
            example = to_example(t, system)
            fp = hashlib.sha256(json.dumps(example["contents"], sort_keys=True).encode()).hexdigest()
            if fp in fingerprints:
                excluded["duplicate"] += 1
                continue
            fingerprints.add(fp)
            split = split_of(t.task_id, validation_share)
            seen_tasks[split].add(t.task_id)
            exposure[split][domain_of(info.tags)] += 1
            split_files[split].write(json.dumps(example, ensure_ascii=False) + "\n")
    finally:
        for fh in split_files.values():
            fh.close()

    overlap = seen_tasks["train"] & seen_tasks["validation"]
    assert not overlap, f"task in two splits: {sorted(overlap)}"
    holdout_tasks = sorted(tid for tid, info in tasks.items() if info.suite in holdout)
    manifest = {
        "rules": {"holdout_suites": list(holdout), "split": "sha256(task_id)", "validation_share": validation_share,
                  "eligible": "grader PASS and acceptance not failed; no grader file touched"},
        "inputs": {str(t.path): hashlib.sha256(t.path.read_bytes()).hexdigest() for t in trajs},
        "models": sorted({t.model for t in trajs}),
        "examples": {s: sum(c.values()) for s, c in exposure.items()},
        "tasks": {s: sorted(v) for s, v in seen_tasks.items()},
        "exposure_by_domain": {s: dict(c) for s, c in exposure.items()},
        "excluded": dict(excluded),
        "holdout_tasks": holdout_tasks,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build a Vertex Gemini SFT set from eval trajectories.")
    ap.add_argument("trajectories", type=Path)
    ap.add_argument("--suites", type=Path, default=Path("evals/suites"))
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--holdout", nargs="*", default=list(DEFAULT_HOLDOUT))
    ap.add_argument("--validation-share", type=float, default=0.2)
    args = ap.parse_args(argv)
    m = build(args.trajectories, args.suites, args.out, holdout=tuple(args.holdout),
              validation_share=args.validation_share)
    print(json.dumps({k: m[k] for k in ("examples", "exposure_by_domain", "excluded")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
