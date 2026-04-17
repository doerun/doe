# Pipeline-cache contribution lane

Audience: engineers producing cache-contribution evidence for a single backend, or reading status entries that cite the lane.

## What this lane is

A Doe-vs-Doe comparison on identical hardware and workloads where the only intentional difference is the pipeline-cache state:

- baseline: Doe with `--no-pipeline-cache` -> `trace_meta.pipelineCache.state="disabled" reason="cli-flag"`
- comparison: Doe with the pipeline cache active -> `trace_meta.pipelineCache.state="enabled" reason="default"`

The delta isolates the contribution of the persistent pipeline cache to Doe's measured performance. It is a diagnostic lane, not a Doe-vs-Dawn claim lane.

## What this lane is NOT

- Not a Doe-vs-Dawn comparison. It measures Doe's own cache contribution, not relative performance against an incumbent.
- Not interchangeable with "cold vs warm" package or plan lanes. Those sweep many cache kinds (file system, OS page cache, driver JIT state, CPU predictor state, pipeline cache); this lane toggles one axis only.
- Not a claim-grade surface. There is no comparability obligation between "Doe cached" and "Doe uncached"; the two sides are intentionally the same system in two configurations.

## Per-backend applicability

| Backend | Lane available | Executor pairing today |
| --- | --- | --- |
| Apple Metal | Yes | `doe_direct_metal` (cache off) vs `doe_direct_metal_cache` (cache on). Both templates in `bench/native_compare_modules/executor_registry.py`. |
| AMD Vulkan | No -- Doe does not yet implement persistent `VkPipelineCache` (see `bench/docs/pipeline-cache-backend-audit.md`). Lane lands once Doe Vulkan caching lands. |
| Local D3D12 | No -- Doe does not yet populate `CachedPSO`. Lane lands once Doe D3D12 caching lands. |

## What the lane actually measures

The pipeline cache sits between backend IR (MSL / SPIR-V / DXIL) and the driver's final GPU ISA + PSO object. It does not cover WGSL parsing or Tint translation. The delta this lane produces therefore attributes to:

1. driver-level shader compile (backend IR -> GPU ISA)
2. pipeline state object finalization (shader + root signature + binding layout + raster state for graphics)

The delta does not attribute to:

- WGSL parsing and validation
- Tint translation to backend IR
- runtime dispatch / execute
- descriptor set updates / per-dispatch state

Where the delta lands in the timing phases depends on the workload shape:

- workloads that create pipelines only in setup (most compute workloads, most inference workloads): delta lands in `setup_ns`; main-phase `executionTotalNs` is not affected beyond a small PSO-lookup cost
- workloads that create pipelines inside the timed loop (`pipeline_compile_stress`, async pipeline diagnostics): delta lands in the main execution phase directly
- pure upload / copy workloads: no pipeline creation, so the lane's delta should be at noise floor; any non-zero delta is a signal of unrelated state

## How to read the artifact

Both compare-report JSONs from this lane carry `pipelineCache.state` in both participants' `runtimeIdentity` blocks. The difference in `state` is the signature of the lane:

- baseline `left.runtimeIdentity.pipelineCache.state = "disabled"`, reason `"cli-flag"`
- comparison `right.runtimeIdentity.pipelineCache.state = "enabled"`, reason `"default"`

Any other lane shape -- both sides disabled, both sides enabled, asymmetric reasons -- is not a cache-contribution artifact and should be reclassified.

## Relationship to the Doe-vs-Dawn fair-cold and fair-warm lanes

| Lane | Baseline side | Comparison side | Claim surface |
| --- | --- | --- | --- |
| Cache-contribution (this doc) | Doe cache off | Doe cache on | diagnostic |
| Doe-vs-Dawn fair-cold (current Metal default) | Doe cache off | Dawn cache off | claim-eligible |
| Doe-vs-Dawn fair-warm (future Metal, once Dawn shim lands) | Doe cache on | Dawn cache on | claim-eligible |

The cache-contribution lane is the internal measurement that justifies the step from the fair-cold to the fair-warm lane: if the contribution is non-trivial on the workload class that matters for a claim, the fair-warm lane is worth landing. If the contribution is zero on the target workload class, the fair-warm lane adds no evidence and the fair-cold lane is the terminal Doe-vs-Dawn surface for that class.

## When to run this lane

- **Scoping a new Doe-vs-Dawn fair-warm lane**: measure the cache contribution first; it upper-bounds the delta the fair-warm lane can expose vs fair-cold.
- **Regressing a Doe-cache code change**: compare the same workload under the lane before and after the change; a regression in the cached-side p50 that exceeds a threshold flags a PSO-cache-hit-rate regression.
- **Explaining a surprising Doe-vs-Dawn delta**: if Doe appears unexpectedly fast on a workload, this lane tells you how much of that delta is cache-attributable.

## What this lane does not do

- Does not validate the cache's correctness. Cache hit returning a stale binary is still a correctness question; the lane only measures wall-time.
- Does not measure cross-process cache reuse. Both sides run in-process; the cache is warmed once per side, not shared.
- Does not produce a claim report. The artifact is a compare-report only.

## Follow-up queue

- Add a promoted-compare-catalog entry for the Metal cache-contribution lane once the executor templates and workload cohort scope stabilize.
- Extend the lane to Vulkan and D3D12 once Doe-side caching lands on those backends.
- Decide whether the lane needs its own config-template shape distinct from `compare.config.apple.metal.*` or whether a lane-override knob on the existing Metal compare configs is sufficient.
