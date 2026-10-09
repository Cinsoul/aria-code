# Aria Code Execution Protocol

Aria Code competes on the control layer of software engineering, not on
writing code faster: every code change should be **bounded, verified,
explained, approved by risk and reversible**.

```text
Understand before editing.   Plan before executing.
Approve by risk, not by command.   Change atomically.
Verify every change.   Review independently.   Make everything reversible.
```

The runtime state machine this aims for:

```text
INSPECT → PLAN → (approval if needed) → EXECUTE → VERIFY → REVIEW → DELIVER
                                           ↑                    │
                                           └──── REPAIR ◄───────┘
```

## What exists today

| Piece | Where | Status |
|---|---|---|
| Durable runs and event log | `runtime/run_state.py`, `runtime/run_store.py` | shipped |
| Acceptance gate — "done" requires green checks | `runtime/acceptance.py` | shipped |
| File checkpoints, `/rewind code <run>` | `runtime/checkpoints.py` | shipped |
| Worktree isolation for background agents | `runtime/worktrees.py` | shipped |
| Symbol-ranked repo map | `runtime/repo_map.py` | shipped |
| **Risk assessment** (L0–L4, capabilities, blast radius) | `safety/risk.py` | **phase 1** |
| **Change contract**, enforced per tool call | `runtime/contract.py` | **phase 1** |
| **Delivery report** from evidence | `runtime/delivery.py` | **phase 1** |

## Risk levels

`assess_command()` / `assess_tool()` describe what an action touches.

| Level | Meaning | Examples |
|---|---|---|
| L0 | read, inspect, verify | `ls`, `rg`, `git diff`, `pytest`, `tsc --noEmit` |
| L1 | change inside the workspace | edit a file, `git add`, `sed -i` |
| L2 | change the environment | `npm install`, `pip install`, `curl` |
| L3 | act outside the local repo | `git commit`, `git push`, `gh pr create`, HTTP POST |
| L4 | destructive or production | `rm`, force push, `reset --hard`, migrations, deploy, secrets, `sudo` |

Each assessment also names its **capabilities** — `filesystem.write`,
`network.read`, `package.install`, `git.push`, `github.pr`, `database.write`,
`secret.read`, `cloud.deploy`, `system.admin`, … — whether it is
**reversible**, and its **blast radius**: hosts (`registry.npmjs.org`), files
(`package.json`, `package-lock.json`) and systems (`Database schema`).

It is descriptive: the existing command policy still decides what runs, and an
assessment never reports a command milder than that policy does.

## Change contracts

A project bounds what a coding task may change in `.aria/policy.yaml`:

```yaml
contract:
  allow: [src/auth/**, tests/**]      # paths the task may change (default: whole workspace)
  restrict: [src/auth/secrets.py]     # never, even inside allow
  forbid: [git.push, cloud.deploy, database.write]   # capabilities it may not use
  max_level: 3                        # highest risk level an action may have
  success:
    - existing tests pass
    - expired sessions refresh
```

Each request becomes the contract's goal. The model sees the contract before
the first round; the runtime checks every tool call against it before anything
runs and refuses the ones that break it — the call does not execute, and the
model receives the reason as the tool's result. Reading is never restricted.

A `policy.yaml` that cannot be read (bad YAML, an unknown capability, a
`max_level` outside 0–4) gives a **fail-closed** contract: reads and checks
only, with the error shown to the model so it can report it. It never silently
becomes "no contract".

## Delivery report

When a turn changed files, ran checks or had calls refused, the runtime ends
it with a report built from what happened, not from the model's summary:

```text
DONE

Changed
  M src/session.py  +2 -1
  A src/refresh.py  +3
  2 files · +5 / -1

Verified
  ✓ pytest -q

Review
  Not reviewed

Risk
  L2 medium · Install dependency

Checkpoint
  2 checkpoints · /rewind code a1b2c3d4

Next
  Ready to commit
```

`INCOMPLETE` whenever the turn stopped early or a check is red, however the
model's last message reads. `delivery_report: false` in the config hides it in
the REPL; headless (`-p`) results always carry it, and the contract, as data.

## Roadmap

**Phase 2 — risk-aware approval and independent review**

- Approval card driven by the assessment: action, scope (hosts, files),
  risk `L2 · 43/100`, reversible, reason; options *allow once / for this
  project / always for this command prefix / deny*.
- Auto-approve by level: L0–L1 run, L2 asks with context, L3 asks
  explicitly, L4 always asks and shows the blast radius.
- Reviewer sub-agent with a fresh context: sees the goal, the contract, the
  diff and the check results — not the builder's reasoning — and fills the
  report's *Review* section; blocking findings send the turn back to REPAIR.

**Phase 3 — semantic diff and the action layer**

- Semantic diff: behaviour before / after / why / impact / tested-by, with the
  code diff one level down.
- Actions over tool calls in the terminal: "Inspecting the auth flow" instead
  of `read_file`, three levels of detail (summary, files and commands, raw
  events).
- Symbol-level patches (`replace_symbol`, `insert_after`, …) instead of
  whole-file writes.

**Phase 4 — transactions and project knowledge**

- Worktree per task by default, merged on approval.
- Transaction checkpoints that also restore task graph, approvals, test
  baseline and conversation, not only files.
- Persistent project graph (files, symbols, tests, services and their edges)
  for impact analysis before editing.
- `.aria/workflows/*.yaml` for user-defined pipelines (`/release` → test →
  build → security review → changelog → PR).
