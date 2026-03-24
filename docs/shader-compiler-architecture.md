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

| Layer | Files | Lines | Status |
|-------|-------|-------|--------|
| Lexer/Parser/AST | token, lexer, ast, parser, parser_decl, parser_expr, parser_stmt | 2,575 | Production, sharded |
| Semantic analysis | sema, sema_attrs, sema_body, sema_helpers, sema_resolve, sema_types | 1,821 | Production, sharded |
| IR + validation | ir, ir_builder, ir_validate | 1,263 | Production |
| IR → MSL | emit_msl, emit_msl_ir, emit_msl_maps, emit_msl_stage, emit_msl_texture | 1,206 | Production, compute + vertex/fragment |
| IR → HLSL | emit_hlsl, emit_hlsl_maps, emit_hlsl_stage | 1,059 | Production, compute + vertex/fragment (struct I/O, builtins, MRT, frag_depth, interpolation) |
| IR → SPIR-V | emit_spirv, emit_spirv_builtins, emit_spirv_fn, emit_spirv_stages, spirv_builder | 2,843 | Working, compute + vertex/fragment (struct I/O, builtins, MRT, frag_depth, interpolation); samplers/graphics incomplete |
| IR → DXIL (native) | dxil_spec, dxil_bitcode, dxil_builder, dxil_serialize, dxil_container, emit_dxil_native, emit_dxil | 2,670 | Primary path; native LLVM 3.7 bitcode + DXBC container, DXC fallback available |
| Legacy MSL | doe_wgsl_msl | 641 | Legacy regex-based path |
| Public API + tests | mod.zig, mod_*_test.zig, emit_*_test.zig, coverage_*_test.zig | Sharded | All four translateTo* wired; tests split by backend, coverage, and integration concern |
| **Total** | **~80 files** | **~16,000+** | Approximate; file/line counts are approximate and have grown since the original audit |

## Remaining work (current reality)

1. **The current compute kernel corpus is now on the native Vulkan path, but the surface is still intentionally narrow.**
   - The native compute slice now includes storage-buffer runtime arrays, workgroup/storage atomics, `dot`, `sin`, `fract`, `texture_2d<f32>`, `texture_storage_2d<rgba8unorm, write>`, `textureLoad`, `textureStore`, Vulkan image/view creation, texture upload/query/destroy commands, and descriptor-image writes for `.texture` / `.storage_texture` bindings.
   - Remaining Vulkan work is now narrower:
     - sampled samplers / `textureSample*`
     - broader texture/storage-texture format coverage
     - graphics-stage IO and render-pipeline integration

2. **Shader-side vertex/fragment emission is functional across all backends.**
   - Vertex/fragment builtins, stage IO, struct I/O decomposition, inter-stage locations, interpolation decorations, MRT, frag_depth, and discard are parsed, lowered to IR, and emitted correctly by MSL, HLSL, and SPIR-V.
   - Render pipeline runtime integration (render pass wiring, location assignment at pipeline creation, draw command encoding) remains open.

3. **SPIR-V validation/build proof is still outstanding.**
   - The native SPIR-V path has moved well beyond the original stub state, but it still needs an actual build/validation pass (`zig build`, `spirv-val`) to prove the current emitter/runtime integration.

4. **Compiler correctness coverage is still thin.**
   - The compiler is still primarily exercised by benchmark kernels and runtime usage.
   - A dedicated shader-focused test suite is still needed for parser/sema/IR/emitter regressions.

5. **File-size debt still exists, but the old list is stale.**
   - `sema.zig` was already sharded and should not be listed as the original blocker anymore.
   - `parser.zig` and likely `emit_spirv.zig` still need sharding to stay aligned with the 777-line policy.

6. **Native DXIL is implemented but needs broader validation.**
   - The primary D3D12 path is now `IR -> native DXIL bytecode` (no external DXC).
   - DXC fallback remains available via `emitWithToolchainConfig`.
   - Remaining: DXIL validator coverage, vertex/fragment completeness, production Windows evidence.
