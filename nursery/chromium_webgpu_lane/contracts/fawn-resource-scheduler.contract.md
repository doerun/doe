# fawn_resource_scheduler Contract (Draft)

## Status

`draft`

## Goal

Define config-driven, deterministic resource pooling and submit-cadence behavior for Chromium lane modules running through Fawn.

## Ownership Boundary

Owns:

1. Buffer/texture pool policy for contract-covered modules.
2. Submit cadence policy selection from explicit config.
3. Resource pressure and eviction telemetry.

Does not own:

1. Cross-process browser scheduling policy.
2. Non-contract resource managers.
3. Hidden adaptive heuristics without config declaration.

## Input Contract (Candidate)

1. `resourceRequest[]`
   - type (`buffer|texture`)
   - size/format/usage
2. `workloadContext`
   - module id
   - operation class
3. `schedulerPolicy`
   - pool limits
   - submit cadence mode
   - eviction policy mode
4. `profile`
   - adapter/driver metadata

## Output Contract (Candidate)

1. `allocationResult[]`
   - allocated/reused resource identifiers
2. `poolStats`
   - hit/miss/eviction counts
   - high-water marks
3. `submitStats`
   - submit count
   - cadence mode used
4. `fallbackStats`
   - fallback count and reason codes
5. `traceLink`
   - module and hash anchors

## Failure/Fallback Taxonomy (Draft)

1. `pool_limit_exceeded`
2. `usage_mode_unsupported`
3. `profile_policy_missing`
4. `cadence_policy_invalid`
5. `determinism_guard_triggered`

## Determinism Rules

1. Policy selection must come from config, not hidden branching.
2. Resource reuse/eviction order must be deterministic for fixed input sequence.
3. Fallback and pressure decisions must emit typed reason codes.

## Gates

Blocking:

1. Schema gate for scheduler artifacts.
2. Correctness gate for policy application and deterministic outcomes.
3. Trace gate for resource event sequencing and hash continuity.

Advisory:

1. Performance gate for pool efficiency and cadence outcomes.

## KPI Candidates

1. Pool hit-rate trend by workload class.
2. Eviction rate and high-water trends.
3. Submit cadence stability by profile.
4. Tail-latency trend under fixed policy settings.

## Promotion Preconditions

1. Policy schema promoted to `fawn/config`.
2. Determinism tests for allocation/eviction pass.
3. Fallback taxonomy and metrics included in run artifacts.
