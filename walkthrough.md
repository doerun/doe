# Fawn vs Dawn (Local Metal Extended Comparable) Walkthrough

## Artifacts audited

- Canonical compare report:
  - `bench/out/20260228T210540Z/metal.macos.final.local.comparable.latest.json`
- Run manifest:
  - `bench/out/20260228T210540Z/run_manifest.json`
- Generated HTML view:
  - `bench/out/metal.macos.final.local.comparable.latest.html`

## Run outcome

- `comparisonStatus`: `comparable`
- `claimStatus`: `diagnostic`
- `nonComparableCount`: `0`
- `nonClaimableCount`: `5`

Interpretation: comparability obligations passed; the run is diagnostic because 5 workloads failed local claimability tails (`p50` and/or `p95` not positive for Doe).

## Where Dawn is faster (p50)

- `upload_write_buffer_1kb`: `-91.37%` (`Doe p50=0.117302 ms`, `Dawn p50=0.010118 ms`)
- `upload_write_buffer_64kb`: `-84.86%` (`Doe p50=0.085104 ms`, `Dawn p50=0.012881 ms`)
- `texture_sampler_write_query_destroy`: `-39.57%` (`Doe p50=0.018192 ms`, `Dawn p50=0.010993 ms`)
- `render_draw_throughput_baseline`: `-1.10%` (`Doe p50=0.0002395 ms`, `Dawn p50=0.0002369 ms`)

## Where Doe is faster (p50)

17 of 21 workloads are positive on p50 in this run, including:

- `upload_write_buffer_1mb`: `+25.19%`
- `upload_write_buffer_4mb`: `+192.33%`
- `upload_write_buffer_16mb`: `+3041.04%`
- `render_bundle_dynamic_bindings`: `+27.01%` (but p95 is negative, so non-claimable)
- `texture_sampler_write_query_destroy_mip8`: `+51.46%`
- `render_uniform_buffer_update_writebuffer_partial_single`: `+1190.72%`
- `compute_concurrent_execution_single`: `+33406.73%`

Very large positive percentages mostly come from very small Doe absolute times on some macro/dispatch-style workloads (tiny denominator effects), not from a methodology failure in this run.

## What did not make sense (historical context)

This walkthrough captured a period where JSON/HTML delta formulas drifted.

- Current benchmark convention is now unified:
  - `((rightMs / leftMs) - 1) * 100` (positive => left/Doe faster)
- This walkthrough's legacy percentages were produced before that realignment.

## Merged interpretation of shortfalls (corrected)

1. Upload performance:
- It is accurate that upload path reliability/overhead remains an active tuning area (`submit-wait spikes`, `allocator churn` are explicitly tracked in `performance-strategy.md:90` and `performance-strategy.md:92`).
- But it is not accurate to summarize upload shortfall as `64kb, 1mb` in this run.
- In this run: `1kb` and `64kb` are slower for Doe; `1mb`, `4mb`, and `16mb` are faster for Doe.

2. Texture performance:
- It is not uniformly slower for Doe.
- `texture_sampler_write_query_destroy` is slower, but `..._mip8` and macro texture workload are faster.
- So the evidence suggests workload-shape sensitivity, not a single blanket texture-runtime regression.

3. Render and render-bundle:
- `render_draw_throughput_baseline` is near parity and slightly negative at p50.
- `render_bundle_dynamic_bindings` has positive p50 but negative p95 tail (instability), which explains claimability failure despite comparability success.

4. Correctness vs speed:
- No sample command failures were present in this completed run.
- The run is correctly classified as diagnostic due to claimability tails, not due to comparability or correctness gate failure.

## Practical conclusion

- There is no evidence in this artifact of a fatal runtime correctness break.
- The main actionable gaps are:
  - small-upload lanes (`1kb`, `64kb`),
  - one texture contract (`texture_sampler_write_query_destroy`),
  - one render-bundle tail (`render_bundle_dynamic_bindings` p95).
- Use the JSON report as source-of-truth until the HTML delta formula is aligned with compare-report semantics.
