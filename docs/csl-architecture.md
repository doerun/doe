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

## Source of truth

The most relevant implementation docs today are the module comments in:

- `runtime/zig/src/doe_wgsl/emit_csl_classify.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_host.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_maps.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_matmul.zig`
- `runtime/zig/src/doe_wgsl/emit_csl_host_runtime.zig`
- `runtime/zig/src/doe_wgsl/csl_spec.zig`

Related user-facing entrypoints:

- [`runtime/zig/README.md`](../runtime/zig/README.md)
- [`runtime/zig/examples/csl-runtime-smoke.json`](../runtime/zig/examples/csl-runtime-smoke.json)
