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
- safetyClass may add stricter requirements only if configured in `fawn/config/gates.json`

Current integration boundary (v0):
- Lean files in `fawn/lean/Fawn` are the formal contract/model source for verification semantics.
- Blocking CI gates are currently schema/correctness/trace (and claim when enabled) through `fawn/bench` scripts.
- Zig/Python runtime/gate logic mirrors Lean obligation fields and policy (`verificationMode`, `proofLevel`, blocking/advisory outcomes).
- Manual Lean typecheck/build is available through `./lean/check.sh` (uses pinned toolchain version from `config/toolchains.json`).

Current formalization:
- `Fawn/Model.lean` (core enums, precedence lattice, requirement predicates)
- `Fawn/Dispatch.lean` (command/scope relation and support lemmas)
- `Fawn/Runtime.lean` (deterministic matching + scoring + selector for quirk streams)
- `Fawn/Runtime.lean` now includes driver-range matching and dispatch decision metadata (`DispatchDecision`) with proof obligations in the path.
- `Fawn/Bridge.lean` (obligation gate evaluation from dispatch decisions)
- `Fawn/Comparability.lean` (machine-checkable apples-to-apples comparability obligation model and blocking-failure semantics)
- `Fawn/ComparabilityFixtures.lean` (fixed comparability-facts parity fixtures with expected blocking-obligation proofs)
- `Fawn/Dispatch.lean` and `Fawn/Runtime.lean` now include `kernelDispatch` as a first-class command kind.
- `Fawn/Extract.lean` (proof artifact extraction program)

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
- Zig build can optionally embed the artifact at comptime via `@embedFile` for proof-driven branch elimination.
