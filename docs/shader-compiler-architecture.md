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
│ emit_msl   │  │ emit_spirv  │  │ emit_hlsl   │
│ emit_msl_ir│  │ spirv_builder│  │ (→ DXC)    │
│            │  │             │  │             │
│ IR → MSL   │  │ IR → SPIR-V │  │ IR → HLSL  │
│ (text)     │  │ (binary)    │  │ (text)     │
└─────┬──────┘  └──────┬──────┘  └──────┬──────┘
      │                │                │
      ▼                ▼                ▼
  MSL text        SPIR-V words     HLSL text
      │                │                │
      ▼                ▼                ▼
 xcrun metal      VkCreateShader    DXC (dxcompiler.dll)
 (platform)       Module (driver)   (platform compiler)
      │                                 │
      ▼                                 ▼
 MTLLibrary                         DXIL bytecode
                                        │
                                        ▼
                                   D3D12 driver
```

Key invariant: every backend enters at `ir.Module`. No backend reads AST directly. External tools (xcrun, DXC) are platform compilers, not translation hosts.

## WebGPU integration

The compiler is internal to the WebGPU API. Consumers never see IR, MSL, SPIR-V, or HLSL.

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
  MSL    SPIR-V      HLSL→DXC
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

## Comparison with Dawn/Tint

Dawn is Google's WebGPU implementation. Tint is Dawn's shader compiler.

| Dimension | Dawn/Tint | Doe |
|-----------|-----------|-----|
| Language | C++ | Zig |
| Compiler size | ~200K LOC (Tint) | ~7.7K LOC |
| IR | Mature SSA with transforms and optimization | Minimal typed IR, no optimization passes |
| Metal target | MSL text (same) | MSL text (same) |
| Vulkan target | Native SPIR-V writer (mature) | Native SPIR-V writer (new, compute-only) |
| D3D12 target | HLSL text → DXC (permanent) | HLSL text → DXC (default; native DXIL as future option) |
| GLSL | Has a GLSL writer for compat | Not a target |
| Shader stages | Compute + vertex + fragment + full graphics | Compute only |
| Optimization | Dead code elimination, constant folding, binding remapping, robustness injection | None yet |
| Robustness | Bounds checks, null guards per spec | Not implemented |
| Polyfills | Emulates missing features per driver | Explicit unsupported errors |

Structural similarity: both follow WGSL → AST → semantic analysis → typed IR → per-backend emission. Doe is 25x smaller and does not yet have optimization, robustness, or graphics pipeline support.

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

### Default architecture: IR → HLSL → DXC

DXC on Windows is the same pattern as xcrun metal on macOS: a platform-provided compiler that turns text into the binary the driver consumes.

| Platform | Text format | Platform compiler | Binary format |
|----------|------------|-------------------|---------------|
| macOS | MSL | xcrun metal (on system) | metallib/AIR |
| Windows | HLSL | DXC (on system or downloaded) | DXIL |
| Linux | — | — (native SPIR-V) | SPIR-V |

For the npm package, DXC is conditionally downloaded on Windows only:
- macOS: ~2MB (xcrun metal already on system)
- Linux: ~2MB (native SPIR-V, no external tool)
- Windows with SDK: ~2MB (DXC already on system)
- Windows without SDK: ~2MB + ~20MB DXC download

Current Doe DXC contract:

- explicit pin: `DOE_WGSL_DXC=/absolute/or/workspace-relative/path/to/dxc(.exe)`
- explicit PATH opt-in: `DOE_WGSL_DXC=PATH`
- explicit code path: `doe_wgsl.translateToDxilWithToolchainConfig(..., .{
  .executable = ...,
  .discovery = .explicit_config,
})`
- unset `DOE_WGSL_DXC` still falls back to PATH for backward compatibility, but
  that mode is not the reproducible contract Doe wants for governed runs
- native DXIL emission is still not implemented; the final DXIL container still
  comes from an external DXC process

### Future options (not blocking, neither foreclosed)

**Option A: Native DXIL emission.** Write an LLVM 3.7 bitcode encoder + DXIL container builder in Zig. Eliminates DXC dependency entirely. Same pattern as native SPIR-V for Vulkan.

| Pro | Con |
|-----|-----|
| Zero external dependencies | LLVM bitcode encoding is an order of magnitude harder than SPIR-V |
| Potentially much faster compilation (skip LLVM optimization) | Must independently pass Microsoft's DXIL validator |
| Full auditability for Lean verification | No optimization — driver must compensate |
| Tiny binary | Must track DXIL spec revisions manually |

Only justified if compilation latency or binary size becomes a measured bottleneck.

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

| Layer | Files | Lines | Status |
|-------|-------|-------|--------|
| Lexer/Parser/AST | token, lexer, ast, parser | 2,332 | Production |
| Semantic analysis | sema, sema_helpers, sema_types | 1,060 | Production, sharded |
| IR + validation | ir, ir_builder, ir_validate | 1,040 | Production |
| IR → MSL | emit_msl, emit_msl_ir | 576 | Production, compute |
| IR → HLSL | emit_hlsl | 574 | Production, compute |
| IR → SPIR-V | emit_spirv, spirv_builder | 1,591 | Working, compute-first native path with storage/runtime arrays, barriers, atomics, `dot`, `sin`, `fract`, and narrow texture/image support; samplers/graphics incomplete |
| IR → DXIL | emit_dxil | 41 | Stub |
| Public API | mod.zig | 168 | All four translateTo* wired |
| **Total** | **17 files** | **7,382** | |

## Remaining work (current reality)

1. **The current compute kernel corpus is now on the native Vulkan path, but the surface is still intentionally narrow.**
   - The native compute slice now includes storage-buffer runtime arrays, workgroup/storage atomics, `dot`, `sin`, `fract`, `texture_2d<f32>`, `texture_storage_2d<rgba8unorm, write>`, `textureLoad`, `textureStore`, Vulkan image/view creation, texture upload/query/destroy commands, and descriptor-image writes for `.texture` / `.storage_texture` bindings.
   - Remaining Vulkan work is now narrower:
     - sampled samplers / `textureSample*`
     - broader texture/storage-texture format coverage
     - graphics-stage IO and render-pipeline integration

2. **Graphics stages are still not implemented.**
   - All native emitters are still compute-first.
   - Vertex/fragment IO, locations/interpolation, render pipeline lowering, and graphics-stage runtime integration remain open.

3. **SPIR-V validation/build proof is still outstanding.**
   - The native SPIR-V path has moved well beyond the original stub state, but it still needs an actual build/validation pass (`zig build`, `spirv-val`) to prove the current emitter/runtime integration.

4. **Compiler correctness coverage is still thin.**
   - The compiler is still primarily exercised by benchmark kernels and runtime usage.
   - A dedicated shader-focused test suite is still needed for parser/sema/IR/emitter regressions.

5. **File-size debt still exists, but the old list is stale.**
   - `sema.zig` was already sharded and should not be listed as the original blocker anymore.
   - `parser.zig` and likely `emit_spirv.zig` still need sharding to stay aligned with the 777-line policy.

6. **Native DXIL remains deferred.**
   - The architecture is still `IR -> HLSL -> DXC` for D3D12 by default.
   - Native DXIL is still a future option, not a current requirement for the documented architecture.
