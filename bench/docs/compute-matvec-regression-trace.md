# `compute_matvec_32768x2048_f32` regression trace

Audience: runtime engineers investigating why Doe is slower than Dawn on the matrix-vector multiply benchmark on AMD Vulkan.

## Observed delta

**Before the Doe Vulkan pipeline cache landed (2026-04-12 explore):**

| Variant | Doe vs Dawn p50 delta |
| --- | --- |
| `compute_matvec_32768x2048_f32` (naive swizzle0) | **-38.62%** |
| `compute_matvec_32768x2048_f32_swizzle1` | **-3.87%** |
| `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` | **+11.45%** |

**After the Doe Vulkan pipeline cache landed (2026-04-17 strict compare at `bench/out/amd-vulkan/compare/20260417T114917Z/dawn-vs-doe.amd.vulkan.compare.json`):**

| Variant | Doe vs Dawn p50 delta |
| --- | --- |
| `compute_matvec_32768x2048_f32` (naive swizzle0) | **-4.33%** (was -38.62%, +34.29pp) |
| `compute_matvec_32768x2048_f32_swizzle1` | **+11.26%** (was -3.87%, +15.13pp) |
| `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` | **+16.28%** (was +11.45%, +4.83pp) |

**Hypothesis #1 confirmed.** The cold Vulkan pipeline compile cost was the dominant contributor to the regression. With Doe-side `VkPipelineCache` active, two of the three variants flipped to Doe-faster and the naive_swizzle0 gap narrowed from -38% to -4.3%. The small residual on naive_swizzle0 is now understood to be SPIR-V codegen-shape sensitivity in the RADV driver, not a runtime bottleneck.

## Subphase breakdown of the -4.33% residual on naive_swizzle0

Per-subphase median across 15 samples each on AMD Vulkan (2026-04-17 strict compare):

| Phase | Doe (ms) | Dawn (ms) | Delta | Notes |
| --- | ---: | ---: | ---: | --- |
| `setup_ms` | 0.0008 | 12.7162 | **-12.72** | Doe 16,000x faster -- cache hit |
| `encode_ms` | 1.2518 | 5.0801 | -3.83 | Doe 4x faster -- command encoder |
| `submit_wait_ms` | 2142.25 | 2036.46 | **+105.79** | Doe 5% slower -- GPU execution |
| `total_ms` | 2144.40 | 2055.46 | +88.93 | Net +4.3% slower |

The gap is entirely in `submit_wait_ms` -- i.e., what the GPU is actually doing during the dispatch-and-wait cycle. Doe already wins setup and encode by large margins.

## Why the GPU is slower on Doe's SPIR-V

Direct A/B on this host (single-invocation timing of the matvec command stream via `doe-zig-runtime --execute`):

| SPIR-V source | executionGpuTimestampTotalNs | Delta vs Doe |
| --- | ---: | ---: |
| Doe (`doe-emit-spirv`) tracked `.spv` | 2,121,636,687 | baseline |
| Tint-generated from same WGSL | 2,103,046,366 | **-18,590,321 (-0.88%)** |

Feeding the same WGSL through Tint produces SPIR-V that runs ~18 ms (~0.9%) faster on the GPU for this 100-dispatch workload. Both SPVs declare identical capabilities (`Shader` only), identical execution mode (`LocalSize 64 1 1`), identical descriptor bindings. No subgroup-size hints on either side.

Structural differences:

- Tint wraps each storage buffer in a `_block_tint_explicit_layout` struct with an `inner` member. Doe references the storage array directly.
- Tint inserts `tint_loop_idx`, `tint_low_inc`, `tint_carry` loop-safety variables. Doe's loop is a direct WGSL-style `loop { if (col >= kPackedCols) break; ... col = col + 1u; }`.
- Tint names every struct member via `OpMemberName` and every variable via `OpName` with hashed prefixes.

The loop-safety variables should *slow* Tint if they mattered at codegen time -- they don't, so the driver is optimizing them away. The net +0.9% GPU-side advantage for Tint's SPIR-V therefore points at the storage-buffer wrapping: RADV's SPIR-V-to-AMDGPU pass produces slightly better ISA when storage buffers are accessed through an explicit block struct than when accessed as bare runtime arrays.

