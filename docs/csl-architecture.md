# Doe CSL architecture

## What this path is

Doe's Cerebras CSL path is not a standard WebGPU backend.

Metal, Vulkan, and D3D12 keep the ordinary GPU execution model: WGSL lowers to
backend shader/codegen targets that still preserve SIMT-style concepts such as
workgroups, barriers, and subgroup operations.

The CSL path uses a different boundary. It recognizes supported computation
patterns, lowers them into an explicit host-side execution contract, and then
emits Cerebras-specific artifacts for PE-grid and fabric execution.

This is a retargeting path, not a claim that Cerebras is implementing the
WebGPU runtime contract directly.

## The abstraction stack

The current CSL lowering stack is:

1. WGSL enters the normal Doe compiler pipeline and becomes Doe IR.
2. The CSL classifier inspects that IR and chooses a supported kernel pattern.
3. Doppler `execution-v1` steps are lowered into an explicit `HostPlan`.
4. CSL emitters render `layout.csl`, `pe_program.csl`, compile/runtime config,
   and simulator-plan artifacts from that `HostPlan`.
5. External Cerebras tools or the simulator runner consume those artifacts.

The most important design rule is that the explicit `HostPlan` is the contract
boundary between higher-level execution intent and Cerebras-specific emission.

## SDK complete-program implication

CSL evidence is a complete-program contract, not a single-kernel contract.
The SDK execution shape couples layout code, one or more PE programs, compiler
parameters, exported symbols, RPC entrypoints, memcpy channels, and host-side
runtime calls.

That has direct consequences for Doe receipts:

- A CSL compile artifact should bind the emitted `layout.csl`, each
  `pe_program.csl`, the `cslc` command shape, compile-time parameters, output
  directory, and compiler metadata such as `out.json` when present.
- A runtime or simulator trace should bind exported mutable/readonly symbols,
  host-to-device and device-to-host copy rectangles, element counts, data
  type/order/streaming mode, RPC launch names, and command-stream completion
  requirements such as `unblock_cmd_stream`.
- Multi-PE smoke should graduate before inter-PE communication: replicated
  work over a `width x 1` rectangle exercises PE-grid parameterization,
  per-PE copies, and result gathering without adding fabric routing as a
  confounder.
- Inter-PE or time-marching programs add a routing-resource contract: colors,
  task IDs, entrypoints, memcpy-reserved resources, per-direction routes,
  chunking, and completion callbacks must be explicit receipt fields so a
  compile/run cannot silently collide with the SDK runtime's reserved colors.
- Multi-stage host flows should be represented as an ordered operation graph,
  not as a single run flag. For example: H2D input copies, RPC launch with
  scalar arguments, D2H reduction/timestamp copy after checkpoint unblock,
  RPC output-preparation launch, then D2H tensor copy.
- Streaming-mode memcpy ordering is part of the contract. The SDK GEMV
  streaming example starts computation from wavelet-triggered receive tasks
  instead of an explicit kernel launch, and warns that swapping the stream
  order can hang the program. Doe receipts therefore need to preserve
  stream order and nonblocking/blocking mode per H2D/D2H operation.

## CSL operation graph contract

`config/csl-operation-graph.schema.json` is the shared receipt shape for the
host/device operation sequence that surrounds emitted CSL code. It is
deliberately separate from the current simulator-plan schema so it can be
validated and adopted incrementally by the SDK driver, simulator result, and
governed-lane report.

The top-level discriminator is `orchestrationMode`:

- `memcpy`: direct `cslc` compile plus `SdkRuntime` `memcpy_h2d`,
  `memcpy_d2h`, and `launch` operations. This covers the Gemma 4 E2B ladder
  and SDK patterns such as single-PE GEMV, replicated multi-PE GEMV, streaming
  memcpy, and checkerboard GEMV. Streaming H2D/D2H is still `memcpy` mode when
  the host operation is `SdkRuntime.memcpy_*` with `streaming=true`.
- `sdklayout`: Python `SdkLayout` code regions, ports, connections, streams,
  and async `SdkRuntime.send` / `receive` operations. This is the expected
  31B weight-streaming path once the resident E2B path has compile and trace
  receipts.

The schema carries typed CSL compile params, the `cslc` fabric/arch/memcpy
command shape, exported device symbols, and an ordered operation list. The
operation graph is intentionally explicit about ROI rectangles, elements per
PE, data type, row/column order, streaming mode, blocking mode, RPC function
names, and `unblock_cmd_stream` completion requirements.

