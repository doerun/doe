# Fawn Zig Architecture: Lean-Verified to Runtime Execution

This document defines how Zig implements fast, deterministic runtime quirk behavior using
Lean-verified evidence contracts from `fawn/dawn-research`.

## Design goals

- Consume only validated artifacts (`candidate_pack`, optionally `workaround_rows`, `trend_buckets`).
- Keep policy logic in Lean; keep Zig in deterministic execution and fast dispatch.
- Replace nested branching with explicit state types, compile-time or startup-built lookup tables.
- Produce auditable outputs (rule IDs, evidence IDs, decision traces).
- Prevent silent behavior drift.

## Module responsibilities

- `fawn/lean/`
  - verifies schema + safety invariants
  - emits machine-checked guarantees consumed by Zig runtime boundary
- `fawn/zig/src/model.zig`
  - canonical runtime contracts:
    - `DecisionInput` (candidate rows + optional context)
    - `EvidenceRef`
    - `QuirkKey`
    - `QuirkAction` (union enum)
    - `DecisionRecord`
- `fawn/zig/src/parser.zig`
  - reads JSONL artifacts and maps to typed contract structs
  - validates:
    - required evidence fields
    - enum/domain integrity
    - rule/action consistency
- `fawn/zig/src/dispatch.zig`
  - builds decision indexes:
    - `key -> rule list`
    - ordered by `priority`/score
  - resolves candidate deterministically
- `fawn/zig/src/executor.zig`
  - applies chosen `QuirkAction` on request/context
  - emits `DecisionTrace` and execution result
- `fawn/zig/src/trace.zig`
  - structured trace schema:
    - `traceId`
    - input signature
    - selected rule id
    - match rationale
    - fallback path and reason

## Data flow

1) Ingestion
- `candidate_pack/*.jsonl` (and optional context files) read in.
- Inputs parsed to canonical structs.

2) Validate
- Validate all entries via schema assumptions from Lean outputs.
- Reject malformed rows as hard errors at load boundary.

3) Index
- Build `DispatchIndex`:
  - `QuirkKey -> []RuleIndexEntry`
- Keep stable ordering and deterministic tie-breakers.

4) Resolve
- For each candidate:
  - normalize key (vendor/backend/failure class)
  - lookup key bucket
  - select first eligible rule by score/policy ordering
  - attach fallback state when no rule matches

5) Execute
- Convert selected action into a concrete runtime operation.
- Return decision + trace.

## Anti-if-ladder mapping

- Replace conditions like:
  - `if vendor == X && backend == Y && failure == Z`
- with:
  - typed `QuirkKey` lookup table
  - ordered rule candidate list per key
  - explicit `switch(action)` execution

## Initial folder structure

- `fawn/zig/src/model.zig`
- `fawn/zig/src/parser.zig`
- `fawn/zig/src/dispatch.zig`
- `fawn/zig/src/executor.zig`
- `fawn/zig/src/trace.zig`
- `fawn/zig/src/plan_cache.zig` (optional)
- `fawn/zig/src/main.zig`
- `fawn/zig/build.zig`
- `fawn/zig/generated/` (generated lookup artifacts from candidate data)
- `fawn/zig/tests/`

## Suggested first pass implementation

### Phase 1: Contracts + loader (day 1)
- Implement `model.zig` (core types + serde expectations)
- Implement `parser.zig` for `candidate_pack/candidate-*.jsonl`
- Add minimal fixture tests

### Phase 2: Deterministic dispatch (day 2)
- Implement `dispatch.zig` as key-indexed rules
- Add deterministic sorting and tie-break tests

### Phase 3: Executor + trace (day 3)
- Implement `executor.zig` + `trace.zig`
- Emit `DecisionRecord` with rule IDs/evidence list

### Phase 4: Integration and Lean boundary
- Add CLI entry `main.zig` for pipeline-driven replay
- Validate output parity vs Lean expectations

## Error model

- Use explicit errors:
  - `ParseError`
  - `MissingField`
  - `InvalidEnum`
  - `NoApplicableRule`
  - `SchemaMismatch`
- Never default to silent fallback for unexpected combinations.

## Trace fields (minimum)

- `traceId`
- `candidateId`
- `decision`
- `matchedRuleId`
- `fallbackRule` (if any)
- `evidenceIds` (array)
- `reason`
- `inputs` (vendor/backend/failureclass/context hash)
- `generatedAt`

## Build / validation gates

- `zig fmt` + `zig test`
- Determinism check:
 - same input artifact set => stable output JSON and traces
- Lean gating:
 - no Zig execution run without Lean-verified schema acceptance for consuming artifacts.
