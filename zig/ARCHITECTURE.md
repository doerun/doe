# Doe Zig Architecture

This document tracks the current Zig runtime topology in `fawn/zig/src`.
It replaces the old `parser/dispatch/executor` module naming model.

## Runtime goals

- deterministic command selection and execution
- explicit unsupported taxonomy (no silent fallback)
- trace/replay parity for audit and debugging
- config-driven behavior for benchmark and gate contracts

## Current module topology

Core decision/runtime lane:

- `fawn/zig/src/model.zig`
  - typed contract enums/structs for quirks, commands, and runtime status
- `fawn/zig/src/quirk_json.zig`
  - strict quirk JSON ingestion
- `fawn/zig/src/command_json.zig`
  - strict command JSON ingestion
- `fawn/zig/src/runtime.zig`
  - deterministic quirk matching + precedence selection
- `fawn/zig/src/execution.zig`
  - execution mode orchestration (`trace` vs `native`)
- `fawn/zig/src/main.zig`
  - CLI boundary and artifact wiring

Trace/replay lane:

- `fawn/zig/src/trace.zig`
  - trace row + trace-meta emission and hash-chain generation
- `fawn/zig/src/replay.zig`
  - replay validation against row/meta contract invariants

WebGPU native execution lane:

- `fawn/zig/src/webgpu_ffi.zig`
  - backend lifecycle (instance/adapter/device/queue), capability probing, queue wait/sync behavior
- `fawn/zig/src/core/abi/wgpu_types.zig`
  - C API type/function/proc-table contracts
- `fawn/zig/src/core/abi/wgpu_loader.zig`
  - dynamic proc loading and callback helpers
- `fawn/zig/src/wgpu_resources.zig`
  - buffer/texture/shader/pipeline resource management
- `fawn/zig/src/wgpu_commands.zig`
  - upload/copy/barrier/dispatch and command execution glue
- `fawn/zig/src/wgpu_render_*`
  - render pass/bundle/resource/type-specific surfaces
- `fawn/zig/src/wgpu_*_procs.zig`
  - domain-specific proc tables (P0/P1/P2 surfaces, texture/surface/async/capability APIs)

## Data flow

1. Input load
- CLI arguments resolve quirk + command artifacts.
- JSON ingestion modules parse into typed model contracts.

2. Deterministic selection
- `runtime.zig` filters candidate quirks by profile.
- per-command matching chooses one action with deterministic precedence.

3. Execution
- `execution.zig` routes command handling.
- trace mode emits deterministic decision artifacts only.
- native mode executes through WebGPU proc surfaces with explicit status mapping.

4. Observability
- trace rows carry command/op metadata and hash-chain links.
- trace-meta carries run-level timing, status counts, and terminal hash.
- replay validates deterministic continuity.

## Lean boundary

- Lean remains a verification producer and does not execute hot path logic at runtime.
- Zig consumes verification-relevant fields (`verificationMode`, `proofLevel`) and emits obligations in trace artifacts.
- Proof-driven elimination is implemented by deleting proven runtime branches and hoisting conditions into artifacts/config.

## Extension discipline

- Add new WebGPU API surfaces as dedicated `wgpu_*_procs.zig` or feature-scoped modules.
- Keep capability probing and unsupported taxonomy explicit.
- Route all runtime-visible behavior changes through config + docs + status updates in the same change.

## Gate expectations

- `zig fmt` on changed Zig files
- `zig build test` for affected modules
- schema/correctness/trace gates must remain green for release paths
