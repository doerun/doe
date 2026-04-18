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
| Classifier: which WGSL kernel patterns are recognized | `runtime/zig/src/doe_wgsl/emit_csl_classify.zig` | Pattern coverage changes here, not in prose. |
| Doppler `execution-v1` → CSL pattern mapping | `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` | |
| HostPlan emission | `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig` | Schema-backed; HostPlan is the contract boundary. |
| External SDK driver seam | `runtime/zig/tools/csl_sdk_driver.py` | Fail-closed behavior; no fabricated traces. |
| Fixture canonicity | `examples/doe-wgsl-*.json` registered in `config/schema-targets.json` | See "Fixture mirrors" below. |

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

Rules when modifying a mirrored fixture:

- Edit `examples/<name>.json` first; re-run `python3 bench/gates/schema_gate.py`.
- Update the `runtime/zig/examples/<name>.json` mirror in the same change so
  the two stay bytewise identical.
- A divergence between the two copies is a contract bug, not a design choice.
  Treat it as a blocker on any change that touches either copy.
