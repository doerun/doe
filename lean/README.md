# Fawn Lean Module

Purpose:
- formalize high-ROI invariants for selected quirk classes
- emit proof verdicts and validator artifacts where required

Policy:
- not every quirk requires Lean in v0
- use `verificationMode` in quirk records to decide obligation
- obligation matrix:
  - `guard_only`: no Lean proof required
  - `lean_preferred`: proof is advisory in v0
  - `lean_required`: proof is required (`proofLevel=proven`)
- safetyClass may add stricter requirements only if configured in `config/gates.json`

Current integration boundary (v0):
- Lean files in `lean/Fawn` are the formal contract/model source for verification semantics.
- Blocking CI gates are currently schema/correctness/trace (and claim when enabled) through `bench` scripts.
- Zig/Python runtime/gate logic mirrors Lean obligation fields and policy (`verificationMode`, `proofLevel`, blocking/advisory outcomes).
- Manual Lean typecheck/build is available through `./lean/check.sh` (uses pinned toolchain version from `config/toolchains.json`).

Current formalization (core/full split):

Core theorem pack (`Fawn/Core/`, maps to `zig/src/core/`):
- `Fawn/Core/Model.lean` (foundational enums, precedence lattice, requirement predicates)
- `Fawn/Core/Runtime.lean` (deterministic matching + scoring + selector for quirk streams, driver-range matching, dispatch decision metadata; includes `kernelDispatch` as a first-class command kind)
- `Fawn/Core/Dispatch.lean` (dispatch-level theorems: `toggleAlwaysSupported`, `strongerSafetyRaisesProofDemand`, `identityActionComplete`)
- `Fawn/Core/Bridge.lean` (obligation gate evaluation from dispatch decisions)

Full theorem pack (`Fawn/Full/`, maps to `zig/src/full/`):
- `Fawn/Full/Comparability.lean` (machine-checkable apples-to-apples comparability obligation model and blocking-failure semantics)
- `Fawn/Full/ComparabilityFixtures.lean` (fixed comparability-facts parity fixtures with expected blocking-obligation proofs)

Re-export shims (backward compatibility):
- `Fawn/Model.lean`, `Fawn/Runtime.lean`, `Fawn/Dispatch.lean`, `Fawn/Bridge.lean`, `Fawn/Comparability.lean`, `Fawn/ComparabilityFixtures.lean` re-export from `Fawn.Core.*` / `Fawn.Full.*` so existing imports continue to work.

Extraction:
- `Fawn/Extract.lean` (proof artifact extraction program, imports from both Core and Full)

Bridge layer contract:
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

Usage model:
- proofs are authored manually; no auto-generated theorem output is expected for `fawn`.
- runtime obligations should map from `verificationMode` + safety class to theorem entry points in a separate integration layer.

Proof artifact extraction:
- `./lean/extract.sh` compiles all Lean modules and runs `Fawn/Extract.lean` to produce `lean/artifacts/proven-conditions.json`.
- The artifact lists all verified theorems, evaluates decidable propositions, and maps theorems to Zig runtime elimination targets.
- Artifact schema: `config/proof-artifact.schema.json`.
- CI runs extraction after typecheck and uploads the artifact (see `.github/workflows/lean-check.yml`).
- The artifact is generated (not committed); `lean/artifacts/` is gitignored.
- Zig build embeds the artifact at comptime via `-Dlean-verified=true` for proof-driven branch elimination.

## Proof-driven branch elimination (active)

When built with `-Dlean-verified=true`, Lean theorems eliminate runtime branches in the Zig dispatch path. Proofs run at build time. The compiled binary has fewer branches.

| Theorem | Elimination | Path | Scope |
|---------|------------|------|-------|
| `toggleAlwaysSupported` | Skip 20 `supportsCommand` switch evaluations per `driver_toggle` quirk | `runtime.zig:buildDispatchContext` | init |
| `requiredProof_forbidden_reject_from_rank` | `.rejected` proof level → unconditionally blocking (skip `requires_lean` check) | `runtime.zig:finalizeBucket` | init |
| `strongerSafetyRaisesProofDemand` | Critical safety class → `is_blocking = proof_level != .proven` (skip `requires_lean` check) | `runtime.zig:finalizeBucket` | init |
| `identityActionComplete` | Informational/unhandled toggle and no-op actions skip `applyAction` entirely | `runtime.zig:dispatch` | per-command |

The per-command elimination (`identityActionComplete`) hoists the toggle registry linear scan (12 entries, case-insensitive string compare) from per-command to init time. Saves ~100-180ns per dispatched command matched by an informational toggle quirk. At 10,000 commands (autoregressive decode or diffusion step loops), this is 1-2ms saved from proof alone.

Build chain: Lean typecheck, `extract.sh` emits `proven-conditions.json`, `build.zig` reads artifact, `lean_proof.zig` validates at comptime, `runtime.zig` uses `lean_proof.lean_verified` as comptime gate, compiler dead-code-eliminates the unreachable branches.
