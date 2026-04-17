# Comparability promotion audit

Audience: engineers growing Doe's claim-grade breadth across backends.

## Headline

Breadth on AMD Vulkan and Local D3D12 is not bottlenecked by runtime quality. It is bottlenecked by a process gap: most workloads in those catalogs are marked `comparable: false` with no stated reason.

## Cross-backend maturity snapshot

Data pulled from the tracked workload catalogs on 2026-04-17:

| Backend | Total workloads | `comparable=true` | `governed` cohort | Directional (no reason stated) | Directional (reason stated) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Apple Metal | 96 | 38 | 27 | 26 | 32 |
| AMD Vulkan | 84 | 9 | 17 | 75 | 0 |
| Local D3D12 | 54 | 13 | 11 | 41 | 0 |

Source files:

- `bench/workloads/workloads.apple.metal.json`
- `bench/workloads/workloads.amd.vulkan.json`
- `bench/workloads/workloads.local.d3d12.json`

## What this means

The `comparable` flag on a workload is a *contract*: it declares that both Doe and Dawn can execute this workload with matching dispatch counts, matching timing-phase coverage, matching hardware-path, and no material path asymmetry. The comparability gate reads that flag and refuses to produce `comparable=true` output for workloads whose contract says `comparable=false`, regardless of what the runtime actually did.

On Apple Metal, 38/96 workloads have cleared this contract bar. Directional workloads on Metal have stated reasons on 32/58 rows -- someone audited them, decided they cannot be compared apples-to-apples today, and documented why.

On AMD Vulkan, 9/84 workloads have cleared the bar. The other 75 are all marked directional **with no stated reason**. On Local D3D12, 13/54 are cleared and 41 directional rows are similarly empty.

This is not evidence of runtime failure. The `explore` corpus runs on both backends show Doe and Dawn both executing the full catalog with concrete timing numbers. The `comparable=false` contract is just the absence of an audit, not a verdict on the execution.

## What a promotion audit looks like

For each directional workload, the audit decides between two outcomes:

1. **Promote to `comparable=true`.** Requires verifying on the latest `explore` artifact:
   - both sides report the same `executionDispatchCount`
   - both sides report the same `executionRowCount`
   - both sides report non-trivial timing in the same phases (setup, encode, submit_wait)
   - no hardware-path asymmetry on either side (or the asymmetry is auto-disclosed via `pathAsymmetry: true` + note)
   - timing source and timing class match on both sides
   - the workload is a meaningful product surface (not a synthetic stressor that doesn't translate to user-visible performance)
2. **Keep as directional with a stated reason.** Requires writing a short `directionalReason` on the workload entry explaining what specifically blocks comparability (missing feature on one side, different dispatch semantics, known driver quirk that is out of scope, etc.). This produces an auditable record even when promotion is rejected.

Either outcome is progress. Both require a per-workload decision; there is no bulk path to breadth.

## Why this matters for "Doe faster than Dawn across all boards"

Current released-claimable evidence per backend:

- Apple Metal: 38 comparable rows (broad claim base); G18 push disabled pipeline cache on both sides for fair-cold, 4 of 7 cache-asymmetric compute rows recovered as strict claimable on 2026-04-16.
- AMD Vulkan: 9 comparable rows; latest release compare artifact is 4 `upload_write_buffer_*` rows at +27 to +97% Doe. No comparable compute or render coverage today.
- Local D3D12: 13 comparable rows; Windows host required for runtime-backed evidence.

The headline claim "Doe is faster than Dawn across all boards" is supported today by:

- 4 upload-class workloads on AMD Vulkan
- a handful of upload/compute workloads on Apple Metal (broader once the 3 remaining matvec re-runs land)
- contract-only on D3D12 pending Windows runtime

That is narrower than it looks. The directional corpus on Vulkan and D3D12 is where the breadth lives, and it is dormant until the promotion audit runs.

## First-pass promotion candidates on AMD Vulkan

Cross-referencing the directional catalog against the latest `explore` compare at `bench/out/amd-vulkan/explore/20260412T161500Z/`, the rows where both sides appear to execute with reasonable timing symmetry (heuristic, not audit) include:

- `compute_workgroup_atomic_1024` -- Doe +48.35% over Dawn
- `compute_workgroup_non_atomic_1024` -- Doe +47.21%
- `compute_concurrent_execution_single` -- Doe +14.92%
- `pipeline_compile_stress` -- Doe +48.25% (cache-relevant)
- `compute_zero_initialize_workgroup_memory_256` -- Doe +99.99% (likely needs shape audit; delta saturating on 100 is suspicious)
- `render_bundle_dynamic_pipeline_bindings_200k` -- Doe +65.50%
- `render_draw_redundant_pipeline_bindings_200k` -- Doe +26.00%
- `texture_sampler_write_query_destroy_500` -- Doe +98.78% (needs shape audit)

Rows where Doe is behind or marginal, which deserve either audit or runtime-engineering work before any promotion:

- `compute_matvec_32768x2048_f32` -- Doe **-38.62%** (slower)
- `compute_matvec_32768x2048_f32_swizzle1` -- Doe **-3.87%** (slower)
- `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` -- Doe +11.45%

The matvec regression is particularly worth tracing: it is Doe's natural strong area (compute-heavy, cache-irrelevant) and should not be negative. That is a runtime-engineering lead, not a contract issue.

## Scope of the promotion work

Roughly sized per backend, assuming the heuristic-symmetric rows audit in about 10-15 minutes each and the shape-audit-needed rows take longer:

- AMD Vulkan: ~30-40 engineer-hours to triage the 75 directional rows, probably ~25 promotable, ~50 staying directional with stated reasons.
- Local D3D12: ~20-25 engineer-hours to triage the 41 directional rows, bottlenecked by a Windows host for runtime validation.
- Apple Metal: ~10 engineer-hours to fill in the 26 directional rows with empty reasons (contract-only, no runtime work).

This is the largest single-lever "Doe faster across all boards" breadth work available today on Linux.

## What this audit did not do

- Did not promote any workload. The promotion decision per row is still an explicit engineer step; this document only quantifies the gap.
- Did not investigate the `compute_matvec_*` regression. That is a runtime follow-up, not a contract follow-up.
- Did not verify the `explore` artifact's comparability heuristics against the full gate stack. The listed first-pass candidates are starting points, not pre-cleared promotions.

## Follow-up queue

1. Run the full promotion audit on AMD Vulkan starting with the listed first-pass candidates.
2. Trace the `compute_matvec_32768x2048_f32` regression -- identify whether the bottleneck is dispatch geometry, memory layout, or instruction scheduling, and address runtime-side.
3. Run the promotion audit on Local D3D12 in parallel when a Windows host is available.
4. Fill the 26 Apple Metal directional rows with stated reasons (contract-only cleanup).
