# Doe numeric-stability runtime roadmap

## Purpose

This document defines the integration/product/claim path for Doe numeric
stability.

It exists to answer four questions:

1. What is true today?
2. What would actually make Doe novel?
3. What work belongs in Doe rather than Doppler or a research harness?
4. What is the staged path from current bench evidence to a real runtime
   feature?

The current evidence base lives in:

- [`docs/status.md`](./status.md)
- [`bench/README.md`](../bench/README.md)
- [`config/numeric-stability-policy.json`](../config/numeric-stability-policy.json)
- [`config/numeric-stability-policy.schema.json`](../config/numeric-stability-policy.schema.json)
- [`pipeline/lean/Doe/Core/NumericStabilityPolicy.lean`](../pipeline/lean/Doe/Core/NumericStabilityPolicy.lean)

## Current truth

Doe already has real numeric-fragility evidence.

It can currently show:

1. micro floating-point divergence under different accumulation policies
2. operator-level selected-token drift under different numeric policies
3. prompt-level bounded-answer flips on real prompt states
4. a proof-linked route decision in bench/probe land

The current best evidence chain is:

1. the real red-light `go/stop` flagship in [`docs/status.md`](./status.md)
2. the real `rmsnorm` `accept-fast` control in [`docs/status.md`](./status.md)
3. the attention negative control in [`docs/status.md`](./status.md)
4. the normalized fragility corpus export in [`bench/README.md`](../bench/README.md)

The current numeric-stability contract is real but narrow:

1. route outcomes are only:
   - `accept-fast`
   - `prefer-stable`
   - `abstain`
2. one trigger family and one routing family are currently defined
3. route evaluation now exists in both:
   - bench/probe flows for promoted cases
   - native ordinary execution for annotated `matmul.logits`

The current public/package determinism surface is also real but separate:

1. `stableToken`
2. `stableChoice`
3. `reviewedChoice`

as documented in [`packages/doe-gpu/README.md`](../packages/doe-gpu/README.md)
and implemented under
[`packages/doe-gpu/src/vendor/`](../packages/doe-gpu/src/vendor/).

## What is not novel enough

The following are useful, but not sufficient to make Doe novel by themselves:

1. finding prompts that flip under alternate math policies
2. comparing logits under `f16` and `f32`
3. bounded-answer-set slicing
4. higher-precision reruns in an offline harness
5. charts over surprisal, margin, and flips
6. proof-linked receipts without broader runtime/package adoption across
   operator families

Those can be reproduced in principle by:

1. Doppler
2. PyTorch
3. Triton
4. CUDA
5. a JS/WebGPU research harness

The corpus is evidence. It is not the moat.

## The novelty bar

Doe becomes novel when numeric fragility stops being a bench artifact and
becomes a live runtime-enforced, receipted, proof-linked control surface.

The target capability is:

1. the runtime detects a numerically fragile decision boundary
2. it localizes first divergence to a named operator family
3. it reruns only the fragile operator under a stronger declared numeric policy
4. it returns a governed route decision from the real runtime path
5. it emits versioned receipts that tie route semantics to config and proof

The concise product thesis is:

**Doe is a WebGPU runtime that can detect numerically fragile decisions, rerun
only the fragile operator under a stronger declared policy, and return a
receipted route decision.**

## What must belong to Doe

The defensible Doe boundary is the runtime boundary, not the hunt boundary.

### Doppler or research-harness work

The following can happen outside Doe:

1. prompt discovery
2. prompt-state harvesting
3. operator-sensitivity experiments
4. bounded-answer ranking and filtering
5. fragility-corpus construction
6. exploratory selective-rerun analysis

That work is still useful. It seeds the evidence base.

### Doe-only moat work

The following must land in Doe to become defensible:

1. runtime-level numeric policy IDs
2. runtime-emitted first-divergence receipts
3. operator-local rerun in the live execution path
4. route decisions executed by the runtime, not a post-hoc probe
5. package-facing APIs that expose the contract to ordinary callers
6. eventual browser-lane consumption of the same core contract

