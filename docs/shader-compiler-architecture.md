# Shader compiler architecture

## Pipeline

```
WGSL source text
       │
       ▼
┌─────────────┐
│   Lexer     │  token.zig, lexer.zig
│  (tokenize) │
└──────┬──────┘
       │ Token[]
       ▼
┌─────────────┐
│   Parser    │  parser.zig, ast.zig
│  (parse)    │
└──────┬──────┘
       │ Ast
       ▼
┌─────────────┐
│    Sema     │  sema.zig, sema_attrs.zig, sema_body.zig, sema_types.zig
│  (analyze)  │
│             │  name resolution, type resolution, builtin resolution,
│             │  binding/attribute extraction
└──────┬──────┘
       │ SemanticModule
       ▼
┌─────────────┐
│ IR Builder  │  ir_builder.zig → ir.zig
│  (lower)    │
│             │  typed SSA-like values, explicit blocks + control flow,
│             │  explicit address spaces, explicit bindings/builtins
└──────┬──────┘
       │ ir.Module
       ▼
┌─────────────┐
│ IR Validate │  ir_validate.zig
│  (verify)   │
└──────┬──────┘
       │ ir.Module (validated)
       │
       ├────────────────┬────────────────┐
       │                │                │
       ▼                ▼                ▼
┌────────────┐  ┌─────────────┐  ┌─────────────┐
│  Metal     │  │   Vulkan    │  │    D3D12    │
│            │  │             │  │             │
│ emit_msl   │  │ emit_spirv  │  │ emit_dxil   │
│ emit_msl_ir│  │ spirv_builder│  │ (native)   │
│            │  │             │  │             │
│ IR → MSL   │  │ IR → SPIR-V │  │ IR → DXIL  │
│ (text)     │  │ (binary)    │  │ (binary)   │
└─────┬──────┘  └──────┬──────┘  └──────┬──────┘
      │                │                │
      ▼                ▼                ▼
  MSL text        SPIR-V words     DXIL bytecode
      │                │                │
      ▼                ▼                ▼
 xcrun metal      VkCreateShader    D3D12 driver
 (platform)       Module (driver)
      │
      ▼
 MTLLibrary
```

Key invariant: every backend enters at `ir.Module`. No backend reads AST directly. The only external tool in the default pipeline is xcrun metal on macOS; Vulkan (SPIR-V) and D3D12 (DXIL) are fully native.

## WebGPU integration

The compiler is internal to the WebGPU API. Consumers never see IR, MSL, SPIR-V, or HLSL.

This diagram shows the **headless native path** (Node.js / Bun → Zig). The
browser wrapper path (`packages/doe-gpu/src/browser.js`) does not use the Doe
shader compiler — it delegates `createShaderModule` to the browser's own WebGPU
implementation, which compiles shaders internally.

```
JS / C application
       │
       │  wgpuDeviceCreateShaderModule(device, {code: "WGSL..."})
       ▼
┌──────────────────┐
│   WebGPU API     │  wgpu_dropin_lib.zig (symbol routing)
│   (C ABI)        │  doe_wgpu_native.zig (native impl)
└───────┬──────────┘
        │  stores WGSL source + extracts bindings
        │
        │  wgpuDeviceCreateComputePipeline(device, {module, entryPoint})
        ▼
┌──────────────────┐
│  Backend Router  │  picks Metal / Vulkan / D3D12 based on runtime
└───┬───────┬──────┴──────┐
    │       │             │
    ▼       ▼             ▼
  Metal   Vulkan        D3D12
  native  native        native
  runtime runtime       runtime
    │       │             │
    ▼       ▼             ▼
  doe_wgsl compiler (shared)
    │       │             │
    ▼       ▼             ▼
  MSL    SPIR-V      DXIL (native)
    │       │             │
    ▼       ▼             ▼
  Metal   Vulkan       D3D12
  driver  driver       driver
    │       │             │
    └───────┼─────────────┘
            ▼
    GPU pipeline object
            │
            ▼
    wgpuComputePassEncoderDispatchWorkgroups(...)
            │
            ▼
          GPU
```

## TSIR path for spatial backends

The current compiler pipeline in this document is the operative path for Metal,
Vulkan, and D3D12. It is also the frontend path that today's CSL classifier
consumes. The general WGSL -> spatial-backend route adds a Tiled
Spatial IR (TSIR) between Doe IR and backend emission so residency, tiling,
collectives, and exactness are declared in one place instead of re-derived by
per-kernel emitters.

This path is documented in
[`docs/tsir-lowering-plan.md`](./tsir-lowering-plan.md). Phase A compiler
surface (schema, digests, frontend, planner, reference interpreter,
collective-synthesis pass, and five backend emitters whose realization-only
entry points still serialize contract skeletons while their semantic-aware
entry points emit executable bodies for the Phase A bootstrap families)
is landed under `runtime/zig/src/tsir/`; live status is in
[`docs/status/tsir.md`](./status/tsir.md). TSIR is not yet the wired
executable compiler path for CSL or WebGPU — the live CSL lane still
routes through the classifier/template path and the Doe IR →
MSL/SPIR-V/HLSL WebGPU lanes remain live.