Within `orchestrationMode="memcpy"`, `executionPattern` is the second
discriminator:

- `rpc_launch`: copy data through exported device symbols, launch an exported
  device function through the memcpy RPC mechanism, then copy results back.
  Launch ops carry `unblockCheckpointRequired` because the host command stream
  cannot safely proceed to the following copy unless the device function
  releases it.
- `streaming_memcpy_driven`: use `memcpy_h2d` / `memcpy_d2h` with
  `targetKind="memcpy_color"` and `streaming=true` so wavelet-triggered device
  tasks drive computation. This is the production-shaped E2B matvec/attention
  lane because checkerboard-style GEMV streams `x`, `b`, and `y` over memcpy
  colors instead of launching a separate RPC compute entrypoint.

`reservedResources` is optional on day one. It records color, queue, task-ID,
and memcpy-channel reservations so future gates can detect collisions between
multiple emitted kernels. The current gate validates graph references and
source-level unblock obligations, but deliberately does not run the
cross-kernel resource-collision check until the E2B path exercises concurrent
kernel composition.

`bench/gates/csl_operation_graph_gate.py` validates the first enforceable
invariants:

- every memcpy op references an exported `device_variable`
- every launch op references an exported `device_function`
- every memcpy ROI fits the declared PE grid
- every `memcpy` launch marked `unblockCheckpointRequired` ends the referenced
  CSL function with `sys_mod.unblock_cmd_stream()`
- every `sdklayout` send/receive references a declared stream, every stream
  references a declared port, every port references a declared code region,
  and every connection references declared ports

SDK library-backed domains are a separate pattern family. The SDK 3D FFT
example imports `<kernels/fft/fft3d_layout>` and binds a pencil-decomposition
data reshuffle contract around a library layout helper. Doe should represent
that as a declared library-backed CSL pattern and operation graph, not by
silently synthesizing arbitrary PE routing from generic WGSL.

Reference SDK patterns for this contract:

- GEMV 1 complete program: canonical memcpy RPC launch and
  `sys_mod.unblock_cmd_stream()` completion shape.
- GEMV 5 multiple PEs: canonical multi-PE ROI and row-major distribution shape.
- GEMV 9 memcpy streaming and GEMV checkerboard: canonical
  streaming-memcpy-driven shape with memcpy colors and fabric/buffer flags.
- SDK 1.4 release notes: `SdkLayout` beta and direct-link `send` / `receive`
  API boundary.
- SdkLayout 5 GEMV: code regions, ports, connections, streams, and async
  `send` / `receive` ordering.
- Host Runtime and Tensor Streaming: `SdkRuntime` lifecycle, copy mode,
  streaming mode, ROI semantics, and `load` / `run` / `stop`.

## Why CSL is different

Doe's CSL backend does not assume that GPU-style execution primitives carry
over unchanged.

The classifier is explicit about this:

- GPU backends can translate IR mechanically because they share a SIMT model.
- CSL cannot rely on that model because WSE execution is expressed in terms of
  PE-local memory, fabric routing, and pattern-specific templates.

That is why the CSL path classifies first and emits second.

## What survives the lowering

Some information remains explicit across the WGSL -> CSL boundary:

- model dimensions and execution phases
- quantization and storage formats such as `f16`, `q4k`, and `q8_0`
- KV-cache layout and decode metadata
- recognized operator families such as matmul, reduction, gather, dequant,
  attention, and sampling

These become explicit fields in the host/runtime artifacts rather than being
left implicit in shader-only code.

## What does not survive directly

WGSL subgroup semantics are not currently the direct abstraction boundary for
CSL.

Recognized kernels can still be retargeted to spatial Cerebras programs, but
that happens through pattern selection, not by treating subgroup operations as
portable primitives that map one-for-one onto CSL.

Current behavior is:

- pattern-specific kernels can be rewritten into Cerebras collectives or PE-grid
  programs
- generic WGSL subgroup builtins are treated as unsupported for CSL emission
- subgroup-tuned WGSL kernels may be recognized and remapped to a higher-level
  CSL kernel family instead of preserving subgroup operations literally

This means "subgroups map to Cerebras spatial computing" is only true at the
pattern/template level in the current implementation, not as a general builtin
lowering rule.

## Current scope

The current repo contains two related CSL surfaces:

1. A governed smoke/simulator path for checked artifacts and contract testing.
2. A broader host/runtime scaffolding path that models WSE-3 deployment inputs
   explicitly.

