# Fawn Lean module

## Verification tier classification

Every theorem in this module is classified into one of three tiers based on whether Lean is actually necessary to verify it:

- **`comptime_verified`** — property operates on finite enums and is independently verifiable by Zig `comptime` exhaustion or unit tests. Lean provides a second-opinion check but is not the only way to verify these. All dispatch-layer theorems (Model, Runtime, Dispatch) fall here.
- **`lean_verified`** — property is quantified over unbounded domains (arbitrary lists, parametric structures) that `comptime` cannot enumerate. Lean is necessary. The comparability obligation theorems fall here.
- **`lean_fixture`** — specific test case verified against a `lean_verified` theorem. Could be an integration test, but exercises the genuine proofs and catches regressions in the obligation model. The comparability fixture theorems fall here.

The tier is recorded in the `category` field of the proof artifact (`config/proof-artifact.schema.json`).

## Theorem inventory by tier

### `comptime_verified` (12 theorems, ~46 lines)

All finite-enum properties. Zig `comptime` inline-for or exhaustive tests would verify the same thing.

| Theorem | What it says | Why comptime suffices |
|---------|-------------|----------------------|
| `critical_is_max_rank` | Critical has the highest safety rank | 4 enum values |
| `requiredProof_forbidden_reject_from_rank` | No safety class maps to `.rejected` | 3 × 3 enum pairs |
| `toggleAlwaysSupported` | `driver_toggle` scope supports all commands | Subsumed by `scopeCommandTableComplete` |
| `strongerSafetyRaisesProofDemand` | Critical safety demands `.proven` proof | 3 enum values |
| `betterMatch_prefers_higher_score` | Higher score wins tie-breaking | Obvious from `if a < b then b` |
| `noOpActionIdentity` | `no_op.isIdentity = true` | Definitional (`rfl`) |
| `informationalToggleIdentity` | `(toggle .informational).isIdentity = true` | Definitional (`rfl`) |
| `unhandledToggleIdentity` | `(toggle .unhandled).isIdentity = true` | Definitional (`rfl`) |
| `behavioralToggleNotIdentity` | `(toggle .behavioral).isIdentity = false` | Definitional (`rfl`) |
| `identityActionComplete` | Exactly which actions are identity | 4 action variants |
| `scopeCommandTableComplete` | `supportsScope` is decidable for all 120 scope×command pairs | Table is built from the function at comptime |
| `identityActionPreservesCommand` | Identity actions preserve commands | Follows from `identityActionComplete` |

### `lean_verified` (6 theorems, ~42 lines)

Quantified over arbitrary `List Obligation` — unbounded domain, cannot enumerate.

| Theorem | What it proves |
|---------|---------------|
| `comparableFromObligations_eq_noFailed` | Comparability equals having no failed obligations |
| `comparableFromFacts_eq_noFailed` | Same, from facts (composed through obligation pipeline) |
| `comparableFromObligations_true_iff_failedBlockingNil` | Comparable ↔ no failed blocking obligations |
| `comparableFromObligations_false_iff_failedBlockingNonEmpty` | Not comparable ↔ at least one failed blocking obligation |
| `comparableFromFacts_true_iff_failedBlockingNil` | Same, from facts |
| `comparableFromFacts_false_iff_failedBlockingNonEmpty` | Same, from facts |

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
- `Fawn/Core/Dispatch.lean` — dispatch-level theorems (all `comptime_verified`)
- `Fawn/Core/Bridge.lean` — obligation gate evaluation from dispatch decisions

Full theorem pack (`Fawn/Full/`, maps to `zig/src/full/`):
- `Fawn/Full/Comparability.lean` — comparability obligation model (`lean_verified`)
- `Fawn/Full/ComparabilityFixtures.lean` — parity fixtures (`lean_fixture`)

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

- `./lean/extract.sh` compiles all Lean modules and runs `Fawn/Extract.lean` to produce `lean/artifacts/proven-conditions.json`.
- The artifact lists all verified theorems with their tier classification, evaluates decidable propositions, and maps theorems to Zig runtime elimination targets.
- Artifact schema: `config/proof-artifact.schema.json`.
- CI runs extraction after typecheck and uploads the artifact (see `.github/workflows/lean-check.yml`).
- The artifact is generated (not committed); `lean/artifacts/` is gitignored.
- Zig build embeds the artifact at comptime via `-Dlean-verified=true`.

## Zig runtime integration

When built with `-Dlean-verified=true`, `lean_proof.zig` validates the proof artifact at comptime and sets `lean_proof.lean_verified = true`. The Zig compiler dead-code-eliminates branches gated on this flag.

The `comptime_verified` theorems gate init-time and per-command branch elimination in `quirk/runtime.zig`. These same branches could equivalently be gated by Zig `comptime` assertions — the Lean proof is a redundant second check, not the sole authority.

The `lean_verified` theorems validate the comparability obligation model used by benchmark methodology gates. These cannot be replicated by `comptime` exhaustion because they quantify over arbitrary obligation lists.

Build chain: Lean typecheck → `extract.sh` emits `proven-conditions.json` → `build.zig` reads artifact → `lean_proof.zig` validates at comptime → `runtime.zig` uses `lean_proof.lean_verified` as comptime gate → compiler eliminates unreachable branches.
