# Fawn Zig Module

Purpose:
- produce specialization outputs from validated quirk sets
- provide standalone or embedded/adjacent integration paths

Decision rubric (when to use Zig):
1. Use Zig for hot-path runtime logic that executes per command/dispatch/frame.
2. Use Zig for compile-time specialization from static quirk/profile data.
3. Use Zig when allocator control or bounded-memory behavior is part of the requirement.
4. Keep logic out of Zig when it is policy-only, proof-only, or infrequent orchestration.
5. Move logic into Zig only after benchmark traces show it is in the latency-critical path.
6. For incumbent-replacement/runtime paths, implement in Zig first, then remove branches only when Lean proofs let us hoist them out safely.

Interop note:
- initial integration target is Fawn's standalone runtime path
- adapter/ABI paths are used only for side-by-side incumbent comparisons

Style guide:
- follow `STYLE.md` for all Zig implementations in this module.

## Source modules (runtime + backend lanes)

Core:
- `src/model.zig` (433) — typed contract for API, scope, safety, proof mode, match spec, actions, command kinds, device profile.
- `src/runtime.zig` (402) — deterministic matcher, selector, and action application with profile-indexed command buckets.
- `src/main.zig` (493) — CLI, arg parsing, dispatch loop, `--trace`/`--replay`/`--trace-meta` orchestration.
- `src/execution.zig` (157) — execution mode switching (`trace` and `native`) and run result envelope.

Parsing:
- `src/command_json.zig` (595) — JSON command stream parser for replay-style inputs.
- `src/quirk_json.zig` (194) — deterministic JSON parser for quirk records with strict schema checks.

Trace and replay:
- `src/trace.zig` (280) — TraceState, hash functions, name helpers, trace row and meta output.
- `src/replay.zig` (107) — replay expectation parsing and hash-chain validation.

WebGPU backend:
- `src/webgpu_ffi.zig` (311) — WebGPUBackend struct, lifecycle (init/deinit), adapter/device request, queue sync, timestamp readback.
- `src/wgpu_types.zig` (707) — all WebGPU C API types, constants, function pointer types, Procs table, record types.
- `src/wgpu_loader.zig` (212) — dynamic library loading, C callbacks, helper functions.
- `src/wgpu_commands.zig` — command execution orchestration for upload/copy/barrier/dispatch/kernel dispatch plus render command delegation.
- `src/wgpu_render_commands.zig` — native `render_draw` lowering via render pass, per-format pipeline caching, and draw-call submission loop.
- `src/wgpu_resources.zig` (573) — buffer/texture management, bind group building, shader module and pipeline creation.

Build:
- `build.zig` — compile and run hooks, links libC and libdl.

## How to run (toolchain must be available)

```bash
cd fawn/zig
zig build run -- --vendor intel --api vulkan --family gen12 --driver 31.0.101
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --trace
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --replay path/to/trace.jsonl
zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute --trace --trace-jsonl run.jsonl --trace-meta run.meta.json
zig build run -- --commands fawn/examples/kernel_dispatch_commands.json --backend native --execute --kernel-root fawn/bench/kernels
zig build run -- --commands fawn/examples/draw_call_proxy_commands.json --backend native --execute --trace --trace-meta run.meta.json
zig build run -- --commands fawn/examples/draw_call_proxy_commands.json --backend native --execute --trace --queue-sync-mode deferred --trace-meta run.deferred.meta.json
zig build run -- --commands ../../examples/kernel_dispatch_commands.json --trace
zig build run -- --commands ../../examples/kernel_dispatch_commands.json --emit-normalized
zig build test
```

When `--quirks` is provided, JSON file values are loaded directly and validated before transform.

Timestamp debug mode (for zero/empty GPU timestamp investigation):

```bash
FAWN_WGPU_TIMESTAMP_DEBUG=1 zig build run -- --commands path/to/commands.json --backend native --execute --trace --trace-meta run.meta.json
```

This emits timestamp-path diagnostics to stderr, including adapter/device feature state, query artifact creation, write mode, map status, and begin/end readback values.

- `--trace` now emits trace rows conforming to `fawn/config/trace.schema.json`.
- trace rows include `traceVersion`, `module`, `opCode`, deterministic `hash` and `previousHash`,
  and the full decision envelope used by Lean parity checks.
- `--trace-meta` execution timing now includes split fields:
  `executionSetupTotalNs`, `executionEncodeTotalNs`, `executionSubmitWaitTotalNs`, `executionDispatchCount`.
  Native execution metadata also records `queueSyncMode` when `--execute` is enabled.
- `--replay` mode validates per-row `seq`, `command`, optional `kernel`, `module`, `opCode`, and hash-chain fields.

## Runtime behavior contract (minimal clone slice)