The smoke bundle path is documented as a governed preparation surface. It does
not claim full model-runtime execution on its own.

## SDK version compatibility

The CSL lane targets Cerebras SDK v1.4 as its compile/runtime floor. Two v1.4
breaking changes are relevant to emitted CSL code and already satisfied by the
emitters in-tree:

- *Tasks must be activated, not called.* All task invocations emitted by
  `runtime/zig/src/doe_wgsl/emit_csl_*.zig` use `@activate(task_id)` form.
- *Config-space pointer access is illegal; `@get_config` / `@set_config` are
  required.* The emitters do not construct pointers into config space.

WSE-1 is no longer supported by SDK v1.4. The HostPlan fabric/arch constraints
should not assume WSE-1 as a deployment target.

`cslc` in SDK v1.4 is shipped as a Singularity/Apptainer SIF runner, not a
static native binary. Host preflight for the CSL lane therefore has to verify
that `singularity` (or `apptainer`) is on `PATH` in addition to the usual
`DOE_CSLC_EXECUTABLE` resolution.

## Receipt discipline: three outcomes, no fourth path

Every Doppler/WGSL operator routed toward the CSL lane terminates in exactly
one of the outcomes declared for the `doe_csl` backend in
`config/shader-error-taxonomy.json` under `laneContracts.doe_csl`:

1. Supported CSL pattern with emitted HostPlan and CSL artifacts.
2. Explicit `csl_unsupported_*` receipt carrying a code from
   `laneContracts.doe_csl.unsupportedCodes` (currently
   `csl_unsupported_pattern`, `csl_unsupported_shader_stage`,
   `csl_unsupported_builtin`, `csl_unrecognized_compute_pattern`).
3. Hard compiler or runtime failure whose code matches one of the prefixes in
   `laneContracts.doe_csl.failureCodePatterns` (`csl_compile_*`,
   `csl_simulator_run_*` — populated after SDK diagnostics surface the
   concrete failure shapes).

No fourth path: no Cerebras-only fork of a Doppler operator, no silent
fallback onto a non-governed backend, and no directional promotion of a CSL
result that has not cleared the governed-lane gate.

## Scale-up direction: E2B first, 31B as streaming add-on

The near-term execution target is Gemma 4 E2B, whose host-plan / memory-plan /
runtime-config / simulator-plan fixtures already exist under
`examples/doe-wgsl-*.gemma-4-e2b-smoke.json`. Gemma 3 270M is the smaller
graduation target used to debug the SDK v1.4 driver seam before repointing the
governed lane at E2B fixtures.

Gemma 4 31B does not fit resident in WSE memory. The SDK v1.4 primitive that
maps cleanly to streamed weights is `SdkRuntime.send` / `receive` for program
input/output ports, introduced in v1.4 alongside memcpy-based data transfer.
The 31B memory-plan schema migration is therefore expected to add a
`csl_weight_streaming_policy` contract so receipts can distinguish resident
weights from streamed weights and bind port IDs / wavelet counts / chunks /
trace paths into the governed artifact.

`SdkLayout` (v1.4 beta: rectangular code regions, color routing, auto-routing
between regions) is the second-generation layout backend, not the first
integration seam. Its current beta restrictions — `memcpy` API not supported
for data transfers or remote launches, CSL libraries with internal color
routing not supported — conflict with Doe's existing memcpy-based driver. The
CSL emitters stay on the current HostPlan path until the governed lane has
working compile + trace receipts on E2B; `SdkLayout` adoption is a later
refactor gated on beta restrictions clearing or a parallel driver shape.

For 31B-style streaming, `SdkLayout` is still the likely long-term contract
shape. Multi-PE input/output streams imply fields that the current resident
memory-plan fixtures do not yet model:

- tensor sharding maps from logical dimensions to PE-grid width/height chunks
- code-region graph, placement, ports, stream IDs, and route colors
- demux/mux adaptor regions when host-visible streams enter or leave through
  fewer PEs than the compute region uses
- async `send` / `receive` ordering and dependency receipts
- control wavelets or sentinel entrypoints used to advance switches or release
  downstream computation

Those fields belong in a future streaming memory-plan / runtime-config schema
migration, not as hidden behavior in `csl_sdk_driver.py`.

## Source of truth

CSL-related sources of truth are layered by concern. Read the layer that
matches the question, not a nearby one:

