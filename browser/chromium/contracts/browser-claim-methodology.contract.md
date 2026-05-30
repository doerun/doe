# Browser claim methodology contract

## Status

`draft`

## Goal

Define the conditions required before Chromium WebGPU evidence can move from
diagnostic Track A output to a claimable Dawn-vs-Doe browser claim lane.

This contract applies to browser artifacts produced by:

1. `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
2. `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
3. `bench/browser/browser_gate.py`

## Claim boundary

Browser claim language is allowed only when all required artifacts prove:

1. the runtime mode is forced rather than auto-selected,
2. hidden fallback is disabled,
3. runtime identity is emitted for every mode,
4. the Doe runtime artifact hash is present for Doe mode,
5. Dawn and Doe execute the same required browser rows,
6. required browser rows have zero required failures,
7. timing scope and comparability class are explicit,
8. adapter identity is emitted for every mode with an available adapter,
9. shader compiler identity is emitted for every mode,
10. workload identity is emitted for every browser report,
11. per-mode trace hash fields are emitted,
12. report, summary, check, and gate artifacts are hash-linked.

Until those conditions are true, browser output remains diagnostic.

## Required runtime-selection fields

Every per-mode browser artifact must emit:

1. `selectionMode`
   - expected values: `dawn` or `doe` for forced claim lanes.
2. `selectedRuntime`
   - expected values: `dawn` or `doe`.
3. `forcedMode`
   - must match the mode being tested.
4. `fallbackApplied`
   - must be `false` for forced claim lanes.
5. `fallbackReasonCode`
   - must be empty when `fallbackApplied=false`.
6. `hiddenFallbackAllowed`
   - must be `false` for claim lanes.
7. `selectorVersion`
   - non-empty selector contract version.
8. `artifactIdentity`
   - `browserExecutablePath`
   - `browserExecutableSha256`
   - `dawnRuntimePath`
   - `dawnRuntimeSha256`
   - `doeLibPath` for Doe mode
   - `doeLibSha256` for Doe mode
9. `launchArgsHash`
   - hash of the launch arguments used for the mode.

The current selector contract source is
[`runtime-selector-and-fallback.contract.md`](./runtime-selector-and-fallback.contract.md).

## Forced-mode policy

For claim lanes:

1. Dawn mode must launch with an explicit Dawn runtime selection.
2. Doe mode must launch with an explicit Doe runtime selection.
3. Forced Doe initialization failure is a failed Doe run, not a Dawn fallback.
4. Auto mode output can be diagnostic but cannot be claimable.
5. Fallback reasons must use the runtime-selector taxonomy when fallback is
   allowed in diagnostic lanes.

## Required artifacts

A claim-candidate browser gate must produce:

1. smoke report:
   - `dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
2. layered report:
   - `dawn-vs-doe.browser-layered.superset.diagnostic.json`
3. layered check:
   - `dawn-vs-doe.browser-layered.superset.check.json`
4. layered summary:
   - `dawn-vs-doe.browser-layered.superset.summary.json`
5. browser gate report:
   - `bench/out/browser-promotion/<stamp>/browser_gate.json`
6. run manifest sidecar from `bench.lib.output_paths`

The file names may continue to say `diagnostic` until a formal browser claim
lane is added. The promotion gate decides whether those diagnostics satisfy a
claim-candidate contract.

## Gate requirements

The promoted browser gate must fail when:

1. any mode lacks a `runtimeSelection` object,
2. any mode lacks `dawnRuntimeSha256`,
3. Doe mode lacks `doeLibSha256`,
4. Dawn mode carries a Doe library identity,
5. `fallbackApplied=true` in a forced claim-candidate run,
6. `hiddenFallbackAllowed=true`,
7. launch argument hash is missing,
8. adapter identity is missing for an available adapter,
9. shader compiler identity is missing,
10. workload identity is missing,
11. per-mode trace hash fields are missing,
12. required smoke checks fail,
13. required layered rows fail,
14. promotion approvals are missing when required.

## Non-claims

This contract does not claim:

1. Doe has replaced Chromium WebGPU.
2. Doe is faster than Dawn globally.
3. browser-wrapper execution proves Doe runtime execution.
4. diagnostic browser-layered output is equivalent to strict L0 runtime
   benchmark output.

## Promotion path

The next promotion step is a formal browser claim lane that changes report
classification only after this contract, the selector contract, and the
benchmark-superset contract all pass under the promoted browser gate.
