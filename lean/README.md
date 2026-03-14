# Fawn Lean module

## Verification tier classification

Every theorem is classified into one of four tiers based on whether Lean is actually necessary to verify it:

- **`tautological`** — correct by construction or definitional. There is nothing to verify: the property follows directly from how the code is written. Lean is restating the definition. Examples: a table built from a function trivially matches that function; `rfl` proofs that just unfold a definition; a one-liner that follows from another theorem.
- **`comptime_verified`** — property over a finite domain that requires checking all cases but is independently verifiable by Zig `comptime` exhaustion or unit tests. Lean is redundant — a `comptime` inline-for or exhaustive test does the same thing.
- **`lean_verified`** — property quantified over unbounded domains (arbitrary lists, parametric structures) that `comptime` cannot enumerate. Lean is necessary.
- **`lean_fixture`** — specific test case verified against a `lean_verified` theorem. Could be an integration test, but exercises the genuine proofs and catches regressions in the obligation model.

The tier is recorded in the `category` field of the proof artifact (`config/proof-artifact.schema.json`).

## Theorem inventory by tier

### `tautological` (8 theorems, ~27 lines)

Nothing to verify. These restate definitions or are correct by construction.

| Theorem | What it says | Why it's tautological |
|---------|-------------|----------------------|
| `scopeCommandTableComplete` | Comptime table matches `supportsScope` | Table is built from the function — `X == X` |
| `toggleAlwaysSupported` | `driver_toggle` supports all commands | Subsumed by above; `driver_toggle => True` is the definition |
| `noOpActionIdentity` | `no_op.isIdentity = true` | Definitional (`rfl` — just unfolds the definition) |
| `informationalToggleIdentity` | `(toggle .informational).isIdentity = true` | Definitional (`rfl`) |
| `unhandledToggleIdentity` | `(toggle .unhandled).isIdentity = true` | Definitional (`rfl`) |
| `behavioralToggleNotIdentity` | `(toggle .behavioral).isIdentity = false` | Definitional (`rfl`) |
| `betterMatch_prefers_higher_score` | Higher score wins | `if a < b then b` returns `b` — obvious from definition |
| `identityActionPreservesCommand` | Identity actions preserve commands | One-liner: calls `identityActionComplete` |

### `comptime_verified` (4 theorems, ~19 lines)

Finite-enum properties that require checking all cases. Zig `comptime` inline-for or exhaustive tests would verify the same thing.

| Theorem | What it says | Domain size |
|---------|-------------|-------------|
| `critical_is_max_rank` | Critical has the highest safety rank | 4 enum values |
| `requiredProof_forbidden_reject_from_rank` | No safety class maps to `.rejected` | 3 × 3 enum pairs |
| `strongerSafetyRaisesProofDemand` | Critical safety demands `.proven` proof | 3 enum values |
| `identityActionComplete` | Exactly which actions are identity (iff) | 4 action variants × sub-cases |

### `lean_verified` (9 theorems, ~65 lines)

Quantified over arbitrary `List Obligation` — unbounded domain, cannot enumerate.

| Theorem | What it proves |
|---------|---------------|
| `comparableFromObligations_eq_noFailed` | Comparability equals having no failed obligations |
| `comparableFromFacts_eq_noFailed` | Same, from facts (composed through obligation pipeline) |
| `comparableFromObligations_true_iff_failedBlockingNil` | Comparable ↔ no failed blocking obligations |
| `comparableFromObligations_false_iff_failedBlockingNonEmpty` | Not comparable ↔ at least one failed blocking obligation |
| `comparableFromFacts_true_iff_failedBlockingNil` | Same, from facts |
| `comparableFromFacts_false_iff_failedBlockingNonEmpty` | Same, from facts |
| `structurallyEquivalentGeometry_refl` | Any workload geometry is structurally equivalent to itself |
| `structurallyEquivalentGeometry_forall_components` | Arbitrary Nat-valued buffer/dispatch components remain structurally equivalent when mirrored |
| `equalGeometrySetsExecutionShapeFacts` | Equal Nat-valued geometry forces execution-shape comparability facts true |

### `lean_fixture` (10 theorems, ~35 lines)

Specific obligation sets verified against the `lean_verified` theorems.

| Theorem | Fixture |
|---------|---------|
| `strictHappyPathExpectedBlocking_exact` | Happy-path facts produce expected blocking list |
| `strictHappyPathComparable` | Happy-path facts are comparable |
| `strictMissingLeftSamplesExpectedBlocking_exact` | Missing-left facts produce expected blocking |
| `strictMissingLeftSamplesComparable` | Missing-left facts are comparable |
| `allowLeftNoExecutionDensityFailureExpectedBlocking_exact` | Density-failure facts produce expected blocking |
| `allowLeftNoExecutionDensityFailureComparable` | Density-failure facts are comparable |
| `strictTimingPhaseFailureExpectedBlocking_exact` | Timing-phase failure blocking |
| `strictTimingPhaseFailureComparable` | Timing-phase failure comparability |
| `strictHardwarePathFailureExpectedBlocking_exact` | Hardware-path failure blocking |
| `strictHardwarePathFailureComparable` | Hardware-path failure comparability |

