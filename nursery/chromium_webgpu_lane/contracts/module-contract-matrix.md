# Module Contract Matrix (Draft)

## Status

`draft`

## Purpose

Define one shared matrix for Track A and Track B module contracts:

1. exact request/response field sets to schema,
2. blocking/advisory gates per module,
3. staged rollout KPIs and promotion thresholds.

This matrix is intentionally strict so each module can ship independently with a kill switch.

## Shared Run Metadata (All Modules)

Required fields for every module run artifact:

1. `runId` (string)
2. `runTimestampUtc` (RFC3339 string)
3. `moduleId` (string)
4. `moduleVersion` (string)
5. `selectorVersion` (string, Track A required)
6. `selectionMode` (`dawn|fawn|auto`, Track A required)
7. `selectedRuntime` (`dawn|fawn`, Track A required)
8. `fallbackApplied` (boolean)
9. `fallbackReasonCode` (enum string, empty when none)
10. `profile.vendor` (string)
11. `profile.deviceFamily` (string)
12. `profile.api` (string)
13. `profile.driver` (string)
14. `artifactHash` (string)
15. `traceHashChainHead` (string)
16. `timingSource` (enum string)
17. `timingClass` (`diagnostic|strict_comparable|claim_candidate`)

## Track A Runtime Selector Matrix

### Input Contract

1. `mode` (`dawn|fawn|auto`)
2. `globalDisable` (boolean)
3. `forcedRuntime` (`none|dawn|fawn`)
4. `denylistProfileMatch` (boolean)
5. `requiredSymbolSurfacePresent` (boolean)
6. `requiredCapabilitiesPresent` (boolean)
7. `runtimeArtifactPath` (string)
8. `runtimeArtifactHash` (string)

### Output Contract

1. `selectedRuntime`
2. `fallbackApplied`
3. `fallbackReasonCode`
4. `selectionDecisionTrace[]`:
   - `checkName`
   - `checkResult`
   - `decisionOrder`

### Blocking Gates

1. Schema gate for selector fields.
2. Correctness gate for mode precedence and denylist behavior.
3. Trace gate for deterministic decision ordering.
4. Drop-in symbol gate for selected Fawn artifact.

### Advisory Gates

1. Session crash/hang trend.
2. Startup overhead trend.

### KPI Thresholds (Draft)

1. Crash/hang parity:
   - no statistically significant regression versus Dawn in staged matrix.
2. Selection determinism:
   - identical inputs produce identical `selectionDecisionTrace` in 100% of replayed runs.
3. Fallback fidelity:
   - 100% of forced-negative test cases map to expected reason code.

## Track B Module Matrix

## B1. `fawn_2d_sdf_renderer`

### Input Contract

1. `textRuns[]`:
   - `fontId`, `glyphIds[]`, `positions[]`, `subpixelMode`
2. `pathOps[]`:
   - `verb`, `points[]`, `windingRule`, `strokeStyle`
3. `paintState`:
   - `fill`, `stroke`, `blendMode`, `clipStack[]`, `transform`
4. `target`:
   - `width`, `height`, `format`, `sampleCount`

### Output Contract

1. `renderPassStats`:
   - `drawCount`, `dispatchCount`, `atlasMissCount`
2. `timingSpansNs`:
   - `setup`, `encode`, `submitWait`
3. `qualityFlags[]`
4. `fallbackCount`
5. `outputSurfaceId`

### Blocking Gates

1. Schema gate for request/response and quality flags.
2. Correctness gate for deterministic image hash on fixed fixtures.
3. Trace gate for pass ordering and hash-chain continuity.

### Advisory Gates

1. Verification obligations based on safety class.
2. Performance trend on raster-heavy workloads.

### KPI Thresholds (Draft)

1. Determinism: 100% stable output hash on fixed fixtures.
2. Fallback transparency: no untyped fallback events.
3. Performance: `p50` and `p95` non-negative versus Dawn baseline before claim mode.

## B2. `fawn_path_engine`

### Input Contract

1. `pathBatch[]`:
   - `pathId`, `segments[]`, `fillRule`, `strokeParams`