The clean rule is:

**Use other tooling to discover cases. Use Doe to govern them.**

## Current repo gap

The current gap is structural:

1. config exists
2. proof exists
3. evidence exists
4. explicit bounded-slice runtime enforcement exists
5. native ordinary-execution operator-local rerun now exists for annotated
   `matmul.logits`
6. package/browser ordinary execution still do not consume that path

More specifically:

1. there is now a Zig-side bounded-slice runtime consumer of
   [`config/numeric-stability-policy.json`](../config/numeric-stability-policy.json)
2. there is now a native numeric-stability receipt and trace-meta summary path
3. there is now a public `doe-gpu` numeric-stability API for the bounded
   `matmul.logits` slice service
4. there is now a native ordinary-execution rerun path in `runtime/zig` for
   annotated `matmul.logits`
5. ordinary package callers do not yet get that in-path behavior
6. the current flagship is still parity evidence on Doe and Dawn, not a Doe-only
   runtime behavior claim

## Public claim ladder

Claims must stay below the current implementation boundary.

### True now

1. Doe has a real numeric-fragility corpus.
2. Doe can localize first divergence in promoted bench cases.
3. Doe has a proof-linked numeric-stability route contract in bench/probe land.
4. Doe has at least one real prompt/operator/rerun flagship case.
5. Doe has an explicit Zig/package bounded-slice numeric-stability service with
   receipted route decisions.
6. Doe has native ordinary-execution `runtime-exercised` cases for
   `matmul.logits`.

### True after operator-local runtime v1

1. Doe runtime can emit numeric-stability receipts.
2. Doe runtime can rerun one sensitive operator family under a stronger policy.
3. Doe can enforce `accept-fast`, `prefer-stable`, and `abstain` in a live path.

This is now true for native `matmul.logits`.

### True only later

1. browser-lane numeric-stability enforcement
2. broader operator-family coverage
3. ordinary package-caller exposure of the in-path rerun feature
4. multiple trigger families
5. `review-required` as a live route, if schema and proof migrate to support it

### Do not claim yet

1. that Doe is more correct than Dawn
2. that stable/reference math is semantically true
3. that Chromium/browser replacement is already a shipped capability
4. that `review-required` is a current numeric-stability runtime route

## v1 target

The first real product milestone was deliberately narrow and is now landed in
native runtime.

### Scope

1. one operator family:
   - `matmul.logits`
2. one live runtime contract:
   - runtime-loaded numeric-stability policy
3. one receipt family:
   - first divergence
   - fast/stable policy IDs
   - selected-token comparison
   - route decision
4. one package exposure in `doe-gpu`

### Why `matmul.logits` first

1. it already has the best promoted real prompt evidence
2. it has a clear bounded-answer interpretation
3. it keeps the first live rerun small
4. it is easy to explain in the product story

Native status:

1. ordinary-execution rerun is now live in `doe-zig-runtime`
2. explicit bounded-slice service remains the package-facing `doe-gpu` surface

## Roadmap

## Phase 0: freeze the evidence base

Goal: make the current corpus stable enough to promote into runtime work.

Deliver:

1. one canonical fragility-signature row shape
2. one canonical split:
   - strict
   - broad
   - top-prefix-only
   - operator/control
3. one promoted starter set for runtime v1

Exit bar:

1. the runtime track can point at a stable promoted case set
2. the policy track can define route semantics against a stable corpus

## Phase 1: define the runtime receipt contract

Goal: create a runtime-native numeric-stability receipt shape.

Minimum fields:

1. numeric policy IDs for fast and stable paths
2. operator family
3. first divergent operator
4. fast/stable digests
5. selected token(s)
6. exact-reference match flags where applicable
7. route decision
8. proof links

Exit bar:

1. runtime and package can serialize the same receipt contract
2. trace/trace-meta can carry numeric-stability receipts without piggybacking on
   determinism-only fields

## Phase 2: load policy in the runtime

