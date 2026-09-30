# Architecture

Aria Code follows a product architecture similar to modern coding agents:
a small launcher, terminal UI adapters, a reusable runtime, typed tools,
service packages, plugin boundaries, and explicit safety controls.

## Repository Layers

```text
apps/
  cli/          terminal adapter, command parsing, direct command routing
  daemon/       background/server entrypoints
  channels/     chat or webhook adapters

runtime/        agent loop, tool execution, approvals, traces, events
packages/
  aria_sdk/     public SDK surface
  aria_core/    architecture manifest and contracts
  aria_services/data, provider health, usage, registry
  aria_mcp/     MCP bridge and tool manifests
  quant_engine/ quantitative engines

ui/             terminal rendering, input, banner, image/glyph rendering
plugins/        shareable workflow bundles
docs/           architecture, operations, and release guidance
```

## CLI Rule

`aria_cli.py` remains the legacy compatibility adapter while the migration is in
progress. New reusable behavior should move to:

- `apps/cli/*` for CLI parsing and adapters;
- `runtime/*` for agent/tool/approval/streaming behavior;
- `packages/aria_services/*` for business services;
- `packages/aria_sdk/*` for public programmable APIs;
- `ui/*` for terminal rendering only.

## Runtime Rule

Tool execution, permissions, retries, result events, streaming callbacks, and
approval decisions should flow through runtime events. Terminal code consumes
events; it should not own core execution semantics.

## Plugin Rule

Product workflows that are not core platform behavior should be packaged under
`plugins/` first. If a plugin needs a reusable primitive, promote that primitive
into `runtime/` or `packages/` with tests.

## Open-Core Rule

The repository is Apache 2.0 (see `LICENSE` and `NOTICE`). That license is a
commitment about *this* layer, not about everything Arthera builds, and the
boundary between the two is an architectural constraint rather than a licensing
footnote.

```text
Open, Apache 2.0 — this repository
  apps/cli, apps/daemon, apps/channels    entrypoints and adapters
  runtime/                                agent loop, tool execution, approvals
  packages/aria_sdk                       public SDK surface
  packages/aria_core                      architecture manifest and contracts
  packages/aria_services                  provider health, settings, registry
  packages/aria_mcp                       MCP bridge and tool manifests
  ui/, plugins/, packs/                   rendering, workflows, domain packs
  evals/, tests/                           verifiable evals, acceptance gates
  domain interfaces                       the abstract shape of a domain pack

Closed — separate, private, not in this repository
  the quantitative engine                 pricing, calibration, factor models
  proprietary datasets and connectors
  institutional trading infrastructure
```

Two rules keep that boundary real:

1. **The open side must never hard-import the closed side.** Every call site
   goes through `packages/quant_engine/is_available()` and degrades when the
   engine is absent. A plain `import` would make the free shell unusable
   without a component that is not in the repository, which is the failure mode
   this boundary exists to prevent.

2. **Interfaces are open, implementations may be closed.** A domain pack's
   contract — what a pack is, how it registers tools, what a tool returns —
   belongs on the open side, so that someone can write a pack without access to
   ours. What a *particular* pack computes can be proprietary.

`packages/quant_engine` is currently still in this tree, so this version
publishes it under Apache 2.0 too. `CLOSING_SOURCE.md` has the plan for moving
it out; until that lands, rule 1 is the only thing separating the two sides, and
rule 2 is aspirational for the finance pack specifically.
