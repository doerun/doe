# Numeric stability contract roadmap

## Purpose

This document defines the config/proof/discovery contract for numeric
stability so bench evidence can graduate into runtime behavior without ad-hoc
logic.

The short rule is:

- discovery artifacts may find fragility
- promoted artifacts may justify runtime work
- only runtime-exercised receipts count toward novelty

This is intentionally narrower than “determinism.” The target is a governed
runtime contract around numerically fragile decision boundaries.

## Current truth

Current shipped truth is limited to:

- one route taxonomy in
  [`config/numeric-stability-policy.json`](/Users/xyz/deco/doe/config/numeric-stability-policy.json)
- one trigger family and one routing family
- Lean proof of the current trigger predicate and the current triggered/fallback
  route selector in
  [`pipeline/lean/Doe/Core/NumericStabilityPolicy.lean`](/Users/xyz/deco/doe/pipeline/lean/Doe/Core/NumericStabilityPolicy.lean)
- bench/probe evaluation in
  [`bench/runners/run_selective_stable_rerun_probe.py`](/Users/xyz/deco/doe/bench/runners/run_selective_stable_rerun_probe.py)
- one explicit live Zig/package bounded-slice consumer in
  [`runtime/zig/src/full/modules/services/numeric_stability.zig`](/Users/xyz/deco/doe/runtime/zig/src/full/modules/services/numeric_stability.zig)
  and
  [`packages/doe-gpu/README.md`](/Users/xyz/deco/doe/packages/doe-gpu/README.md)
- one native ordinary-execution runtime consumer in
  [`runtime/zig/src/numeric_stability_runtime.zig`](/Users/xyz/deco/doe/runtime/zig/src/numeric_stability_runtime.zig)
  wired through
  [`runtime/zig/src/main.zig`](/Users/xyz/deco/doe/runtime/zig/src/main.zig)
- discovery/promotion evidence in status and bench reports
- selected native `runtime-exercised` receipts in
  `bench/out/apple-metal-in-path-numeric-stability/*`

Current route truth is only:

- `accept-fast`
- `prefer-stable`
- `abstain`

There are now two live runtime consumers of the numeric-stability registry in
Zig:

- the explicit bounded-slice service over caller-supplied inputs
- the native ordinary-execution `matmul.logits` path for annotated
  `kernel_dispatch`

Browser is still target state, not proof of uniqueness.

## Canonical fragility signature

Canonical discovery and promotion artifacts should normalize to one case shape.
The schema is:

- [`config/fragility-signature.schema.json`](/Users/xyz/deco/doe/config/fragility-signature.schema.json)

The schema is intentionally case-centric rather than report-centric.

Required identity:

- `signatureId`
- `contractStage`
- `artifactKind`
- `corpusClass`
- `routeTaxonomyVersion`
- `sourceArtifactPath`
- `scenarioStem`

Required semantic payload by stage:

- `answerSet`
- `referenceSelection`
- `fastSelection`
- `boundedAnswerMetrics`

Required runtime-governance payload once promoted:

- `firstDivergence`
- `routeExpectation`

Required runtime-governance payload once exercised live:

- `routeOutcome`
- `proofLinks`

The important separation is:

- `routeExpectation` is still discovery/promoted evidence and may remain
  hypothetical
- `routeOutcome` is realized runtime or policy behavior only

## Artifact graduation ladder

### 1. Discovery

Source:

- timestamped hunt reports under `bench/out/...`

Contract:

- advisory for product claims
- blocking only for schema validity and artifact traceability

Minimum required evidence:

- real prompt or real operator family
- explicit bounded answer set or operator/control surface
- exact/reference token or exact/reference top token
- fast-policy token
- stable-policy token if available
- stable source receipt (`sourceStable` or equivalent repeat stability)

Discovery does not count as runtime novelty.

### 2. Promoted

Source:

- a discovery case plus generated reduction-order and selective-rerun receipts

Canonical checked-in surfaces:

- [`config/fragility-promotion-policy.json`](/Users/xyz/deco/doe/config/fragility-promotion-policy.json)
- [`config/promoted-fragility-catalog.json`](/Users/xyz/deco/doe/config/promoted-fragility-catalog.json)
- `config/fragility-signatures/promoted/*.json`, each validated by
  [`config/fragility-signature.schema.json`](/Users/xyz/deco/doe/config/fragility-signature.schema.json)

Contract:

- blocking for inclusion in the promoted signature catalog
- still advisory for novelty claims until exercised in the runtime

Minimum required evidence:

- first divergent operator ID
- fast/stable digests
- exact-reference match flags
- realized selective-rerun receipt in bench/probe land
- route expectation promoted to `realized-in-promotion`

Promoted means the case is ready to inform runtime work.
It does not mean the runtime already governs it.

### 3. Runtime candidate

Source:

- promoted signature distilled into runtime-consumable config

Required config surfaces:

- numeric-stability policy registry:
  [`config/numeric-stability-policy.json`](/Users/xyz/deco/doe/config/numeric-stability-policy.json)
- promoted fragility catalog:
  [`config/promoted-fragility-catalog.json`](/Users/xyz/deco/doe/config/promoted-fragility-catalog.json)
- runtime trace/receipt schema extension
- runtime-visible consumer of the promoted signature catalog

Contract:

- blocking for runtime-visible enablement
- advisory for performance until the hot-path cost is measured

Runtime candidate means:

- the registry has a versioned trigger/routing policy
- the runtime can parse and evaluate the policy
- the runtime can emit a receipt shape matching the contract

### 4. Runtime exercised

Source:

- native/package runtime execution, later browser

Contract:

- this is the novelty bar
- blocking for public runtime claims

Minimum required evidence:

