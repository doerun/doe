# Config Migration Notes

## 2026-02-25

### Indexed P0 render comparability promotion

- `bench/vendor/dawn/src/dawn/tests/perf_tests/DrawCallPerf.cpp` now includes an
  indexed draw variant (`DynamicVertexBuffer_DrawIndexed`) in Dawn perf coverage.
- `bench/workloads.amd.vulkan.extended.json` restores
  `p0_render_multidraw_indexed_contract` to strict comparable:
  - `comparable=true`
  - `benchmarkClass=comparable`
  - `applesToApplesVetted=true`
- Dawn filter contracts now map indexed workloads to the indexed variant:
  - `bench/dawn_workload_map.amd.extended.json`
  - `bench/dawn_benchmark_adapter.py` autodiscovery patterns (`DynamicVertexBuffer_DrawIndexed`)
- strict apples-to-apples lanes now run indexed-vs-indexed for this contract.

### Directional comparability-candidate cohort contract

- `bench/workloads.amd.vulkan.extended.json` now supports optional workload field
  `comparabilityCandidate`:
  - `enabled` (bool)
  - `tier` (string)
  - `notes` (string)
- this field marks directional workloads that are isolated as likely parity-promotion
  targets; it does not change strict comparability status by itself.
- `bench/compare_dawn_vs_doe.py` now supports:
  - CLI: `--workload-cohort all|comparability-candidates`
  - config: `run.workloadCohort`
- cohort `comparability-candidates` is fail-fast gated to directional lanes and
  requires `includeNoncomparableWorkloads=true`.
- reports now record both:
  - top-level `comparabilityPolicy.workloadCohort`
  - per-workload `comparabilityCandidate` metadata.
- added directional preset for the current 8 candidate workloads:
  `bench/compare_dawn_vs_doe.config.amd.vulkan.comparability-candidates.directional.json`.

### Doe backend identity cutover (phase 1-3 completed)

- Backend runtime identity is now Doe-only across runtime-visible surfaces.
- Canonical artifacts are:
  - runtime binary: `doe-zig-runtime`
  - drop-in shared library: `libdoe_webgpu.so`
- Chromium Track-A runtime controls now use Doe names only:
  - selector value: `--use-webgpu-runtime=doe`
  - kill switch: `--disable-webgpu-doe`
  - runtime library path: `--doe-webgpu-library-path=<path>`
- Chromium GPU preference fields and mojom wiring were renamed to Doe equivalents:
  - `disable_webgpu_doe`
  - `doe_webgpu_library_path`
  - enum/runtime variants `kDoe`
- Legacy backend aliases (`fawn` runtime selector/backend library flag names) were removed.
- Doe-specific compare/report families now use `dawn-vs-doe` naming.

### Doe backend identity cleanup (phase 4 completed)

- Drop-in diagnostic helper exports are now Doe-named:
  - `doeWgpuDropinLastErrorCode()`
  - `doeWgpuDropinClearLastError()`
- Drop-in panic/error text now reports `doe drop-in ...` taxonomy.
- Runtime timestamp debug env flag is now Doe-named:
  - `DOE_WGPU_TIMESTAMP_DEBUG=1`
- Trace gate semantic-parity eligibility now matches Doe runtime module identity (`module` starts with `doe-`) and rejects non-Doe runtime module pairs in `required` mode.

## 2026-02-22

### `benchmark-methodology-thresholds` contract enforcement

- `config/benchmark-methodology-thresholds.schema.json` and
  `config/benchmark-methodology-thresholds.json` are now enforced inputs for
  benchmark comparability/claimability threshold selection.
- `bench/compare_dawn_vs_doe.py` now reads:
  - `timingSelection.minDispatchWindowNsWithoutEncode`
  - `timingSelection.minDispatchWindowCoveragePercentWithoutEncode`
  - `claimabilityDefaults.localMinTimedSamples`
  - `claimabilityDefaults.releaseMinTimedSamples`
- These replace hardcoded benchmark thresholds in code.

### `modules.json` status semantics refreshed

- Bumped `config/modules.json` `schemaVersion` from `2` to `3`.
- Updated module status values from `scaffolded` to `active` for current runtime posture.

### `quirks.schema` action contract tightened

- Bumped `config/quirks.schema.json` quirk `schemaVersion` from `1` to `2`.
- Tightened `action` from open object to a strict discriminated contract:
  - `use_temporary_buffer` requires `params.bufferAlignmentBytes` (`>= 1`)
  - `toggle` requires `params.toggle`
  - `no_op` requires only `kind` and rejects extra fields
- Parser/runtime now enforce the same strictness:
  - unknown quirk fields are rejected during JSON parse
  - legacy action aliases (`noop`, `alignmentBytes`, `alignment`, `name`, `toggle_name`) are no longer accepted
  - implicit fallback alignment is removed; alignment must be explicit in the quirk record
- Updated first-party quirk examples to `schemaVersion: 2`.

## 2026-02-23

### `webgpu-spec-coverage` status semantics expanded

