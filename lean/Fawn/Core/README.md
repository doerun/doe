# Fawn core proofs

Theorem packs for the core runtime layer (`zig/src/core/`).

Core covers baseline command support: upload, copy, barrier, dispatch, kernel_dispatch.

## Modules

- `Model.lean` -- foundational enums (Api, Scope, SafetyClass, VerificationMode, ProofLevel, CommandKind, ActionKind), precedence lattice, requirement predicates, and the `critical_is_max_rank` and `requiredProof_forbidden_reject_from_rank` theorems.
- `Runtime.lean` -- deterministic quirk matching, scoring, driver-range matching, dispatch decision metadata, proof-priority tie-break, and the `betterMatch_prefers_higher_score` theorem.
- `Dispatch.lean` -- dispatch-level theorems proven against the Runtime model: `toggleAlwaysSupported`, `strongerSafetyRaisesProofDemand`, identity-action completeness (`identityActionComplete`), and individual action-identity lemmas.
- `Bridge.lean` -- obligation gate evaluation: `SafetyProofOverride`, `QuirkLeanObligation`, blocking/advisory determination from dispatch decisions, and batch obligation collection.

## Dependency order

```
Model -> Runtime -> Dispatch
Model -> Runtime -> Bridge
```

## Zig elimination targets

Theorems in this pack drive proof-driven branch elimination in the Zig core dispatch path (with `-Dlean-verified=true`):
- `toggleAlwaysSupported` eliminates `supportsCommand` switch for `driver_toggle` quirks
- `requiredProof_forbidden_reject_from_rank` eliminates `requires_lean` check for rejected proof level
- `strongerSafetyRaisesProofDemand` eliminates `requires_lean` check for critical safety class
- `identityActionComplete` hoists toggle registry scan from per-command to init time