Goal: make `runtime/zig` evaluate the numeric-stability registry directly.

Deliver:

1. Zig-side policy loader
2. trigger evaluation in runtime terms
3. route evaluation in runtime terms

Exit bar:

1. the route is no longer computed only by
   [`run_selective_stable_rerun_probe.py`](../bench/runners/run_selective_stable_rerun_probe.py)

## Phase 3: ship one live operator-local rerun

Goal: run the first real selective-rerun loop inside the live execution path.

Deliver:

1. sensitive-operator detection for `matmul.logits`
2. bounded capture of the relevant slice
3. stable rerun of only that slice
4. route evaluation and receipt emission

Constraints:

1. no full-model rerun
2. no hidden fallback behavior
3. no browser-only special path

Exit bar:

1. one real live runtime path can return a numeric-stability receipt

Status:

1. done for native annotated `matmul.logits`
2. remaining work is broader operator families and ordinary package-caller
   exposure

## Phase 4: expose it in `doe-gpu`

Goal: make numeric stability visible to package callers as a first-class
runtime capability.

Deliver:

1. public API surface
2. TypeScript types
3. package docs
4. one minimal example

The design should parallel the current determinism helpers, but it should not
pretend numeric-stability is the same thing as `stableToken` or `stableChoice`.

Exit bar:

1. a package caller can invoke Doe runtime and receive a numeric-stability
   receipt without bench tooling

Status:

1. done for the explicit bounded-slice service
2. not yet done for ordinary-execution operator-local rerun

## Phase 5: grow policy and proof

Goal: evolve past the current minimal trigger family without losing rigor.

Candidate additions:

1. multiple trigger families
2. explicit fragility-signature modes
3. adapter/driver fragility fingerprints
4. optional route growth beyond `accept-fast`, `prefer-stable`, `abstain`

This phase must stay schema-first.

If `review-required` is introduced later, it must land through:

1. schema migration
2. registry migration
3. Lean route-proof expansion
4. package/runtime receipt updates

## Phase 6: browser promotion

Goal: make the browser lane consume the same promoted runtime contract.

This comes last.

Nothing in [`browser/chromium/README.md`](../browser/chromium/README.md)
currently justifies a live browser claim here. Browser work should consume the
core contract only after `runtime/zig` and `doe-gpu` have promoted it.

## Demo ladder

The first live demo set should prove three things:

1. the runtime can prefer stable when stable is better
2. the runtime can keep fast when stable is worse
3. the runtime can abstain when the route contract says not to force a winner

### Starter set

1. `prefer-stable`
   - red traffic light `go/stop`
2. `accept-fast`
   - `rmsnorm` control
3. `abstain`
   - first live abstain case after the runtime route path exists

### Expansion set

After v1, promote a broader, honest set:

1. buyer-legible danger cases
2. semantically embarrassing cases where stable/reference is still wrong
3. explicit negative controls

The second category matters. It proves Doe governs consistency, not truth.

## Performance and explosion control

Numeric stability must not turn into “rerun everything.”

The runtime path should be bounded by design:

1. trigger only on selected sensitive operator families
2. trigger only on bounded answer slices or selected top-K contexts
3. use bounded readback
4. rerun only the fragile operator or local suffix
5. keep the default path fast and explicit

This is the difference between a runtime feature and a research harness.

## Definition of done for runtime v1

Runtime v1 is done when all of the following are true:

1. Doe runtime loads numeric-stability policy directly from config.
2. Doe runtime emits a numeric-stability receipt with first-divergence data.
3. Doe runtime can rerun one real operator family locally.
4. `doe-gpu` exposes a public numeric-stability API.
5. one live `prefer-stable` case exists.
6. one live `accept-fast` case exists.
7. one live `abstain` case exists.
8. docs and receipts distinguish current truth from target state cleanly.

At that point, the novelty claim becomes credible:

**Doe is not just a harness that finds numeric fragility. It is a WebGPU
runtime that can govern it.**
