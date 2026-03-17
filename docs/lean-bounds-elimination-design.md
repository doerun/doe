# Lean-verified bounds check elimination

## Status

Design approved. Layer 1 (unconditional clamping) is implemented in
`ir_transform_robustness.zig`. Layer 2 (Lean-verified elimination) has
theorem proofs in `pipeline/lean/Fawn/Shader/ComputeBounds.lean` and
requires Zig-side pattern recognition and dispatch-time precondition
enforcement to activate.

## Problem

The WebGPU specification requires that all shader buffer/texture accesses
are bounds-checked. `ir_transform_robustness.zig` injects `min(index,
length-1)` for every indexing operation unconditionally. This is correct
but costs one `min` instruction per array access — measurable in
tight compute kernels.

Tint (Dawn's shader compiler) added heuristic integer range analysis
(2024) to skip bounds checks when it can statically prove an access is
safe. This is sound but not formally verified — the analysis could have
bugs that silently remove necessary checks.

Doe's competitive advantage: Lean proofs that formally verify the
conditions under which an index is guaranteed in-bounds, with the
proofs consumed at compile time to elide clamps. Provably correct
bounds elimination, not heuristic.

## Architecture

### Two-layer robustness

```
Layer 1: Unconditional clamp (always present)
  ir_transform_robustness.zig → min(index, length-1) for every index

Layer 2: Lean-verified elimination (opt-in, -Dlean-verified=true)
  ComputeBounds.lean proves conditions → proven-conditions.json artifact
  → ir_transform_robustness.zig pattern-matches and skips clamp when
  proof conditions are met AND host-side dispatch enforces preconditions
```

Layer 1 is the safety net — it is always correct. Layer 2 is a
performance optimization that removes the clamp only when a formal proof
guarantees the clamp is a no-op.

### Core theorem

The fundamental insight:

```
global_invocation_id.x = workgroup_id.x * workgroup_size.x + local_invocation_id.x
```

GPU hardware guarantees:
- `workgroup_id.x < num_workgroups.x`
- `local_invocation_id.x < workgroup_size.x`

Therefore: `global_invocation_id.x < workgroup_size.x * num_workgroups.x`

If the host ensures `workgroup_size.x * num_workgroups.x ≤ array_length`
at dispatch time, then `global_invocation_id.x < array_length` and the
`min()` clamp is a no-op.

This is formalized as `gid_inbounds_when_dispatch_fits` in
`Fawn/Shader/ComputeBounds.lean`.

### Proof artifact integration

The proof artifact (`proven-conditions.json`) schema version 2 adds a
`boundsEliminations` array:

```json
{
  "schemaVersion": 2,
  "boundsEliminations": [
    {
      "theorem": "gid_inbounds_when_dispatch_fits",
      "pattern": "global_invocation_id.{component} indexes storage buffer",
      "precondition": "workgroup_size.{component} * num_workgroups.{component} <= buffer_element_count",
      "eliminates": "min(gid.{component}, arrayLength(&buf) - 1) → gid.{component}",
      "runtimePath": "runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_runtime_sized"
    },
    {
      "theorem": "flat_index_2d_inbounds",
      "pattern": "gid.y * width + gid.x indexes storage buffer",
      "precondition": "ws.x * nwg.x <= width AND ws.y * nwg.y <= height AND width * height <= buffer_element_count",
      "eliminates": "min(flat_index, arrayLength(&buf) - 1) → flat_index",
      "runtimePath": "runtime/zig/src/doe_wgsl/ir_transform_robustness.zig:clamp_runtime_sized"
    }
  ]
}
```

### Pipeline flow

```
1. Lean typecheck
   pipeline/lean/Fawn/Shader/ComputeBounds.lean is compiled.
   All theorems are verified by the Lean kernel.

2. Artifact extraction
   pipeline/lean/extract.sh runs Fawn/Extract.lean.
   Emits proven-conditions.json with boundsEliminations section.

3. Zig build
   build.zig reads proven-conditions.json when -Dlean-verified=true.
   lean_proof.zig validates the artifact at comptime.
   Sets lean_proof.bounds_elimination_available = true.

4. IR transform (compile time per shader)
   ir_transform_robustness.zig checks lean_proof.bounds_elimination_available.
   For each index expression:
   a. Pattern-match: is this gid.{x,y,z} indexing a storage buffer?
   b. If matched AND the shader declares @workgroup_size, record the
      binding + component + workgroup_size for host-side enforcement.
   c. Skip the min() clamp for this expression.
   d. Tag the shader module with a dispatch precondition table.

5. Host dispatch (runtime per dispatch call)
   doeNativeComputeDispatchFlush checks precondition table:
   - For each entry: workgroup_size.{component} * num_workgroups.{component}
     <= buffer_element_count
   - If ANY precondition fails, the dispatch still executes (safety is
     guaranteed by the proof — the condition failing means the shader
     would access out-of-bounds, which is a user error regardless).
   - Optional: emit a validation warning when precondition fails.
```

### Pattern recognizer (Zig-side, future implementation)

The pattern recognizer in `ir_transform_robustness.zig` will match:

1. **Direct gid access**: `buf[global_invocation_id.x]`
   - Index expression is a member access `.x`/`.y`/`.z` on a builtin
     `global_invocation_id` variable
   - Base is a `global_ref` to a storage buffer

2. **Flat 2D access**: `buf[gid.y * width + gid.x]`
   - Index expression is `binary(add, binary(mul, member(gid, y), const), member(gid, x))`
   - Both gid components have independent proofs; width is a pipeline constant

3. **Loop-carried access**: `buf[gid.x + i]` where `i < stride`
   - Requires compound precondition: `ws.x * nwg.x + stride <= buf.length`
   - Future extension, not in initial implementation

### Comparison with Tint

| Property | Tint | Doe |
|---|---|---|
| Method | Heuristic integer range analysis | Formal proof |
| Verifiability | Test suite | Lean kernel |
| False positives | Possible (analysis bug removes needed check) | Impossible (proof must be valid) |
| Coverage | Broader patterns (arbitrary integer flow) | Focused patterns (gid-based access) |
| Cost | C++ analysis pass at compile time | Zero runtime cost; one-time Lean build |
| Extensibility | Modify C++ analyzer | Add new Lean theorem |
| Auditability | Read 150K LOC C++ | Read 100-line Lean file |

Doe's approach is narrower but provably correct. The common case (compute
shader accessing `buf[gid.x]`) is covered by the core theorem. Tint's
range analysis covers more exotic patterns but cannot guarantee
correctness of the analysis itself.