## Policy

- not every quirk requires Lean in v0
- use `verificationMode` in quirk records to decide obligation
- obligation matrix:
  - `guard_only`: no Lean proof required
  - `lean_preferred`: proof is advisory in v0
  - `lean_required`: proof is required (`proofLevel=proven`)
- safetyClass may add stricter requirements only if configured in `config/gates.json`

## Current integration boundary (v0)

- Lean files in `lean/Fawn` are the formal contract/model source for verification semantics.
- Blocking CI gates are currently schema/correctness/trace (and claim when enabled) through `bench` scripts.
- Zig/Python runtime/gate logic mirrors Lean obligation fields and policy (`verificationMode`, `proofLevel`, blocking/advisory outcomes).
- Manual Lean typecheck/build is available through `./lean/check.sh` (uses pinned toolchain version from `config/toolchains.json`).

## File layout

Core theorem pack (`Fawn/Core/`, maps to `zig/src/core/`):
- `Fawn/Core/Model.lean` — foundational enums, precedence lattice, requirement predicates
- `Fawn/Core/Runtime.lean` — deterministic matching, scoring, selector, driver-range matching
- `Fawn/Core/Dispatch.lean` — dispatch-level theorems (`tautological` and `comptime_verified`)
- `Fawn/Core/Bridge.lean` — obligation gate evaluation from dispatch decisions

Full theorem pack (`Fawn/Full/`, maps to `zig/src/full/`):
- `Fawn/Full/Comparability.lean` — comparability obligation model (`lean_verified`)
- `Fawn/Full/ComparabilityFixtures.lean` — parity fixtures (`lean_fixture`)
- `Fawn/Full/WorkloadGeometry.lean` — arbitrary-`Nat` workload-geometry theorems feeding execution-shape comparability

Generated theorem contract:
- `Fawn/Generated/ComparabilityContract.lean` — generated from `config/comparability-obligations.json`; provides the canonical obligation IDs, fact record, and `obligationsFromFacts`

Re-export shims (backward compatibility):
- `Fawn/Model.lean`, `Fawn/Runtime.lean`, `Fawn/Dispatch.lean`, `Fawn/Bridge.lean`, `Fawn/Comparability.lean`, `Fawn/ComparabilityFixtures.lean` re-export from `Fawn.Core.*` / `Fawn.Full.*`.

Extraction:
- `Fawn/Extract.lean` — proof artifact extraction program, imports from both Core and Full

## Bridge layer contract

- input: runtime `DispatchResult` stream
- optional override: `SafetyProofOverride` maps safety class to stricter proof level requirements
- output per matched quirk (`QuirkLeanObligation`) with:
  - `quirkId`
  - `requiresLean`
  - `requiredProofLevel` (`none` = no Lean requirement)
  - `actualProofLevel`
  - `isBlocking`
  - `isAdvisory`
- v0 policy:
  - `lean_required` sets blocking requirement to `proven`
  - `lean_preferred` is intentionally advisory only when explicitly driven by override
  - default safety overrides remain empty (`none`)

## Proof artifact extraction

- `./lean/generate_comparability_contract.py` regenerates `Fawn/Generated/ComparabilityContract.lean` from `config/comparability-obligations.json` before typecheck/extraction.
- `./lean/extract.sh` compiles all Lean modules and runs `Fawn/Extract.lean` to produce `lean/artifacts/proven-conditions.json`.
- The artifact lists all verified theorems with their tier classification, records the active comparability contract hash, evaluates decidable propositions, and maps theorems to Zig runtime elimination targets.
- Artifact schema: `config/proof-artifact.schema.json`.
- CI runs extraction after typecheck and uploads the artifact (see `.github/workflows/lean-check.yml`).
- The artifact is generated (not committed); `lean/artifacts/` is gitignored.
- Zig build embeds the artifact at comptime via `-Dlean-verified=true`.

## Zig runtime integration

When built with `-Dlean-verified=true`, `lean_proof.zig` validates the proof artifact at comptime and sets `lean_proof.lean_verified = true`. The Zig compiler dead-code-eliminates branches gated on this flag.

The `tautological` and `comptime_verified` theorems gate init-time and per-command branch elimination in `quirk/runtime.zig`. These properties are independently verifiable by Zig `comptime` — the Lean proof is a redundant second check, not the sole authority.

The `lean_verified` theorems validate the comparability obligation model used by benchmark methodology gates. These cannot be replicated by `comptime` exhaustion because they quantify over arbitrary obligation lists and arbitrary Nat-valued workload geometry. This is where Lean earns its keep.

Build chain: Lean typecheck → `extract.sh` emits `proven-conditions.json` → `build.zig` reads artifact → `lean_proof.zig` validates at comptime → `runtime.zig` uses `lean_proof.lean_verified` as comptime gate → compiler eliminates unreachable branches.
