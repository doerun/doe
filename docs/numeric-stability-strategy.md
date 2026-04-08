# Doe numeric-stability strategy

## Purpose

This document defines the part of numeric stability that matters to Doe's
product strategy rather than just to research.

The key distinction is:

1. observing and receipting numeric fragility
2. governing live execution because numeric fragility was detected

Doe already does the first in several forms. The strategy begins only when Doe
does the second as a runtime property.

## Current repo-true state

Doe already has:

1. a real fragility corpus
2. proof-linked route semantics
3. an explicit bounded-slice runtime/package service
4. a native ordinary-execution path for annotated `matmul.logits`
5. live `accept-fast`, `prefer-stable`, and `abstain` outcomes

Doe does not yet have:

1. automatic fragile-operator detection in ordinary execution
2. multiple live in-path operator families
3. a route that changes the committed downstream result of ordinary execution
4. ordinary package execution that inherits the native in-path behavior
5. browser-lane consumption of the same promoted runtime contract

That means the current state is:

1. a real runtime contract
2. a real product-shaped explicit service
3. not yet the full strategy

## The real distinction

The question is not:

1. can Doe detect a fragile operator?

The harder question is:

1. can Doe use that detection to govern what happens next in ordinary
   execution?

The strategy begins when the answer becomes yes.

## Route-effect ladder

## Level A: discovery

Behavior:

1. find prompt or operator cases that flip under legal numeric-policy changes
2. record first divergence and downstream token effects

Where this can live:

1. Doe
2. Doppler
3. PyTorch/Triton/CUDA research harnesses

Why it is not yet part of the strategy:

1. this is evidence work
2. it can be replicated outside Doe

## Level B: explicit runtime service

Behavior:

1. caller asks Doe to evaluate a bounded slice
2. Doe runs fast, stable, and reference policies
3. Doe returns a route decision and receipt

Current Doe status:

1. done for the explicit `matmul.logits` bounded-slice service

Why it matters:

1. it proves Doe can own the contract in a real runtime surface

Why it is still not yet enough for the strategy:

1. the caller opted in explicitly
2. this is not yet ordinary execution governance

## Level C: in-path runtime observation

Behavior:

1. an ordinary executed command is marked as numeric-stability-sensitive
2. Doe captures the live operands and fast output
3. Doe computes stable/reference locally
4. Doe emits a route and receipt

Current Doe status:

1. done for annotated native ordinary execution of `matmul.logits`

Why it matters:

1. the runtime is now part of the execution-time decision loop

Why it is still not the full strategy:

1. this path is annotation-gated
2. the route is still primarily observational unless the caller acts on it

## Level D: in-path execution governance

Behavior:

1. `accept-fast` commits the fast result and continues
2. `prefer-stable` commits the stable result into the live path
3. `abstain` prevents forced continuation and returns an explicit typed outcome

Current Doe status:

1. not yet complete

This is the first level that starts to look strategic because Doe is no longer
only describing fragility. It is changing what execution means.

## Level E: automatic fragile-operator detection

Behavior:

1. Doe identifies likely-fragile operators in ordinary execution without
   explicit per-command annotation
2. detection is bounded, schema-backed, and traceable

Current Doe status:

1. not yet done

Why it matters:

1. the feature starts to belong to ordinary callers, not just expert users

## Level F: multi-operator governance

Behavior:

1. the same route-effect contract works for more than one operator family
2. the runtime can localize and govern fragility earlier than the final LM head

Priority operator families:

1. `rmsnorm.output`
2. `attention.output`
3. softmax/layernorm-style reductions

Current Doe status:

1. not yet done for ordinary execution

## Level G: ordinary package adoption

Behavior:

1. normal `doe-gpu` execution APIs can surface or inherit the in-path contract
2. the feature is not limited to explicit service calls or repo-only runner
   shapes

Current Doe status:

1. explicit bounded-slice service is public
2. ordinary package execution does not yet inherit in-path governance

This is where the product strategy starts to become externally legible.

## Level H: browser-lane adoption

Behavior:

1. the same promoted contract is consumed by browser-facing Doe lanes
2. browser integration does not invent a separate numeric-stability system

Current Doe status:

1. target-state only

## What actually makes Doe hard to copy

The hard-to-copy part is not:

1. higher precision on selected operators
2. prompt hunts
3. alternate-kernel experiments
4. offline rerun analysis

The hard-to-copy part is:

1. runtime-owned numeric policy identity
2. runtime-emitted first-divergence receipts
3. operator-local rerun in ordinary execution
4. route effect on live execution
5. package and later browser adoption of the same contract
6. bounded overhead with explicit receipts and schemas

## Minimum strategy bar

Doe should not describe numeric stability as a core strategy until all of the
following are true:

1. at least one in-path route can affect downstream execution, not just emit a
   receipt
2. at least two operator families are governed in ordinary execution
3. ordinary package callers can consume the same contract
4. the runtime can detect candidate fragile operators without explicit
   per-command annotations
5. the resulting cost envelope is measured and bounded

Browser adoption strengthens the strategy further, but it is not required for
the first credible strategy claim.

## Product wording

## Safe current wording

**Doe already has a native ordinary-execution numeric-stability path for
annotated `matmul.logits`, plus an explicit bounded-slice runtime/package
service with proof-linked route receipts.**

## Safe next wording

**Doe can govern selected numerically fragile operators during ordinary
execution by rerunning only the sensitive path under a stronger policy and
either committing the governed result or abstaining with a receipt.**

Use this only after route effect on live execution is real.

## Strong strategy wording

**Doe is the WebGPU runtime that governs numeric fragility for ordinary
callers: it detects fragile operators, reruns only the sensitive path under a
declared policy, and commits or abstains with a proof-linked receipt.**

Use this only after:

1. route effect is live
2. multiple operator families are live
3. ordinary package callers inherit the behavior

## Demo bar

A strategy-grade demo set should include:

1. one live `prefer-stable` case where the route affects execution
2. one live `accept-fast` case where the runtime explicitly keeps the fast path
3. one live `abstain` case that prevents a forced winner
4. one buyer-legible prompt case
5. one semantically embarrassing control case
6. at least one second operator family beyond `matmul.logits`

## What stays outside Doe

These are useful but do not define the strategy:

1. search over prompt rewrites
2. prefix/suffix exploration
3. semantic-envelope experimentation
4. policy-beam or decode-mixing research prototypes
5. corpus ranking and clustering

Those may feed Doe. They do not replace the runtime boundary.