## Comparison with Dawn/Tint

Dawn is Google's WebGPU implementation. Tint is Dawn's shader compiler.

| Dimension | Dawn/Tint | Doe |
|-----------|-----------|-----|
| Language | C++ | Zig |
| Compiler size | ~200K LOC (Tint) | ~13.7K LOC |
| IR | Mature SSA with transforms and optimization | Minimal typed IR, no optimization passes |
| Metal target | MSL text (same) | MSL text (same) |
| Vulkan target | Native SPIR-V writer (mature) | Native SPIR-V writer (new, compute-only) |
| D3D12 target | HLSL text → DXC (permanent) | Native DXIL bytecode (primary); HLSL text → DXC (fallback) |
| GLSL | Has a GLSL writer for compat | Not a target |
| Shader stages | Compute + vertex + fragment + full graphics | Compute + vertex + fragment |
| Optimization | Dead code elimination, constant folding, binding remapping, robustness injection | None yet |
| Robustness | Bounds checks, null guards per spec | IR robustness transform for arrays/vectors/matrices, runtime-sized arrays, and texture coordinates; Lean-proven bounds elimination for dispatch-fit patterns |
| Polyfills | Emulates missing features per driver | Explicit unsupported errors |

Structural similarity: both follow WGSL → AST → semantic analysis → typed IR → per-backend emission. Doe is ~15x smaller and does not yet have optimization passes, but does have robustness injection (bounds checks on arrays, runtime-sized arrays, vectors, matrices, and texture coordinates, with Lean-proven bounds elimination for dispatch-fit patterns).

## Why custom Zig IR (not SPIR-V as universal IR)

SPIR-V was evaluated as a universal IR: WGSL → SPIR-V → all backends.

Rejected because:

1. **Unnecessary round-trip.** SPIR-V-to-Metal mapping is mechanically sound (SPIRV-Cross and MoltenVK do it daily; the binding model is translatable). But using SPIR-V as IR means Doe would need both a SPIR-V writer (for Vulkan) and a SPIR-V reader (for MSL/DXIL input). An in-memory IR that all backends consume directly avoids both the write and the read for non-Vulkan targets.

2. **Vulkan-specific constructs leak into non-Vulkan backends.** SPIR-V carries Vulkan-specific concepts: interface variables, explicit StorageClass rules, structured merge/continue blocks. MSL and DXIL backends would need to translate through these constructs even though they don't need them. A purpose-built IR carries only what all backends share.

3. **Proof boundary complexity.** Lean verification targets the semantic IR. Proving properties on SPIR-V words requires modeling SPIR-V's type/decoration/storage-class system in Lean. A smaller, purpose-built IR with known invariants is easier to verify.

4. **Practical simplicity.** The custom IR is ~1,028 LOC (ir.zig + ir_builder.zig + ir_validate.zig). A SPIR-V reader of comparable scope would serve only the non-Vulkan backends.

Note: holding SPIR-V in-memory Zig structs without binary serialization was also considered. This carries SPIR-V's data model complexity (StorageClass rules, decoration system, merge blocks) without SPIR-V's tooling benefits (spirv-val requires serialized binary). Worst of both worlds.

## D3D12 backend strategy

### Why the driver eats DXIL, not HLSL

The D3D12 driver does not accept HLSL text. The actual chain is:

```
HLSL text          ← not consumed by driver
    │ (DXC)
    ▼
DXIL container     ← LLVM 3.7 bitcode + metadata + signatures
    │ (D3D12 API)
    ▼
D3D12 driver       ← consumes DXIL, compiles to GPU ISA
```

This is analogous to Metal (driver eats AIR, not MSL) and unlike Vulkan (driver eats SPIR-V directly, no intermediate compiler needed).

### Current architecture: native DXIL (primary), IR → HLSL → DXC (fallback)

The primary D3D12 path now generates DXIL bytecode natively in Zig. The native
emitter translates Doe IR to LLVM 3.7 bitcode via `dxil_builder`, serializes
it via `dxil_serialize`, and wraps it in a DXBC container via
`dxil_container`. No external toolchain is required.

DXC remains available as a fallback path for validation against the reference
compiler. The fallback generates HLSL text from the IR and invokes DXC to
produce DXIL, the same pattern as xcrun metal on macOS.

| Platform | Primary path | External tool needed | Binary format |
|----------|-------------|---------------------|---------------|
| macOS | IR → MSL text → xcrun metal | xcrun metal (on system) | metallib/AIR |
| Windows | IR → DXIL bytecode (native) | None | DXIL |
| Linux | IR → SPIR-V (native) | None | SPIR-V |

