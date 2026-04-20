# Package and browser ORT fairness audit

Audience: Doe benchmark operators evaluating Node, Bun, and browser ORT WebGPU comparisons.

## Scope

This audit covers the repo-only ORT WebGPU compare lanes under `bench/native-compare/` and their executor ids in `bench/native_compare_modules/executor_registry.py`:

- Node package lanes comparing `tjs_ort_node_doe` with `tjs_ort_node_webgpu_package`;
- Bun package lanes comparing `tjs_ort_bun_doe` with `tjs_ort_bun_webgpu_package`;
- browser lanes comparing `browser_ort_webgpu_doe` with `browser_ort_webgpu_dawn`.

These are not public `packages/doe-gpu/` contract claims unless a promoted artifact and claim report says so.

## Findings

The current package and browser ORT lanes are narrower than native Apple Metal Dawn-vs-Doe lanes. They compare provider stacks through the host runtime harness and use process-wall timing where the harness contract requires whole-process or host-mediated measurements. The existing artifacts and configs should be treated as local, host-specific evidence unless a claim report passes strict comparability, report-level comparability coherence, structural equivalence, and the claimability gate.

No package or browser ORT lane is allowed to inherit the Apple Metal pipeline archive advantage implicitly. Native Apple Metal default executors now disable the archive by default; package/browser lanes that reach native Metal through Doe must still rely on emitted runtime telemetry and the compare report to prove cache state before a claim can be accepted.

## Contract exemptions by surface

The canonical comparability contract lives in `bench/native_compare_modules/` (`comparability.py`, `comparability_runtime.py`, `compare_assessment.py`, `claimability.py`). Not every compare surface enforces every layer of that contract. The table below records which layer applies to which surface and the reason for any exemption. Any new compare surface MUST be added to this table before promotion.

| Contract layer | Native GPU (`bench/cli.py compare`) | Package (Node/Bun) | Browser | Ad-hoc CPU-only (Tint compilation) | Ad-hoc GPU (subgroup kernels) |
| --- | --- | --- | --- | --- | --- |
| Comparability mode (`strict` / `warn` / `off`) | Required; `strict` for release lanes | Required | Required | N/A — no native backend lanes | N/A — construction-validated parity |
| Report-level comparability coherence | Required, default-on in `run_blocking_gates.py` | Required | Required | N/A — emits `.claim.json` directly | N/A — emits `.claim.json` directly |
| Execution-shape parity (dispatch, row, success counts) | Required (CLAUDE.md non-negotiable #10) | Required if the dispatch bridge exposes counts; otherwise flagged in residual limits | Required via Playwright artifacts | Exempt — compilation has no GPU dispatch; parity is "compiled once, compared once" | Exempt — dispatch count is hardcoded to 100 by script contract (`compare_subgroup_kernels.py`) |
| Phase-asymmetry gate (all-zero-vs-any-material) | Required for every comparable row | Required when both sides report GPU timestamps; see residual limits | Required when both sides report GPU timestamps | N/A — single-scope wall-time | Exempt — single GPU-timestamp scope on both sides |
| Two-tier sample-floor (`minTimedSamples` / `smokeMinTimedSamples`) | Required via `comparability_coherence` | Required | Required | Required via `bench/lib/adhoc_claim_gating` (local=7, release=15) | Required via `bench/lib/adhoc_claim_gating` |
| Required positive percentiles (p50 / p95 / p99) | Required via `claimability.py` | Required | Required | Required via `adhoc_claim_gating` | Required via `adhoc_claim_gating` |
| Timer-overhead budget | Claimability-scoped | Claimability-scoped | Claimability-scoped | Gated via `ClaimPolicy.timer_overhead_budget_percent` | Gated via `ClaimPolicy.timer_overhead_budget_percent` |
| Path-asymmetry (`pathAsymmetry` / note) | Auto-disclosed via `metal_pipeline_cache_manifest` on Apple Metal; required on UMA-upload | Required if surface inherits a Doe-side cache | Required if surface inherits a Doe-side cache | N/A — CPU-only compilation | Required — subgroup script must declare if it probes a cached kernel |

## Residual limits

This audit closes the Linux-side contract review. It does not substitute for new Mac hardware evidence, and it does not promote Node, Bun, or browser ORT results to release-grade claims by itself. Release evidence still needs fresh artifacts from the target host, the configured sample floor, positive tail checks, and the blocking gates that apply to the selected surface.

Specific residual limits to watch on package and browser surfaces:

1. Phase-asymmetry gating assumes both sides report non-trivial GPU-timestamp samples. When a host falls back to pure wall-time timing on one side, the phase-asymmetry gate has no signal to fire on; the comparability coherence gate's sample-floor is the only line of defense. Any wall-time-only package or browser comparison MUST be marked `diagnostic` until both sides produce GPU-timestamp evidence.
2. Execution-shape parity depends on the JavaScript dispatch bridge surfacing dispatch-count and row-count into the run receipt's `traceMeta`. The browser ORT Playwright bridge emits timed-iteration WebGPU dispatch counts; package bridges that do not surface those fields must stay diagnostic until extended.
3. Ad-hoc GPU-execution scripts (the `subgroup kernels` family is the current example) pass structural parity by construction — both sides dispatch an equal fixed count and execute the same WGSL. New ad-hoc GPU scripts that do not carry this construction guarantee MUST route through `bench/cli.py compare` instead of emitting their own `.claim.json`, so the structural-equivalence gate applies.
