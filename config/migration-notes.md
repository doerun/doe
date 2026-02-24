# Config Migration Notes

## 2026-02-22

### `benchmark-methodology-thresholds` contract enforcement

- `config/benchmark-methodology-thresholds.schema.json` and
  `config/benchmark-methodology-thresholds.json` are now enforced inputs for
  benchmark comparability/claimability threshold selection.
- `bench/compare_dawn_vs_fawn.py` now reads:
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
