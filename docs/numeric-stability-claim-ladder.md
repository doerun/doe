# Doe numeric-stability claim ladder

## Purpose

This document defines the canonical claim ladder for Doe numeric stability.

Use it to separate:

1. what the repo proves today
2. what the repo is targeting next
3. what we should not claim yet
4. what belongs to Doe rather than a discovery harness

## Core statement

The correct high-level statement is:

**Doe is not just a harness that finds numeric fragility. Doe is trying to
become the WebGPU runtime that can govern it.**

That distinction matters because the examples alone are not the moat.

## Claim ladder

## Level 0: phenomenon exists

Safe claim:

1. floating-point and accumulation-policy choices can change bytes
2. those changes can propagate into operator outputs
3. those changes can propagate into selected-token differences

This level is necessary but not differentiating.

## Level 1: Doe has evidence

Safe claim:

1. Doe has a real numeric-fragility corpus
2. Doe can show real prompt-level bounded-answer flips
3. Doe can trace promoted cases to named operator families and numeric policies

This is where the current corpus sits.

## Level 2: Doe has governed bench contracts

Safe claim:

1. Doe has a proof-linked numeric-stability route contract
2. Doe can evaluate `accept-fast`, `prefer-stable`, or `abstain` in a promoted
   probe flow
3. Doe can show first divergence, fast/stable comparison, and route results in
   bench artifacts

This remains true and still matters for cases that are not yet live in
ordinary execution.

## Level 3: Doe has a live runtime contract

Safe claim:

1. Doe runtime loads numeric-stability policy directly from config
2. Doe runtime emits first-divergence receipts
3. Doe runtime reruns one sensitive operator family locally
4. Doe runtime returns a governed route decision in the live path

This is now true for native ordinary execution of auto-detected
`matmul.logits` `kernel_dispatch` commands.

Important caveat:

1. the current live path proves in-path rerun plus route effect for one
   operator family
2. it does not yet prove automatic ordinary-execution governance for generic
   callers across multiple operator families

## Level 4: Doe has in-path execution governance

Safe claim only after route effect becomes real:

1. `accept-fast` explicitly keeps the fast result in the live path
2. `prefer-stable` can commit the stable result into the live path
3. `abstain` can prevent forced continuation and return an explicit governed
   outcome

This is the first level that starts to look like a moat rather than a runtime
measurement feature.

## Level 5: Doe has a package/runtime product surface

Safe claim:

1. `doe-gpu` exposes numeric-stability as a first-class runtime capability
2. the explicit bounded-slice service is versioned, schema-backed, and
   proof-linked
3. package callers can get numeric-stability receipts without bench tooling for
   that explicit service

What is not yet true at this level:

1. ordinary package callers do not yet get the native in-path operator-local
   rerun path automatically
2. package execution surfaces do not yet apply ordinary-execution
   numeric-stability capture automatically to arbitrary callers

This is the current product-shape claim boundary for the explicit bounded-slice
service, not for ordinary execution generally.

## Level 6: Doe has browser-lane adoption

Safe claim only after core promotion and browser consumption:

1. the same numeric-stability contract can be consumed by browser-facing Doe
   lanes
2. browser integration uses the same promoted runtime contract rather than a
   separate browser-only implementation

This is target-state, not current-state.

## What we should claim now

We should currently claim only:

1. Doe has a real numeric-fragility evidence base.
2. Doe has a proof-linked numeric-stability route contract in bench/probe land.
3. Doe has a native ordinary-execution numeric-stability path for
   auto-detected `matmul.logits` execution in `doe-zig-runtime`.
4. Doe has both:
   - an explicit bounded-slice runtime/package numeric-stability service
   - an explicit package helper for ordinary-execution numeric-stability
     receipts
5. Doe has real prompt/control cases that are `runtime-exercised` in native
   ordinary execution.
6. Doe does not yet claim moat-level execution governance for ordinary
   automatic callers.

## What we should not claim yet

We should not currently claim:

1. that Doe is already more correct than Dawn
2. that stable/reference math is semantically true
3. that browser replacement is already a shipped numeric-stability feature
4. that `review-required` is part of the live numeric-stability route contract
5. that generic package callers already get ordinary-execution operator-local
   rerun automatically
6. that the flagship case is a Doe-vs-Dawn divergence today
7. that every current in-path route changes the committed downstream result

## Doe versus Doppler

The clean split is:

### Doppler or other research harnesses can do

1. prompt discovery
2. prompt-state harvesting
3. kernel-path exploration
4. bounded-answer filtering
5. fragility-corpus construction
6. offline selective-rerun experiments

### Doe must do

1. runtime-level numeric policy IDs
2. runtime-emitted first-divergence receipts
3. live operator-local rerun
4. governed route decisions in the execution path
5. route effect on live execution
6. package-facing runtime APIs for the feature

That is the actual defensible boundary.

## Public product thesis

The shortest credible product line is:

**Doe is a WebGPU runtime that can detect numerically fragile decisions, rerun
only the fragile operator under a stronger declared policy, and govern the
live outcome with a receipted route decision.**

That sentence is the target moat wording. It is not yet fully true today for
generic package callers, browser lanes, or general in-path route effect.

Until then, the safer internal wording is:

**Doe now has a native ordinary-execution `matmul.logits` numeric-stability
path plus an explicit bounded-slice runtime/package service, and the remaining
promotion work is live route effect, broader operator coverage, and
package/browser consumption of the same core contract.**