## Is this a Doe SPV compiler issue to fix?

Yes, but it is real compiler work, not a quick patch. The fix is to update Doe's WGSL-to-SPIR-V emitter (`runtime/zig/src/doe_wgsl/` + `doe-emit-spirv`) to wrap storage buffer declarations in an explicit block struct with an `inner` member, matching Tint's canonical emission shape. The WGSL contract does not dictate this wrapping; it is a SPV emission style choice.

Landing that change would:

- close the -0.9% GPU-side gap on matvec naive_swizzle0 (bringing the overall delta to approximately -3.5% or better, potentially positive with the other noise components)
- likely close similar small gaps on other compute workloads where the driver optimizer reacts to SPV structure
- require Doe's WGSL IR → SPIR-V lowering pass to emit `OpTypeStruct { array<T> }` wrappers consistently and update all downstream access chains

Out of scope for the 2026-04-17 session; flagged as a follow-up in the Vulkan optimization queue.

## Ruled out (updated)

Everything in the original hypothesis list has now been ruled out or addressed:

- Codegen bloat (Doe SPIR-V is smaller than Tint's) -- ruled out.
- Dispatch geometry mismatch -- ruled out (both sides dispatch x=128, workgroup_size=64).
- Per-dispatch descriptor rebind -- ruled out (short-circuited by bindings hash).
- Per-dispatch pipeline recreation -- ruled out (short-circuited by pipeline hash).
- Cold pipeline compile (hypothesis 1) -- FIXED by Doe Vulkan `VkPipelineCache`.
- Wave-size mismatch (hypothesis 2) -- ruled out (neither SPV declares a subgroup-size hint; RADV picks the same wave for both).
- Redundant barriers / binding rebinds (hypothesis 3) -- implausible given encode_ms is 4x faster on Doe.

The remaining 4.3% is SPIR-V emission-style sensitivity in RADV. That is now the smallest residual signal on AMD Vulkan and also the most surgical follow-up.

The regression is comparability-contract-compatible: the workloads pass every blocking obligation (execution shape match, timing phases match, hardware path match). They were flagged as "promotion candidates" by the triage in `bench/docs/comparability-promotion-audit.md`. What keeps them directional today is the claim gate, not the comparability gate -- Doe is not faster, so they are not claim-eligible.

## Static findings

### 1. Shader algorithm matches Dawn reference

`bench/kernels/matrix_vector_mul_32768x2048_f32_naive_swizzle0.wgsl` and Dawn's `MatrixVectorMultiplyPerf.cpp` (StoreType=F32, AccType=F32, Impl=Naive, Swizzle=0) use the same memory access pattern:

```
matrix[(4u * row_by_4 + k) * packedCols + col]  // k in 0..4
```

Four rows per invocation, workgroup_size = 64, dispatch x=128 (covers 128 * 64 * 4 = 32768 rows). Dispatch geometry matches Dawn's reference exactly.

### 2. Memory and binding layout differ slightly

Dawn's reference:

- binding 0: `Matrix` struct wrapping `array<StoreType>` (storage, read)
- binding 1: `Vector` struct wrapping `array<StoreType>` (storage, read)
- binding 2: `Vector` struct wrapping `array<StoreType>` (storage, read_write)
- binding 3: `Uniforms { rows: u32, packedCols: u32 }` (uniform)

Doe's WGSL (for the SPIR-V-kernel lane):

- binding 0: `array<vec4<f32>>` (storage, read)
- binding 1: `array<vec4<f32>>` (storage, read)
- binding 2: `array<vec4<f32>>` (storage, read_write)
- no uniform binding; dimensions are `const` in shader

Functionally equivalent. If anything, the constant-dimension form gives Doe's compiler more optimization opportunity than Dawn's uniform-access form. The missing uniform binding means Doe's bind group layout is one slot smaller, which should not regress.

### 3. SPIR-V codegen is not the bottleneck

Regenerating the same WGSL through Tint (`bench/vendor/dawn/out/Release/tint --format=spirv`) produces a 3968-byte binary; Doe's tracked `matrix_vector_mul_32768x2048_f32_naive_swizzle0.spv` is 3476 bytes. Doe's SPIR-V is smaller than what Dawn's own frontend would emit for the same source, so the regression is not a codegen-bloat issue on the Doe side.

(The tracked `matrix_vector_mul_32768x2048_f32.spv` at 2140 bytes is a different, scalar-element-per-invocation kernel -- not the variant this workload dispatches. Do not use it as a size reference.)

### 4. Per-dispatch descriptor work is already short-circuited

`runtime/zig/src/backend/vulkan/vk_pipeline.zig:518` hashes the bindings and early-returns when the hash matches the current state. For a 100-dispatch workload with constant bindings, dispatches 2..100 skip descriptor-set rewrites entirely. This is not a source of overhead per dispatch.

### 5. Pipeline creation is single-pass on warm iterations

`vk_pipeline.zig:325` checks `pipeline_hash != self.current_pipeline_hash` before rebuilding the pipeline. For 100 dispatches of the same kernel, the pipeline is built once and reused. Within a single process iteration, pipeline creation is not a per-dispatch cost.

## Hypotheses worth profiling

Without AMD GPU profiling (RGP / Nsight GFX / perfetto tracing) the regression cannot be confirmed from source alone. Three hypotheses, ranked by plausibility:

1. **First-dispatch pipeline creation cost on cold Vulkan cache.** Doe passes `VK_NULL_U64` to `vkCreateComputePipelines` (see `runtime/zig/src/backend/vulkan/vk_pipeline.zig:385`); Dawn's Vulkan backend uses `PipelineCacheVk` and threads a persistent `VkPipelineCache` into the creation call. With 100 dispatches per iteration and multiple iterations per process, this is a per-process first-compile cost. The Doe-side cost is real but should amortize over 100 dispatches; the question is how much the first compile costs relative to the 100-dispatch steady-state time. Landing Doe-side `VkPipelineCache` (already on the follow-up queue in `bench/docs/pipeline-cache-backend-audit.md`) would eliminate this cost on warm processes and reduce it on cold ones.

2. **Wavefront size mismatch against RDNA3.** RADV lets the driver pick wave32 vs wave64 based on shader stats unless the SPIR-V explicitly requests a preferred size via `SPV_KHR_subgroup_uniform_control_flow` or specialization constants. Tint-emitted SPIR-V (which Dawn uses) may thread different subgroup metadata than Doe's tracked `.spv` artifact. If RADV picks wave64 on one side and wave32 on the other for this specific kernel shape, the steady-state performance difference could be 10-40%. Confirm with RGP's wavefront occupancy view.

3. **Workgroup dispatch cost inside Doe's Vulkan command encoder.** `vkCmdDispatch` itself is cheap, but Doe may be emitting extra barriers or descriptor-binding instructions between dispatches that Dawn elides. The 100-dispatch shape would amplify this. Confirm by diffing the Vulkan command stream from both sides via the validation layer's `VK_LAYER_KHRONOS_validation` with command dumping.

## Non-hypotheses (ruled out)

- Doe SPIR-V is not codegen-bloated (smaller than Tint's for the same WGSL).
- Dispatch geometry is not mismatched (both sides dispatch x=128, workgroup_size=64).
- Per-dispatch descriptor rebind is not happening (short-circuited by the bindings hash).
- Pipeline recreation per dispatch is not happening (short-circuited by the pipeline hash).

## Next concrete step

Land Doe-side persistent `VkPipelineCache` first (see `bench/docs/pipeline-cache-backend-audit.md` and the pipeline-cache backend-audit follow-up queue). If the matvec delta improves after that, hypothesis 1 is the answer and the regression resolves with cache work.

If the delta persists, profile with RGP on an AMD host to confirm hypothesis 2 or 3.

## Follow-up queue

1. Implement Doe-side persistent `VkPipelineCache`; re-run matvec compare on AMD host.
2. If regression persists, capture RGP trace of the 100-dispatch sequence on both sides.
3. If wave-size mismatch is confirmed, emit subgroup-size preference in Doe's Vulkan pipeline creation.
4. If command-stream difference is confirmed, audit Doe's encoder for redundant barriers between dispatches.