- Updated `config/webgpu-spec-coverage.schema.json` to add `status: "tracked"`.
- `tracked` is used for spec-universe feature inventory entries that are explicitly covered as config/audit inventory contracts, but are not yet runtime-semantic implementations.
- Migrated Dawn feature-inventory rows in `config/webgpu-spec-coverage.json` from `planned` to `tracked` for entries sourced from `bench/vendor/dawn/src/dawn/dawn.json` feature inventory.

### `webgpu-spec-coverage` tracked inventory closure

- Closed remaining tracked/blocked feature inventory rows by promoting all `feature_*` entries to explicit implemented inventory contracts.
- Feature inventory implementation contract now requires:
  - Dawn feature-enum source (`bench/vendor/dawn/src/dawn/dawn.json` `feature name` values).
  - Zig runtime capability introspection path (`wgpuAdapterGetFeatures` / `wgpuDeviceGetFeatures` via `zig/src/wgpu_capability_runtime.zig`).
  - benchmark mapping contract via capability introspection workloads (`p1_capability_introspection_contract`, `p1_capability_introspection_macro_500`).
- Current closure totals in `config/webgpu-spec-coverage.json`:
  - `implemented=103`
  - `blocked=0`
  - `tracked=0`
  - `planned=0`

### Dawn autodiscovery map coverage for extended comparable matrix

- Extended `bench/dawn_benchmark_adapter.py` `AUTODISCOVER_WORKLOAD_PATTERNS` to cover all workload IDs in `bench/workloads.amd.vulkan.extended.json` (including `p0_*`, `p1_*`, `p2_*`, macro contracts, and added Dawn suites).
- This removes local strict-run failures caused by missing autodiscovery patterns for full39 execution passes.

### `substantiation-policy` contract introduced

- Added `config/substantiation-policy.schema.json` and `config/substantiation-policy.json`.
- The policy defines machine-checked release evidence minimums:
  - `minReports`
  - `minClaimableComparableReports`
  - `requiredComparisonStatus`
  - `requiredClaimStatus`
  - `minUniqueLeftProfiles`
  - optional `targetUniqueLeftProfiles`
- `bench/substantiation_gate.py` consumes this policy for repeated-window/report substantiation checks.
- `bench/schema_gate.py` now validates the substantiation policy contract as part of blocking schema checks.

## 2026-02-24

### Dispatch-window timing selection hardening

- `bench/compare_dawn_vs_doe_modules/timing_selection.py` now applies tiny dispatch-window rejection globally (not only submit-only/no-dispatch traces) when both are true:
  - dispatch window `< timingSelection.minDispatchWindowNsWithoutEncode`
  - dispatch-window coverage `< timingSelection.minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs`
- when rejected, timing selection falls back to `doe-execution-total-ns` and records `dispatchWindowSelectionRejected` metadata.

### AMD extended workload contract correction for concurrent execution

- `bench/workloads.amd.vulkan.extended.json` was updated to keep strict claim lanes apples-to-apples:
  - `surface_presentation_contract` is now directional-only (`comparable=false`)
  - added `concurrent_execution_single_contract` as the strict comparable mapping for Dawn `ConcurrentExecutionTest ... RunSingle`
- new command/kernel artifacts were added for the replacement comparable contract:
  - `examples/concurrent_execution_single_commands.json`
  - `bench/kernels/concurrent_execution_runsingle_u32.wgsl`
- `bench/dawn_workload_map.amd.extended.json` now includes filter mapping for `concurrent_execution_single_contract`.

### Apples-to-apples enforcement hardening

- `bench/workloads.amd.vulkan.extended.json` now reclassifies directional/proxy mappings as non-comparable (`comparable=false`, `benchmarkClass=directional`) for strict claim lanes.
- `bench/compare_dawn_vs_doe.py` now rejects workload contract entries that set `comparable=true` while:
  - description is directional (`description` starts with `Directional`)
  - comparability notes explicitly declare closest-proxy mapping (`closest draw-call throughput proxy`)
- strict comparable runs now fail fast when those contract invariants are violated.

### Upload ignore-first scope enforcement

- `bench/compare_dawn_vs_doe_modules/comparability.py` and `bench/compare_dawn_vs_doe_modules/claimability.py` now enforce ignore-first timing scope consistency:
  - `uploadIgnoreFirstAdjustedTimingSource` must resolve to `doe-execution-row-total-ns`
  - base and adjusted ignore-first canonical timing sources must match
- mixed-scope derived upload timings now fail strict comparability and claimability checks.

### Machine-checkable comparability obligations

- `bench/compare_dawn_vs_doe_modules/comparability.py` now emits machine-checkable obligation artifacts per workload in report field `comparability`:
  - `obligationSchemaVersion`
  - `obligations[]` entries (`id`, `blocking`, `applicable`, `passes`, `details`)
  - `blockingFailedObligations` / `advisoryFailedObligations`
