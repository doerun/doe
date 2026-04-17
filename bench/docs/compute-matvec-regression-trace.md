# `compute_matvec_32768x2048_f32` regression trace

Audience: runtime engineers investigating why Doe is slower than Dawn on the matrix-vector multiply benchmark on AMD Vulkan.

## Observed delta

From `bench/out/amd-vulkan/explore/20260412T161500Z/compute_matvec_32768x2048_f32.compare.json`:

| Variant | Doe vs Dawn p50 delta |
| --- | --- |
| `compute_matvec_32768x2048_f32` (naive swizzle0) | **-38.62%** |
| `compute_matvec_32768x2048_f32_swizzle1` | **-3.87%** |
| `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` | **+11.45%** |

Doe is slower on two of three variants on this board. The "naive swizzle0" variant is the most worrying -- a 38% gap in what should be Doe's strong area (compute-heavy dispatch, cache-irrelevant workload).

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
