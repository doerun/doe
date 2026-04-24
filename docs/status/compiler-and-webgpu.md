# Doe status: compiler and WebGPU

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

**Scope notice:** 2026-04-24 TSIR entries moved to
[`tsir.md`](./tsir.md); 2026-04-23 TSIR Step 4 history moved to
[`archive/2026-04.md`](archive/2026-04.md). **New TSIR entries go in
[`tsir.md`](./tsir.md).** This shard stays focused on non-TSIR
compiler work (shader compiler non-TSIR paths, WebGPU runtime,
robustness).

## 2026-04-24 — WS2 gap report: four real-Doppler-kernel SPIR-V failures, two root causes

Diagnosed the WGSL→SPIR-V failures blocking WS2 end-to-end green
(per stderr in
`bench/out/doppler-reference/doe-webgpu-export.stderr.log`). Four
real Doppler kernels fail `createShaderModule (Vulkan)`. Three share
one bug; the fourth is separate.

### Root cause 1 — if/else-both-return not recognized as terminal

Affects:
- `dequant_f16_rowwise.wgsl` (Q4_K dequant → f16, row-wise stride)
- `dequant_f16_out_vec4.wgsl` (Q4_K dequant → f16, vec4 variant)
- `rmsnorm.wgsl` (RMSNorm with fused residual add)

Failure site (same for all three):
`runtime/zig/src/doe_wgsl/emit_spirv.zig:303` fires `error.InvalidIr`
because `emit_function` sees a function with non-void return type whose
body completed without an explicit terminator.

**Bug location:**
`runtime/zig/src/doe_wgsl/emit_spirv_fn.zig:195` — the `.if_` case in
`emit_stmt` unconditionally returns `false` (not-terminated), even
when both the then-branch and else-branch are terminated. Lines
185/190 correctly compute `then_terminated` / `else_terminated`;
line 195 throws that information away.

Minimum repro (verified against `doe-emit-spirv`):
```wgsl
fn both_branches_return(x: u32) -> u32 {
    if (x > 0u) { return 1u; } else { return 0u; }
}
```
Fails `InvalidIr`. Adding any statement (including a redundant
`return 99u;`) after the if-else makes it compile. Moving either
branch outside the if (e.g., last `return 0u;` as a trailing
fallthrough) also compiles.

**Fix direction:** in `emit_spirv_fn.zig:195`, return
`then_terminated and else_terminated and if_stmt.else_block != null`.
SPIR-V structured control flow additionally requires that the merge
label not be orphaned — when both branches terminate, either skip
emitting the merge label or emit `OpUnreachable` as its sole
instruction. The function-scope fallthrough at `emit_spirv.zig:299–304`
should then correctly see the function body as terminated and skip
the implicit `OpReturn` emit.

**Session-scale?** Yes, the fix is localized to `emit_stmt` in one
file. Coverage tests should hit if/else-both-return in various
contexts (nested, with shared suffix after, inside loops) before
landing.

### Root cause 2 — scalar coerce_binary_operand called with non-scalar source

Affects:
- `attention_head256_f16kv.wgsl` (f16 head-256 attention, prefill)

Failure site:
`runtime/zig/src/doe_wgsl/emit_spirv_fn.zig:772` fires
`error.UnsupportedConstruct` from `emit_scalar_construct_from_type`,
called via `coerce_binary_operand` at line 727. Target type is
scalar; source type is not a scalar. The function unwraps
`source_type` as `.scalar`, falls through the switch `else`, and
errors.

**What this means:** somewhere in the attention kernel, Doe's sema
or IR produces a binary operation whose target type is a scalar
(f32/f16/u32/i32) while the value being coerced has a non-scalar
type (vector, array element with the wrong shape, or similar). The
stderr doesn't name the specific expression.

**Suspect WGSL constructs** (by inspection of the kernel):
- Local `var q_local: array<vec4<f32>, HEAD_DIM_VECS>` used in nested
  loops; indexed access produces vec4<f32> refs.