- workload comparability is now computed from blocking-obligation failures (`blockingFailedObligations`), preserving legacy `reasons` as human-readable diagnostics.
- `bench/claim_gate.py` and `bench/check_full39_claim_readiness.py` now require valid comparability obligation artifacts and fail when blocking obligations fail in claim/comparable lanes.

### Comparability obligation contract + parity fixtures

- Added canonical obligation-ID contract:
  - `config/comparability-obligations.schema.json`
  - `config/comparability-obligations.json`
- Added comparability parity fixture contract and data:
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/comparability_obligation_fixtures.json`
- `bench/schema_gate.py` now validates both contracts as part of blocking schema checks.
- Added verification-lane parity gate:
  - `bench/comparability_obligation_parity_gate.py`
  - validates Python fixture evaluation (`evaluate_comparability_from_facts`) and Lean/Python obligation ID alignment.
- Added Lean parity fixture proofs:
  - `lean/Fawn/ComparabilityFixtures.lean`
  - compiled by `lean/check.sh`.
- `bench/claim_gate.py` now validates report obligation IDs against `config/comparability-obligations.json` (canonical ID contract) in addition to schema-version checks.
- `bench/run_blocking_gates.py` and release orchestrators now support `--with-comparability-parity-gate` to wire this verification step into automated gate runs.

### Report anti-staleness metadata

- `bench/compare_dawn_vs_doe.py` now emits workload contract metadata in reports:
  - `workloadContract.path`
  - `workloadContract.sha256`
- `bench/check_full39_claim_readiness.py` now verifies:
  - exact comparable workload ID set against current workload contract
  - workload contract hash match when report metadata is present

### Dawn filter-map fallback removal

- `bench/dawn_benchmark_adapter.py` no longer accepts implicit/default workload
  map fallback resolution for Dawn gtest filters.
- `--dawn-filter-map` now resolves only explicit `filters.<workload>` entries or
  explicit `--dawn-filter`; unresolved workloads fail fast.
- `bench/dawn_workload_map*.json` contract files were updated to remove
  `filters.default` fallback entries.

### Report conformance + workload-hash enforcement hardening

- `bench/claim_gate.py` now enforces canonical obligation contract IDs from
  `config/comparability-obligations.json` plus optional strict
  workload-contract hash/path and comparable workload ID-set checks.
- `bench/run_release_pipeline.py` and `bench/run_blocking_gates.py` now pass
  strict workload contract hash/ID requirements into claim-gate release lanes.
- `bench/build_baseline_dataset.py` and
  `bench/build_test_inventory_dashboard.py` now include only conformant compare
  reports (`schemaVersion=4`, canonical comparability obligations, and
  workload-contract hash/path consistency).
- `bench/report_conformance.py` was added as the shared conformance/hash
  validation module for report-ingestion tooling.

### Track B claim-row hash-link and rehearsal artifact enforcement

- `bench/compare_dawn_vs_doe.py` claim-row linkage fields are now validated by
  gate logic, not report-emission only:
  - per-workload `claimRowHash`
  - report-level `claimRowHashChain`
- `bench/report_conformance.py` now includes claim-row hash-link validation helpers:
  - validates chain continuity (`previousHash` -> `hash`)
  - recomputes row hashes deterministically from canonical JSON context
  - verifies context linkage to:
    - `workloadContract.sha256`
    - `configContract.sha256`
    - `benchmarkPolicy.sha256`
    - workload `traceMetaHashes` (`left`/`right`)
- `bench/claim_gate.py` now enforces those hash-link invariants and fails
  claim lanes when linkage is missing/invalid.
- `bench/claim_gate.py` now independently validates claim tails and floors for
  claimable release lanes:
  - per-workload timed sample floors
  - required positive deltas from policy (`p50/p95/p99` for release)
- Added `bench/build_claim_rehearsal_artifacts.py` to emit required
  machine-readable rehearsal artifacts from a compare report:
  - claim gate result
  - tail-health table
  - timing-invariant audit
  - contract-hash manifest
  - rehearsal manifest linking all artifact paths
- `bench/run_release_pipeline.py` now runs this artifact builder by default when
  `--with-claim-gate` is enabled (disable with
  `--no-with-claim-rehearsal-artifacts`).
- `bench/run_release_claim_windows.py` now forwards that release-pipeline
  rehearsal-artifact behavior per window by default.

### Claim cycle contract + rollback gate enforcement

- Added active cycle-lock contract and schema:
  - `config/claim-cycle.schema.json`
  - `config/claim-cycle.active.json`
- `bench/schema_gate.py` now validates the active cycle contract as a blocking schema target.
- Added `bench/cycle_gate.py` for claim-lane governance checks:
  - validates cycle contract hash locks against on-disk contracts
  - validates comparable/directional workload partition against active workload contract
  - validates claim report conformance and hash-link consistency
  - evaluates rollback criteria and artifact namespace policy
- `bench/run_release_pipeline.py` now runs `cycle_gate.py` by default when
  `--with-claim-gate` is enabled (disable only for diagnostics via
  `--no-with-cycle-gate`).
- `bench/run_release_claim_windows.py` now forwards cycle-gate controls per
  window by default.