## Theorems

### Verified (ComputeBounds.lean)

| Theorem | Category | What it proves |
|---|---|---|
| `gid_component_lt_total` | `lean_verified` | Single-dimension gid < array_length when dispatch fits |
| `gid_inbounds_when_dispatch_fits` | `lean_verified` | 1D dispatch: gid.x < buf.length when ws.x * nwg.x ≤ buf.length |
| `clamp_noop_when_inbounds` | `lean_verified` | min(gid, len-1) = gid when gid < len (connects proof to transform) |
| `gid_2d_inbounds` | `lean_verified` | Both components bounded independently for 2D dispatch |
| `flat_index_2d_inbounds` | `lean_verified` | gid.y * width + gid.x < width * height when components bounded |

### Why `lean_verified`

All theorems quantify over arbitrary `Nat` values (workgroup sizes,
dispatch dimensions, array lengths). Zig `comptime` cannot enumerate
these — the domains are unbounded. This is where Lean earns its keep,
exactly matching the criterion established in `pipeline/lean/README.md`.

## Implementation sequence

1. **Done**: `ir_transform_robustness.zig` — unconditional clamping (Layer 1)
2. **Done**: `Fawn/Shader/ComputeBounds.lean` — formal proofs
3. **Done**: `Extract.lean` updated to import Shader module and emit `boundsEliminations`
4. **Next**: Pattern recognizer in `ir_transform_robustness.zig` — match gid access patterns
5. **Next**: `lean_proof.zig` — read `boundsEliminations` from artifact, expose at comptime
6. **Next**: Dispatch precondition table in `DoeShaderModule`
7. **Next**: Host-side precondition check in `doeNativeComputeDispatchFlush`
8. **Future**: 2D flat index pattern, loop-carried access patterns

## File map

| File | Role |
|---|---|
| `pipeline/lean/Fawn/Shader/ComputeBounds.lean` | Formal proofs of compute bounds safety |
| `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig` | Layer 1 clamping + future Layer 2 pattern recognizer |
| `runtime/zig/src/lean_proof.zig` | Comptime proof artifact validator |
| `pipeline/lean/Fawn/Extract.lean` | Proof artifact extraction (emits proven-conditions.json) |
| `config/proof-artifact.schema.json` | Schema for proven-conditions.json |
| `docs/lean-bounds-elimination-design.md` | This document |