For the npm package, no external compiler download is needed on any platform:
- macOS: ~2MB (xcrun metal already on system)
- Linux: ~2MB (native SPIR-V, no external tool)
- Windows: ~2MB (native DXIL, no external tool)

DXC fallback contract (for validation or legacy use):

- explicit pin: `DOE_WGSL_DXC=/absolute/or/workspace-relative/path/to/dxc(.exe)`
- explicit PATH opt-in: `DOE_WGSL_DXC=PATH`
- explicit code path: `doe_wgsl.translateToDxilWithToolchainConfig(..., .{
  .executable = ...,
  .discovery = .explicit_config,
})`
- if `DOE_WGSL_DXC` is unset, the native path is used (no external tool needed)

### Native DXIL emission (implemented)

Native DXIL emission is now the primary D3D12 path. The implementation consists
of 6 modules (2,303 LOC total) that encode LLVM 3.7 bitcode, build DXIL
instructions from the Doe IR, serialize the bitcode, and wrap it in a DXBC
container.

| Pro | Con |
|-----|-----|
| Zero external dependencies | Must independently pass Microsoft's DXIL validator |
| Much faster compilation (skip LLVM optimization) | No optimization — driver must compensate |
| Full auditability for Lean verification | Must track DXIL spec revisions manually |
| Tiny binary | |

Remaining work: broader DXIL validator coverage, vertex/fragment stage
completeness, and production Windows evidence.

**Option B: SPIR-V → Mesa nir_to_dxil.** Mesa's Dozen driver (Microsoft-contributed, ships in WSL2) translates SPIR-V → NIR → DXIL in production. Since Doe already produces SPIR-V, this would cost zero new translation code.

| Pro | Con |
|-----|-----|
| Doe already produces SPIR-V — zero new translation code | Not currently available as a callable library |
| Production-proven (runs in every WSL2 install) | Bundling Mesa requires NIR (~50K LOC C) + nir_to_dxil (~15K LOC C) |
| Battle-tested DXIL output | Tracking Mesa releases for compatibility |

Currently blocked by availability: nir_to_dxil is internal to Mesa's Vulkan ICD with no standalone library packaging. If Microsoft or Mesa ever expose it as a callable library, this becomes the cheapest D3D12 path and should be re-evaluated.

### Paths evaluated and rejected

**IR → SPIR-V → DXC -spirv → DXIL.** Reuses Doe's SPIR-V output, but DXC's SPIR-V ingestion path is less tested than its HLSL path and pulls in SPIRV-Tools as an additional dependency. More fragile than HLSL→DXC with no clear benefit.

**IR → SPIR-V → custom SPIR-V-to-DXIL translator.** Same LLVM bitcode encoding problem as native DXIL, plus requires a SPIR-V reader Doe doesn't have. Strictly more work than native DXIL.

**LLVM IR as shared IR (DXIL falls out naturally).** DXIL is literally LLVM 3.7 IR, so this eliminates D3D12 translation entirely. But LLVM IR is designed for C/C++ optimization, not GPU shader semantics. MSL and SPIR-V backends would translate from the wrong abstraction level. Also defeats "2MB binary" unless Doe maintains an LLVM-compatible format without LLVM.

**Use Tint/Dawn for D3D12 only.** BSD-licensed, mature, handles everything. But adds ~200K LOC C++ for one backend, introduces a second shader compiler with potentially different behavior, and contradicts the self-contained thesis.

**Don't support D3D12.** WebGPU on Windows can run on Vulkan via lavapipe/Dozen. But D3D12 is the performant Windows path. Dropping it loses the Windows gaming/enterprise market.

## Current state

This document describes the compiler architecture, not live coverage totals.
Current compiler/runtime status belongs in
[`docs/status/compiler-and-webgpu.md`](./status/compiler-and-webgpu.md), and
TSIR implementation status belongs in [`docs/status/tsir.md`](./status/tsir.md).
Counts, pass/fail totals, and benchmark results should come from artifacts and
gates, not from prose in this architecture note.

## Related docs

- [`docs/architecture.md`](./architecture.md) — project-level
  architecture (where this doc sits in the broader compiler/runtime
  story)
- [`docs/csl-architecture.md`](./csl-architecture.md) — sibling
  compiler doc covering the Cerebras CSL lane
- [`docs/tsir-lowering-plan.md`](./tsir-lowering-plan.md) for the
  WGSL -> TSIR -> backend lowering architecture and parity-oracle contract
  (Phase A compiler surface landed; live status in
  [`docs/status/tsir.md`](./status/tsir.md))
- [`docs/loop-protocol.md`](./loop-protocol.md) — build-iteration vs
  parity-iteration discipline that drives incremental TSIR + parity
  landing

## Remaining work

Do not maintain a second live backlog in this architecture doc. Track current
compiler gaps in [`docs/status/compiler-and-webgpu.md`](./status/compiler-and-webgpu.md)
or, for TSIR-specific work, [`docs/status/tsir.md`](./status/tsir.md). Keep
this document focused on the stable pipeline shape and backend strategy.