- fixed precedence rules in `runtime.zig`
- runtime dispatch now pre-filters quirks once per process profile and buckets by command kind before tracing starts.
- profile matching:
  - vendor + api hard match
  - optional device family match
  - optional driver range match (`>=`, `>`, `<=`, `<`)
- deterministic action selection by score
- action application returns a transformed command, never silent fallthrough.
- lean obligation fields in dispatch decisions:
  - `requiresLean` (derived from `verificationMode`)
  - `blocking` (required proof not met)
  - `verificationMode` and `proofLevel` of selected quirk
- `--trace` emits JSON rows including the Lean gate fields for replay and gate auditing.
- trace rows now also include:
- `scope`
- `safetyClass`
- `toggle` (toggle action payload when present)
- command parsing accepts `command`, `kind`, or `command_kind` with extra kernel alias (`kernel_name`).

## Lean-out workflow for Zig runtime

1. Implement runtime behavior deterministically in Zig (no placeholder execution branches).
2. Capture benchmark + trace evidence for the current path.
3. Prove removable conditions in Lean and emit bind/build artifacts that encode the decision.
4. Delete the corresponding Zig runtime branch once proof+artifact path is in place.
5. If proof is not available, keep the explicit Zig path and continue measuring.

## Native execution status

Native Zig+WebGPU/FFI execution is implemented across 5 backend modules (~2,364 LOC):
- `webgpu_ffi.zig` — backend struct, adapter/device/queue lifecycle, timestamp readback.
- `wgpu_types.zig` — C API type definitions and function pointer table.
- `wgpu_loader.zig` — dynamic library loading, C callbacks, helpers.
- `wgpu_commands.zig` — command execution with compute pipeline lowering and GPU timestamp queries.
- `wgpu_resources.zig` — buffer/texture/bind-group/pipeline resource management.

Execution capabilities:
- `--backend native --execute` emits `executionBackend` fields in trace rows.
- `upload`, `copy`, `barrier`, `dispatch`, `kernel_dispatch`, and `render_draw` all submit through real command buffers.
- native queue waiting is configurable via `--queue-wait-mode process-events|wait-any` (default: `process-events`; `wait-any` auto-falls back when unsupported).
- queue synchronization timing is configurable via `--queue-sync-mode per-command|deferred` (default: `per-command`);
  deferred mode skips per-submit waits and performs one final queue flush after the command loop.
- `kernel_dispatch` runs through full compute pipeline lowering with bind groups and optional GPU timestamp queries.
- `render_draw` runs through a native render-pass path with a Dawn-aligned centered-triangle vertex-buffer pipeline, static fragment uniform bind-group parity, depth24plus-stencil8 attachment, per-format pipeline caching, cached render/depth texture views, and repeated draw calls.
- kernel lookup supports `--kernel-root` and built-in marker fallback kernels.
- wall-time, setup, encode, and submit-wait timing split into trace rows and `--trace-meta`.

Known gaps:
- GPU timestamp readback returns zero on some adapter/driver combinations (investigation open).
- render path is currently minimal (`render_draw`) and does not yet model full render-pass state space.

Reference commands:
- `zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute`
- `zig build run -- --quirks path/to/quirks.json --commands path/to/commands.json --backend native --execute --trace --trace-jsonl run.jsonl --trace-meta run.meta.json`
- `zig build run -- --commands path/to/commands.json --replay path/to/run.jsonl --backend native`

### Parser behavior guarantees

- API, vendor, and command names are matched case-insensitively where practical.
- malformed payload fields fail fast rather than injecting placeholder strings.

### Command replay examples for Doppler-style command derivatives

- `kernel_dispatch` with `kernel` label and dispatch dimensions: `fawn/examples/kernel_dispatch_commands.json`
- `kernel_dispatch` accepts optional `repeat` (aliases: `dispatch_count`, `dispatchCount`), default `1`.
- `render_draw` supports repeated draw-call submission via `draw_count`/`drawCount`,
  optional `first_vertex`/`firstVertex` and `first_instance`/`firstInstance`,
  indexed mode via `draw_indexed` with required `index_data`/`indexData`/`indices`,
  optional `index_format`/`indexFormat` (`uint16`|`uint32`), and optional indexed-draw fields
  `index_count`/`indexCount`, `first_index`/`firstIndex`, and `base_vertex`/`baseVertex`,
  optional target size/format overrides, and explicit state-set variants:
  `pipelineMode` (`static` | `redundant`) and `bindGroupMode` (`no-change` | `redundant`).
- alias names accepted in command inputs:
  - `upload` | `buffer_upload`
  - `copy_buffer_to_texture` | `texture_copy` | `copy_texture` | `copy_buffer_to_buffer` | `copy_texture_to_buffer`
  - `dispatch` | `dispatch_workgroups` | `dispatch_invocations`
  - `kernel_dispatch`
  - `render_draw` | `draw` | `draw_call` | `draw_indexed`
- either `kind` or `command` may carry the command name in command JSON.
