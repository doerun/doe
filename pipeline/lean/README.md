# Fawn Lean module

## Verification tier classification

Every theorem is classified into one of four tiers based on whether Lean is actually necessary to verify it:

- **`tautological`** — correct by construction or definitional. There is nothing to verify: the property follows directly from how the code is written. Lean is restating the definition. Examples: a table built from a function trivially matches that function; `rfl` proofs that just unfold a definition; a one-liner that follows from another theorem.
- **`comptime_verified`** — property over a finite domain that requires checking all cases but is independently verifiable by Zig `comptime` exhaustion or unit tests. Lean is redundant — a `comptime` inline-for or exhaustive test does the same thing.
- **`lean_verified`** — property quantified over unbounded domains (arbitrary lists, parametric structures) that `comptime` cannot enumerate. Lean is necessary.
- **`lean_fixture`** — specific test case verified against a `lean_verified` theorem. Could be an integration test, but exercises the genuine proofs and catches regressions in the obligation model.

The tier is recorded in the `category` field of the proof artifact (`config/proof-artifact.schema.json`).

## Theorem inventory by tier

### `tautological` (current artifact: 10 theorems; representative selection below)

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

### `lean_verified` (current artifact: 17 theorems) and `lean_required` (current artifact: 40 theorems)

`lean_verified` theorems are quantified over arbitrary `List Obligation` or arbitrary `Nat` — unbounded domain, cannot enumerate. `lean_required` theorems also require Lean (induction over unbounded structures: lists, IR node counts, ref chains, render-pass state machines) and are classified separately in the proof artifact.

Combined unbounded-domain theorems (57 total). Representative `lean_verified` selection below; full `lean_required` list includes IR builder soundness, IR semantic/validator contracts, MSL address-space chains, render-pass state machines, buffer dispatch preconditions, and compute bounds theorems.

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
| `gid_component_lt_total` | Single-dimension gid < array_length when dispatch fits |
| `gid_inbounds_when_dispatch_fits` | 1D dispatch: gid.x < buf.length when ws.x * nwg.x ≤ buf.length |
| `gid_plus_offset_inbounds_when_dispatch_fits` | 1D affine dispatch: gid.x + offset < buf.length when ws.x * nwg.x + offset ≤ buf.length |
| `gid_times_stride_plus_offset_inbounds_when_dispatch_fits` | 1D strided affine dispatch: gid.x * stride + offset < buf.length when ws.x * nwg.x * stride + offset ≤ buf.length |
| `gid_plus_bounded_loop_index_inbounds_when_dispatch_fits` | Constant-bounded counted-loop dispatch: gid.x + i + offset < buf.length for supported ascending or descending `for`/`while`/guarded-`loop` forms when ws.x * nwg.x + limit + offset ≤ buf.length |
| `gid_affine_plus_scaled_loop_index_inbounds_when_dispatch_fits` | Constant-bounded affine counted-loop dispatch: gid.x * gid_stride + i * loop_stride + offset < buf.length for supported ascending or descending loop forms when the scaled dispatch and loop limits fit |
| `gid_tiled_index_plus_offset_inbounds_when_dispatch_fits` | 1D tiled dispatch: `(gid.x / tile_width) * tile_stride + (gid.x % tile_width) + offset` < buf.length when host-validated tiled groups fit |
| `clamp_noop_when_inbounds` | min(gid, len-1) = gid when gid < len (connects proof to transform) |
| `gid_2d_inbounds` | Both components bounded independently for 2D dispatch |
| `flat_index_2d_inbounds` | gid.y * width + gid.x < width * height when components bounded |
| `flat_index_2d_plus_offset_inbounds` | 2D flat index plus constant offset stays in bounds when width * height + offset fits |
| `gid_texture_coords_2d_inbounds_when_dispatch_fits` | Dispatch-fit precondition implies 2D gid texture coords are in bounds |
| `guarded_gid_texture_coords_2d_inbounds` | Root early-return guard against `textureDimensions(...).xy` implies 2D gid coords are in bounds |
| `gid_texture_coords_3d_inbounds_when_dispatch_fits` | Dispatch-fit precondition implies 3D gid texture coords are in bounds |
| `guarded_gid_texture_coords_3d_inbounds` | Root early-return guard against `textureDimensions(...).xyz` implies 3D gid coords are in bounds |

### `lean_fixture` (current artifact: 6 theorems)

Specific obligation sets verified against the `lean_verified` theorems. The artifact contains 6 fixture theorems; 4 additional fixture candidates (timing-phase, hardware-path) are defined in Lean source but not yet extracted to the proof artifact.

