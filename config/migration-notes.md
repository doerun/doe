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
