# Doe full proofs

Theorem packs for the full runtime layer (`runtime/zig/src/full/`), covering extended operations beyond core: render, surface, lifecycle, and benchmark comparability methodology.

## Modules

- `Comparability.lean` -- machine-checkable apples-to-apples comparability obligation model: `ComparabilityObligationId`, `ComparabilityFacts`, `obligationsFromFacts`, blocking-failure semantics, and bidirectional theorems linking `comparableFromObligations`/`comparableFromFacts` to failed-blocking lists.
- `ComparabilityFixtures.lean` -- fixed comparability-facts parity fixtures with expected blocking-obligation proofs: strict happy path, missing left samples, density failure, timing phase failure, hardware path failure (all verified via `native_decide`).

## Dependency order

```
Doe.Core.Model -> Comparability -> ComparabilityFixtures
```

Full proofs depend on `Doe.Core.Model` for shared types but do not depend on `Doe.Core.Runtime`, `Doe.Core.Dispatch`, or `Doe.Core.Bridge`.

## Scope

This pack currently covers benchmark comparability methodology proofs. As render pass, surface lifecycle, and broader object-model proofs are formalized, they will be added here following the same `runtime/zig/src/full/` boundary.