| Theorem | Fixture | In artifact |
|---------|---------|-------------|
| `strictHappyPathExpectedBlocking_exact` | Happy-path facts produce expected blocking list | yes |
| `strictHappyPathComparable` | Happy-path facts are comparable | yes |
| `strictMissingLeftSamplesExpectedBlocking_exact` | Missing-left facts produce expected blocking | yes |
| `strictMissingLeftSamplesComparable` | Missing-left facts are comparable | yes |
| `allowLeftNoExecutionDensityFailureExpectedBlocking_exact` | Density-failure facts produce expected blocking | yes |
| `allowLeftNoExecutionDensityFailureComparable` | Density-failure facts are comparable | yes |
| `strictTimingPhaseFailureExpectedBlocking_exact` | Timing-phase failure blocking | no (source only) |
| `strictTimingPhaseFailureComparable` | Timing-phase failure comparability | no (source only) |
| `strictHardwarePathFailureExpectedBlocking_exact` | Hardware-path failure blocking | no (source only) |
| `strictHardwarePathFailureComparable` | Hardware-path failure comparability | no (source only) |

## Policy

- not every quirk requires Lean in v0
- use `verificationMode` in quirk records to decide obligation
- obligation matrix:
  - `guard_only`: no Lean proof required
  - `lean_preferred`: proof is advisory in v0
  - `lean_required`: proof is required (`proofLevel=proven`)
- safetyClass may add stricter requirements only if configured in `config/gates.json`

## Current integration boundary (v0)

- Lean files in `pipeline/lean/Fawn` are the formal contract/model source for verification semantics.
- Blocking CI gates are currently schema/correctness/trace (and claim when enabled) through `bench` scripts.
- Zig/Python runtime/gate logic mirrors Lean obligation fields and policy (`verificationMode`, `proofLevel`, blocking/advisory outcomes).
- Manual Lean typecheck/build is available through `./pipeline/lean/check.sh` (uses pinned toolchain version from `config/toolchains.json`).

## File layout

Core theorem pack (`Fawn/Core/`, maps to `runtime/zig/src/core/`):
- `Fawn/Core/Model.lean` — foundational enums, precedence lattice, requirement predicates
- `Fawn/Core/Runtime.lean` — deterministic matching, scoring, selector, driver-range matching
- `Fawn/Core/Dispatch.lean` — dispatch-level theorems (`tautological` and `comptime_verified`)
- `Fawn/Core/Bridge.lean` — obligation gate evaluation from dispatch decisions

Full theorem pack (`Fawn/Full/`, maps to `runtime/zig/src/full/`):
- `Fawn/Full/Comparability.lean` — comparability obligation model (`lean_verified`)
- `Fawn/Full/ComparabilityFixtures.lean` — parity fixtures (`lean_fixture`)
- `Fawn/Full/WorkloadGeometry.lean` — arbitrary-`Nat` workload-geometry theorems feeding execution-shape comparability

Shader theorem pack (`Fawn/Shader/`, maps to `runtime/zig/src/doe_wgsl/`):
- `Fawn/Shader/ComputeBounds.lean` — compute dispatch bounds safety, proving global_invocation_id < array_length under dispatch-fit preconditions. Enables bounds-check elimination in `ir_transform_robustness.zig`.

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

- `./pipeline/lean/generate_comparability_contract.py` regenerates `Fawn/Generated/ComparabilityContract.lean` from `config/comparability-obligations.json` before typecheck/extraction.
- `./pipeline/lean/extract.sh` compiles all Lean modules and runs `Fawn/Extract.lean` to produce `pipeline/lean/artifacts/proven-conditions.json`.
- The artifact lists all verified theorems with their tier classification, records the active comparability contract hash, evaluates decidable propositions, and maps theorems to Zig runtime elimination targets.
- Artifact schema: `config/proof-artifact.schema.json`.
- CI runs extraction after typecheck and uploads the artifact (see `.github/workflows/lean-check.yml`).
- The artifact is generated (not committed); `pipeline/lean/artifacts/` is gitignored.
- Zig build embeds the artifact at comptime via `-Dlean-verified=true`.

## Zig runtime integration

When built with `-Dlean-verified=true`, `lean_proof.zig` validates the proof artifact at comptime and sets `lean_proof.lean_verified = true`. The Zig compiler dead-code-eliminates branches gated on this flag.

The `tautological` and `comptime_verified` theorems gate init-time and per-command branch elimination in `quirk/runtime.zig`. These properties are independently verifiable by Zig `comptime` — the Lean proof is a redundant second check, not the sole authority.

The `lean_verified` theorems validate the comparability obligation model used by benchmark methodology gates. These cannot be replicated by `comptime` exhaustion because they quantify over arbitrary obligation lists and arbitrary Nat-valued workload geometry. This is where Lean earns its keep.

Build chain: Lean typecheck → `extract.sh` emits `proven-conditions.json` → `build.zig` reads artifact → `lean_proof.zig` validates at comptime → `runtime.zig` uses `lean_proof.lean_verified` as comptime gate → compiler eliminates unreachable branches.
