# Rust/Go runtime and business migration

The requirement is to retain every existing business capability, including
finance, backtesting and model training, and remove old Python implementations
only after functional replacement is proven. The entire product migration is
not complete. The current installed release remains on its existing worker;
the new Go service is explicitly selectable with `ARIA_RUNTIME` for native
`chat`, `exec` and `tool` verification. Production services and release packages are not switched
by this branch.

## Current implementation

| Area | Native replacement | Evidence and remaining boundary |
| --- | --- | --- |
| Terminal | `rust/cli/src/chat/` | Persistent editing, Markdown, chronological operations, Chinese/English display, reviews and cancelled-turn state. A rounded multiline composer and a hand-tuned compact cream robot with four feet, aligned eyes and a thin orange stripe. |
| Application protocol | `go/runtime/server.go` | Actual executable barrier, approvals, multi-turn persistence, resume, idle cancellation and broken-output shutdown. Commands/events beyond the implemented catalog remain to port. |
| Headless and file bridge | `go/runtime/stream.go`, `bridge.go` | Existing single-turn events, actual Rust/Go process tests, bounded JSON-RPC, literal arguments, per-call write grants and refusal. Full legacy command catalog and change-store routes remain. |
| Google model/auth | `go/runtime/provider_*.go`, `google_auth.go` | SDK and Vertex-compatible streams; signed calls; existing login; independent native OAuth refresh; macOS manual proxy support. Other provider families and automatic proxy discovery remain. |
| Files | `go/runtime/files.go`, `search.go` | Actual edits/read-back, ordered atomic multi-edit, CRLF/mode preservation, root isolation and preimage conflict checks. Python-specific regex extensions, semantic patches, staged-change/undo UX and diagnostics remain. |
| Shell | `go/runtime/command_*.go` | Actual command output/exit, refusal, exact session grants, bounded capture and cancellation. Native OS sandbox/background-service parity remains; unsupported modes reject execution. |
| Sessions | `go/runtime/history.go`, `state.go` | Old JSON formats, unknown fields, supported images and tool history. Additional attachment formats and public import/export routes remain. |
| Portfolio backtest core | `go/runtime/quant/` | 48 complete oracle results plus actual executable comparisons, including gaps, ordering, fees, realized PnL and benchmarks. Market feeds, live broker risk/execution, optimizer/report routes remain. |
| Training evaluation | `go/runtime/training/compare.go` | Paired reports, fixed bootstrap sampling, confidence intervals, costs and error exclusion compared with Python. |
| SFT dataset preparation | `go/runtime/training/dataset.go` | Holdout isolation, task splits, eligibility, deduplication, provenance and Unicode trimming compared with Python; malformed inputs preserve existing files. Cloud tuning/job lifecycle and broader ML implementations remain. |
| Risk assessment and change contracts | `go/runtime/risk.go`, `contract.go` | L0–L4 levels, capabilities, blast radius and score for commands and tools; `.aria/policy.yaml` contracts with allow/restrict/forbid/max_level, fail-closed loading, and a check on every native tool call before approval. Compared field by field with `safety/risk.py` and `runtime/contract.py` through `aria-runtime risk` and `aria-runtime contract`. Go's ASCII `\b` can only rate a keyword flush against a non-ASCII letter higher, never lower. Risk-mode auto-approval, the delivery report and the review gate remain. |
| Relay | `go/relay/` | Existing separately validated Go candidate and storage contracts. Production switch/old-entrypoint deletion are still separate deployment work. |

All source families are in scope. In particular, agents/packs, financial data
and broker adapters, document/notebook/browser tools, API/daemon services,
MCP/LSP/hooks, client isolation, task worktrees/acceptance checks and packaging
are not covered merely by the rows above. Their Python implementations remain
available and must not be removed to make a language count appear complete.

## Local evidence

On 2026-10-12 the Rust/Go path completed a real configured Google greeting
without file tools, read an unpredictable marker from a temporary project,
then approved, edited and read back its file. The latest single samples took
6.10, 6.05 and 10.79 seconds respectively. A separate native OAuth refresh bypassed the CLI
access-token cache and passed without modifying its credentials database.
These observations validate those flows, not every provider/model or an
overall performance comparison with other coding agents.

The later headless/file-bridge increment passed 126 Go test cases (including
subtests; one opt-in live auth test skipped), 63 Rust tests and 111 targeted
Python-driven native/domain/legacy-stream tests on macOS. Linux amd64 and
Windows amd64 Go binaries cross-compiled without CGO. Their runtime behavior
still requires the configured CI matrix. The native model fixture verifies
SDK requests, actual disk effects and the Rust process boundary without live
cloud credentials.

A real pseudo-terminal check rendered the compact cream robot, exercised
Chinese multiline paste, long-input scrolling, resize and clearing, and restored
terminal settings after exit. Earlier source-build startup samples reached the
ready screen in 0.047 and 0.129 seconds; model latency is separate from this
first-screen measurement.

The retained Python domain code serves as the independent oracle in
`tests/test_native_runtime_domain.py`, `test_native_training_compare.py` and
`test_native_training_dataset.py`, `test_native_go_risk.py` and
`test_native_go_contract.py`. The new `.github/workflows/go-runtime.yml`
builds the executable before running those comparisons. Live model/auth
verification is opt-in and is not part of normal CI.

## Required before deleting a module

1. Its behavior and callers have an identified native replacement, including
   public CLI/API paths and saved-state compatibility.
2. Functional tests cover its real effects and outputs, refusal/cancellation
   and relevant edge cases. Imports or placeholder adapters are insufficient.
3. Packaging, installers, service entrypoints and release checks use that
   replacement and preserve the existing deployment contract.
4. Source references and obsolete tests/metadata are updated together, with
   recoverable Git history. The integrated product checks must pass before
   pushing, merging or publishing the full migration.

The existing UI PR remains a draft while the expanded migration is in progress.
New runtime/domain work is a local checkpoint and does not constitute a
completed product release.