2. `clipMaskRequest`:
   - `maskFormat`, `clipBounds`
3. `qualityPolicy`:
   - `maxSegmentCount`, `selfIntersectPolicy`

### Output Contract

1. `pathResult[]`:
   - `pathId`, `renderMode` (`tessellate|sdf|cpu_fallback`)
2. `clipMaskSurfaceId`
3. `pathQualityFlags[]`
4. `fallbackReasonCounts{}`

### Blocking Gates

1. Schema gate for path request/response taxonomy.
2. Correctness gate for geometry fidelity fixtures.
3. Trace gate for selected render mode determinism.

### Advisory Gates

1. Performance trend on complex-geometry workloads.
2. Reliability trend for pathological inputs.

### KPI Thresholds (Draft)

1. Geometry correctness: no blocking fixture mismatches.
2. Deterministic mode selection: stable `renderMode` for identical inputs.
3. Fallback safety: unsupported geometry always emits typed reason.

## B3. `fawn_effects_pipeline`

### Input Contract

1. `effectGraph[]`:
   - ordered nodes (`blur|color_matrix|blend|mask|composite`)
2. `inputSurfaces[]`
3. `outputTarget`
4. `precisionPolicy`

### Output Contract

1. `nodeExecutionStats[]`:
   - `nodeId`, `execTimeNs`, `resourceBytes`
2. `outputSurfaceId`
3. `precisionDegradationFlags[]`
4. `fallbackReasonCounts{}`

### Blocking Gates

1. Schema gate for graph and node telemetry.
2. Correctness gate on golden-effects fixtures.
3. Trace gate for node order and deterministic graph execution.

### Advisory Gates

1. Performance trend by effect class.
2. Memory trend for transient allocations.

### KPI Thresholds (Draft)

1. Golden output fidelity: no blocking fixture deltas above policy.
2. Deterministic graph execution order in replay.
3. Claim mode only if strict comparability and positive `p50`/`p95` tails.

## B4. `fawn_compute_services`

### Input Contract

1. `serviceId`
2. `kernelId`
3. `buffers[]`:
   - `usage`, `size`, `accessMode`
4. `dispatchGeometry`
5. `normalizationDivisor`

### Output Contract

1. `kernelStatus`
2. `dispatchStats`
3. `timingSpansNs`
4. `fallbackReasonCode` (if any)

### Blocking Gates

1. Schema gate for service request/response.
2. Correctness gate for per-kernel fixture checks.
3. Trace gate for dispatch and hash-chain reproducibility.

### Advisory Gates

1. Performance trend on selected service kernels.
2. Reliability trend across adapter matrix.

### KPI Thresholds (Draft)

1. Kernel correctness pass rate at 100% for promoted kernels.
2. Strict comparability pass required for claimable comparisons.
3. No mixed-scope timing in claim mode.

## B5. `fawn_resource_scheduler`

### Input Contract

1. `resourceRequests[]`:
   - `resourceType`, `size`, `lifetimeClass`, `usageClass`
2. `submitPolicy`:
   - `maxInFlight`, `submitCadence`, `queueClass`
3. `adapterBudget`
4. `schedulerMode` (`deterministic|adaptive_profiled`)

### Output Contract

1. `allocations[]`:
   - `poolId`, `resourceId`, `bytesGranted`
2. `submitPlan[]`
3. `budgetPressureEvents[]`
4. `schedulerFallbackReasonCode` (if any)

### Blocking Gates

1. Schema gate for scheduler request/response fields.
2. Correctness gate for deterministic plan generation.
3. Trace gate for allocation/submit ordering.

### Advisory Gates

1. Memory efficiency trend.
2. Frame stutter trend for selected workloads.

### KPI Thresholds (Draft)

1. No deterministic-plan regressions in replay.
2. No hidden budget fallback; all fallback paths typed.
3. Claim lanes require strict comparability and reliability checks.

## Promotion Rules (All Modules)

1. No module exits nursery without schema + migration updates in same change.
2. No module exits nursery without explicit kill switch and rollback contract.
3. Each module must pass blocking gates independently before promotion.
4. Performance claims require claimable classification, never diagnostic-only output.