- Mixed-type arithmetic: `dot(q_local[d4], vec4<f32>(shared_block[...]))`
  where `shared_block` is `array<vec4<f16>, ...>`; the explicit
  `vec4<f32>(vec4<f16>)` cast should go through coerce's `.vector →
  .vector` branch, but may instead hit a scalar-target path in some
  edge case.
- `continue` statements inside nested loops over `BLOCK_SIZE=32`
  arrays.
- `vec4<f16>` type in shared-workgroup allocations.

**Fix direction:** needs a minimum repro to pinpoint which
binary-op site produces the scalar-target-with-vector-source shape.
The fix may be in sema (where types are resolved) or in
`coerce_binary_operand` itself (if the source type it sees is legal
in WGSL but the coercion path doesn't handle it).

**Session-scale?** Probably, once a repro is cut. Days-scale if the
fix cascades into sema's type resolution for large function-local
arrays or vec4<f16> positional uses.

### What this unblocks

Both fixes land → Doe WebGPU compiles all four real Doppler kernels
→ Gemma 3 1B prefill can actually execute on Vulkan → KV buffers
write non-zero bytes → WS2's `realKvCache=false` flips to `true` for
the Gemma 3 shared contract → parity lane can compare tokens/logits
against the Program Bundle reference for real instead of for
trivially-zeroed execution.

Root cause 1 is the higher-priority fix: it's simpler, affects three
of four kernels, and is a single-file change. Root cause 2 is
follow-on; the attention kernel alone won't unblock WS2 end-to-end
unless the dequant+norm kernels also compile.

## 2026-04-24

- Gemma 3 1B now has a Doe WebGPU capture graph at
  `bench/out/doppler-capture/gemma-3-1b-doe-webgpu-capture-graph.json`.
  The capture tool accepts explicit model labels/capture IDs while preserving
  the Gemma-4 E2B default path, and `config/schema-targets.json` registers the
  Gemma 3 graph against `config/doe-webgpu-capture-graph.schema.json`.
- Gemma 3 1B Program Bundle -> Doe shared contract -> Doe WebGPU transcript
  plumbing is now materialized at:
  `bench/out/doppler-reference/gemma-3-1b-shared-execution-contract.json`,
  `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-transcript.json`, and
  `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-shared-execution-parity.json`.
  The source manifest, execution graph, and input-set hashes match the
  Program Bundle reference, and the prompt contract preserves Gemma chat
  templating.
- Gemma 3 1B is still not green through Doe WebGPU. The current transcript
  emits token `[1]` and stops after one decode step, while the Program Bundle
  reference emits eight tokens and stops by `decode_steps_exhausted`. KV/cache
  byte readback is captured, but all layer key/value digests are zero-buffer
  digests; receipts now classify that as `realKvCache=false` rather than
  promotion evidence.

## Current state

- TSIR (Tiled Spatial IR) current state and contracts live in
  [`tsir.md`](./tsir.md); that shard owns schema, digests, frontend,
  planner, collective-synthesis pass, reference interpreter, backend
  emitters (skeleton + semantic-aware body paths), parity CLI, manifest
  fixtures, and canary. Do not duplicate those bullets here.
- Postfix `++` / `--` statements are now supported in the WGSL compiler
  (tokens, lexer, AST `inc_stmt`/`dec_stmt`, parser, sema, IR lowering).
  `ir_transform` / `emit_spirv` errors are surfaced with specific kinds
  instead of silently becoming empty `OOM` strings, and the failing-kernel
  log carries the first 120 chars of the WGSL so failures are identifiable
  without re-running.
- The Doe WebGPU shared-contract lane has real transcript and parity plumbing,
  but it is not green end to end.
- The current blocker is in `runtime/zig/src/doe_wgsl/`, not Vulkan feature
  discovery.
- Vulkan-side capability bring-up has improved: the adapter now advertises
  `shader-f16` correctly, and the shared-contract runner can force subgroup
  removal with `DOE_DISABLE_SUBGROUPS=1`.

## Active blockers

- WGSL semantic-analysis and/or SPIR-V emission gaps still block some real
  Doppler kernels in the shared-contract lane.
- Mixed subgroup and non-subgroup entrypoints remain a real compiler surface.
- Real non-zero KV/cache evidence is still not emitted in the WebGPU transcript
  path; current Gemma 3 1B readbacks prove zero cache writes on the Doe lane.

## Landed infrastructure

- Shared-contract WebGPU transcript receipt
- Pairwise parity binder
- Generic transcript parity report surface
- Vulkan API-version and feature-capability fixes that expose `shader-f16`
  correctly
- Shared-contract runner defaults that force the declared subgroup workaround
  instead of silently relying on unsupported subgroup lowering

## Ground truth

- The WebGPU lane is blocked by WGSL compiler work, not by contract design.
- The current failures are concrete compiler/runtime gaps with named files and
  reproducible signatures.

## Use this shard for

- `doe_wgsl` compiler status
- WebGPU shared-contract transcript status
- WebGPU parity blockers
- Vulkan capability / adapter issues that affect the WebGPU lane
