# Runtime Selector and Fallback Contract (Draft)

## Status

`draft`

## Goal

Define deterministic runtime selection for Chromium WebGPU execution:

1. `dawn` path.
2. `fawn` path.
3. `auto` policy path.

Ensure immediate fallback with explicit reasons and no hidden behavior switches.

## Scope

In scope:

1. Runtime selection controls.
2. Kill switch policy.
3. Adapter/profile denylist policy.
4. Fallback reason taxonomy.
5. Required observability fields.

Out of scope:

1. Browser process-model changes.
2. Non-WebGPU subsystem selection.
3. Implicit policy heuristics.

## Control Surfaces

Candidate control surfaces (precedence high -> low):

1. Emergency global kill switch.
2. Explicit command-line/runtime override (`dawn` or `fawn`).
3. Enterprise/policy override (if present in integration target).
4. Auto selection policy based on adapter/profile support.
5. Default baseline (`dawn`) when none provided.

## Selection Modes

1. `dawn`
   - force incumbent runtime.
2. `fawn`
   - force Fawn path.
3. `auto`
   - attempt Fawn only when all gating preconditions hold for active profile; otherwise fallback to Dawn with reason code.

## Auto Mode Preconditions (Draft)

All required:

1. Runtime artifact availability and load success.
2. Required symbol surface available.
3. Required capability checks pass.
4. Profile not denylisted.
5. No active emergency disable.

If any precondition fails, select `dawn` with explicit fallback reason.

## Fallback Reason Taxonomy (Draft)

1. `global_disable_active`
2. `runtime_artifact_missing`
3. `runtime_artifact_load_failed`
4. `symbol_surface_incomplete`
5. `profile_denylisted`
6. `capability_requirement_failed`
7. `runtime_health_degraded`
8. `explicit_operator_override`
9. `unknown_selection_error`

No free-form fallback reasons in reporting; reasons must be typed from this taxonomy.

## Required Observability Fields

Per runtime session:

1. `selectionMode` (`dawn|fawn|auto`)
2. `selectedRuntime` (`dawn|fawn`)
3. `fallbackApplied` (boolean)
4. `fallbackReasonCode` (taxonomy value or empty when not applicable)
5. `profile`:
   - `vendor`,
   - `api`,
   - `deviceFamily`,
   - `driver`.
6. `selectorVersion`
7. `artifactIdentity`:
   - runtime artifact hash/version.

## Trace and Report Contract

1. Selection fields are emitted in run metadata and trace meta.
2. Fallback events are emitted once per session and linked to run identity.
3. Selection logs must be deterministic for identical profile and controls.

## Failure Policy

1. Selector failures must fail closed to `dawn` unless explicit forced mode says otherwise.
2. Forced `fawn` mode must fail fast with actionable error if runtime cannot initialize.
3. No silent mode mutation after first successful runtime selection in a session.

## Gating Requirements

Blocking before promotion:

1. Schema gate for new selection fields.
2. Correctness gate for mode precedence behavior.
3. Trace gate for selection event and reason consistency.
4. Drop-in gate when artifact lane depends on drop-in ABI.

Advisory:

1. Performance and reliability trend tracking.

## Negative Tests (Required)

1. Missing artifact -> deterministic fallback with `runtime_artifact_missing`.
2. Missing required symbols -> deterministic fallback with `symbol_surface_incomplete`.
3. Denylisted profile -> deterministic fallback with `profile_denylisted`.
4. Global kill switch -> deterministic fallback with `global_disable_active`.
5. Forced `fawn` with failed init -> explicit hard failure, not silent Dawn selection.

## Rollback Contract

1. Rollback can be executed via global kill switch without rebuild.
2. Rollback event must include reason and timestamp in run metadata.
3. Rollback does not alter schema or artifact history contracts.

## Promotion Preconditions

1. Control-surface precedence implemented and tested.
2. Fallback taxonomy implemented and schema-backed.
3. Required observability fields present in artifacts.
4. Required negative tests pass in CI for target matrix.