| Concern | Source of truth | Notes |
| --- | --- | --- |
| Product/strategy boundaries (Doe vs Doppler vs Ouroboros) | `ouroboros/docs/` | Canonical: `ouroboros/docs/go-to-market/verified/doe-doppler-positioning.md` and `ouroboros/docs/strategy/doe-doppler-operator-diffing-implementation.md` ("Doppler owns meaning, Doe owns execution truth"). Runtime/API/operational docs deliberately live in project repos, not Ouroboros. |
| CSL abstraction and contract boundary | This file (`docs/csl-architecture.md`) | Architecture only; does not enumerate individual stages, pattern-family templates, or SDK flags. |
| Artifact contracts (host-plan, memory-plan, runtime-config, simulator-plan/result/trace, governed-lane report) | `config/*.schema.json` registered in `config/schema-targets.json` | Cross-validated by `python3 bench/gates/schema_gate.py`. Schema is authoritative even where prose disagrees. |
| CSL target constants, fabric limits, architecture enums | `runtime/zig/src/doe_wgsl/csl_spec.zig` | Self-declared single source of truth; `emit_csl_*.zig` must consume constants from here rather than redefining them. |
| Taxonomy: outcome codes + `laneContracts.doe_csl` | `config/shader-error-taxonomy.schema.json` and `config/shader-error-taxonomy.json` | Defines the three-outcomes contract below and the allow-list of failure-code prefixes. |
| CSL host operation graphs | `config/csl-operation-graph.schema.json` and `examples/csl-operation-graph.*.json` | Validated by `python3 bench/gates/csl_operation_graph_gate.py`; binds compile shape, exported symbols, ordered host operations, and SdkLayout references. |
| Classifier: which WGSL kernel patterns are recognized | `runtime/zig/src/doe_wgsl/emit_csl_classify.zig` | Pattern coverage changes here, not in prose. |
| Doppler `execution-v1` → CSL pattern mapping | `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` | |
| HostPlan emission | `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig` | Schema-backed; HostPlan is the contract boundary. |
| External SDK driver seam | `runtime/zig/tools/csl_sdk_driver.py` | Fail-closed behavior; no fabricated traces. |
| Fixture canonicity | `config/csl-fixture-mirrors.json` | Validated by `python3 bench/gates/csl_fixture_mirror_gate.py`; canonical fixture copies remain under `examples/` and schema-registered in `config/schema-targets.json`. |

Related pattern and surface modules (implementation SSoT for the specific
family they cover):

- `runtime/zig/src/doe_wgsl/emit_csl_host.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_maps.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_matmul.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_host_runtime.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_attention.zig`, `emit_csl_fused_ffn.zig`,
  `emit_csl_fused.zig`, `emit_csl_reduce_dist.zig`, `emit_csl_sample.zig`

Related user-facing entrypoints:

- [`runtime/zig/README.md`](../runtime/zig/README.md)
- [`runtime/zig/examples/csl-runtime-smoke.json`](../runtime/zig/examples/csl-runtime-smoke.json)

## Fixture mirrors: `examples/` vs `runtime/zig/examples/`

Some CSL fixture files appear at both `examples/<name>.json` and
`runtime/zig/examples/<name>.json`. The canonical copy is the one under
`examples/` — that is the path registered in `config/schema-targets.json` and
cross-validated by the schema hard gate. The `runtime/zig/examples/` copy is
a runtime-local mirror kept path-adjacent to the Zig build so the runtime can
resolve fixtures relative to its own tree without reaching up the repo.

Mirror pairs and intentional runtime-only fixtures are declared in
`config/csl-fixture-mirrors.json` and checked by
`python3 bench/gates/csl_fixture_mirror_gate.py`. Most mirrors are bytewise
identical. A mirror may differ only when the registry declares a path-context
JSON pointer; the Gemma 4 E2B simulator plan currently permits only
`/driver/executablePath`, because that field is resolved relative to the
simulator-plan file location.

Rules when modifying a mirrored fixture:

- Edit `examples/<name>.json` first; re-run `python3 bench/gates/schema_gate.py`.
- Re-run `python3 bench/gates/csl_fixture_mirror_gate.py`.
- Update the `runtime/zig/examples/<name>.json` mirror in the same change so
  byte-identical pairs stay bytewise identical.
- For path-context mirrors, keep every field identical except the registry's
  declared JSON pointers.
- An undeclared divergence between the two copies is a contract bug, not a
  design choice. Treat it as a blocker on any change that touches either copy.