- runtime, not bench, chose the route
- only the sensitive operator was rerun
- first-divergence receipt was emitted live
- route outcome was emitted live
- route proof links resolve against the current proof artifact

This is the first stage that supports the claim:

“Doe governs numeric fragility at the WebGPU runtime boundary.”

This bar is now met for selected native `matmul.logits` ordinary-execution
cases. It is not yet met for broader operator families or generic package and
browser callers.

## Route taxonomy roadmap

### Current supported taxonomy

Current runtime contract truth remains:

- `accept-fast`
- `prefer-stable`
- `abstain`

Interpretation:

- `accept-fast`: keep the fast result
- `prefer-stable`: substitute the stable rerun result
- `abstain`: do not auto-substitute either result

`abstain` is real schema truth now even if current live evidence is thin.
It should remain the only non-substituting route until a review surface exists.

### Review-required roadmap

`review-required` must not enter the numeric-stability registry until all of
the following are true:

1. Native/package runtime can return a non-hidden review-needed outcome.
2. Receipt schema can carry:
   - review policy ID
   - decision reference
   - signature/reference for the review decision
3. Public package/native surface can expose the route without silently falling
   back to `accept-fast` or `prefer-stable`.
4. Lean has proof for:
   - review acceptance semantics
   - fallback ordering when no review decision is supplied
5. Migration notes and trace-meta contract ship in the same change.

Until then:

- `abstain` is the honest current route
- “review-required” is roadmap language only

## Proof roadmap

### What current Lean proves

Current Lean in
[`pipeline/lean/Doe/Core/NumericStabilityPolicy.lean`](/Users/xyz/deco/doe/pipeline/lean/Doe/Core/NumericStabilityPolicy.lean)
proves:

- the current trigger predicate is true iff all current checks are true
- the route selector returns the triggered decision when triggered
- the route selector returns the fallback decision when not triggered

This is the correct current scope.

### What must be added next

Only add proofs that the runtime will actually consume next.

Next proof targets:

1. Route-to-selection semantics
   - `accept-fast` selects fast variant
   - `prefer-stable` selects stable variant
   - `abstain` selects no substitution

2. Trigger family extensions, only when the registry grows
   - bounded-margin trigger
   - outsider-dominance guard
   - persistent-fragility-across-steps trigger

3. Receipt/route coherence
   - if route is `prefer-stable`, stable selection fields must be present
   - if route is `accept-fast`, fast selection fields must be present
   - if route is `abstain`, no substituted token may be claimed

4. Review route semantics, only after the review route exists in config

### What must stay out of Lean

Do not move these into Lean:

- floating-point truth
- proof that one numeric mode is mathematically “correct”
- human truth of the selected token
- discovery heuristics, ranking, or prompt mining
- JSON/file existence, artifact path existence, or hash computation
- full softmax/perplexity analysis over large vocab tensors

Those belong in schema validation, runtime tests, and bench analysis.

## Corpus promotion standard

### Strict

A case qualifies as `strict` when all of these are true:

- real prompt or real operator-family source
- explicit bounded answer set
- source state is stable across reruns
- exact/reference token is explicit
- forward/reverse/tree-style stable family agrees on the same bounded answer
- fast policy flips away from that answer
- no hidden top-prefix-only contamination

Strict is still corpus quality, not novelty.

### Broad

A case qualifies as `broad` when it is real and useful but misses one or more
strict conditions:

- semantically awkward wording
- top-prefix contamination
- broader/noisier answer surface
- stable/reference family is itself not human-right

Broad cases remain useful for coverage and negative controls.

### Control

A case qualifies as `control` when it defines where the wedge does not begin or
where naive “always prefer stable” behavior would be wrong:

- `accept-fast` control
- no-divergence control
- semantically embarrassing stable/reference control

Controls are required to keep the runtime contract honest.

## What must be exercised live before it counts as novelty

Novelty requires runtime exercise, not only corpus presence.

Minimum novelty bar:

1. Live runtime policy evaluation
   - registry loaded by runtime
   - no hidden bench-only decision logic

2. Live first-divergence receipt
   - emitted by the runtime trace surface

3. Live operator-local rerun
   - only the fragile operator rerun
   - not whole-model replay

4. Live governed route
   - `accept-fast`, `prefer-stable`, or `abstain`

5. Live proof-linked receipt
   - trigger and route proof links resolve to the active proof artifact

A promoted bench case without those runtime properties is not novelty.
It is a justified candidate.

## Blocking vs advisory

### Blocking now

- schema validity for numeric-stability registry
- schema validity for fragility-signature export
- proof artifact consistency for current trigger/route semantics
- promoted-case traceability:
  first divergence, digests, exact-reference match flags, route realization in
  promoted probe receipts

### Advisory now

- corpus size
- semantic “buyer legibility”
- prompt ranking quality
- browser promotion
- performance cost of the eventual runtime rerun path

### Blocking later, when runtime lands

- runtime registry loading
- runtime receipt completeness
- runtime route correctness
- runtime/operator-local rerun execution for enabled policies

These are now satisfied for the current native `matmul.logits` ordinary-
execution lane. The next blocking surfaces are:

- additional operator-family promotion
- ordinary package-caller exposure of the in-path rerun contract
- any future route-schema growth beyond the current taxonomy

## Recommended next implementation order

1. Keep
   [`config/numeric-stability-policy.json`](/Users/xyz/deco/doe/config/numeric-stability-policy.json)
   narrow while ordinary execution grows beyond `matmul.logits`.
2. Promote a second real operator family into native ordinary execution.
3. Expose the in-path rerun contract to ordinary package callers without
   hiding the policy boundary.
4. Prove any new route-to-selection semantics before adding new trigger
   families.
5. Treat `review-required` as a separate migration after the current
   `abstain` path is mature in native ordinary execution.
