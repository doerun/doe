# Numeric stability auto-detection plan

## Purpose

This document is the B-track runtime-first plan for moving Doe from the live
ordinary-execution trio toward broader automatic fragility detection and
bounded rerun across additional operator families.

It is intentionally narrower than the product/moat claim documents.

Use it for:

1. automatic fragility detection design
2. operator-family expansion order
3. bounded capture and rerun design
4. suffix replay strategy
5. overhead budgeting
6. auto-detected operator expansion

Planning surfaces:

- [`config/numeric-stability-auto-detection-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-auto-detection-plan.json)
- [`config/numeric-stability-operator-expansion-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-operator-expansion-plan.json)

These are planning-first config surfaces. The live runtime now consumes the
core auto-detect registry, but the ranked expansion and budgeting surfaces
remain planning guidance.

## Current truth

Native ordinary execution already supports auto-detected numeric-stability
capture and routing in:

- [`runtime/zig/src/numeric_stability_runtime.zig`](/Users/xyz/deco/doe/runtime/zig/src/numeric_stability_runtime.zig)
- [`runtime/zig/src/numeric_stability_annotation.zig`](/Users/xyz/deco/doe/runtime/zig/src/numeric_stability_annotation.zig)
- [`runtime/zig/src/command_stream.zig`](/Users/xyz/deco/doe/runtime/zig/src/command_stream.zig)

Current live ordinary-execution families:

1. `matmul.logits`
2. `rmsnorm.output`
3. `attention.output`

That path is real, but still narrow:

1. it only covers the configured live trio
2. the next operator families are still planning-only
3. it does not yet auto-detect arbitrary fragile operators outside the
   configured profiles
4. workflow-level defaults still need to be hardened into clearer execution
   profiles and measured device policy

The next step is not “more prompt hunts.” It is a config-backed runtime path
for deciding:

1. which operators are worth watching
2. when the runtime should escalate from observation to rerun
3. how much extra work is allowed
4. when the runtime should abstain instead of paying more cost

## Detection path

The recommended detection path is staged.

### Stage 1: explicit capture override

Historical foundation:

1. the command explicitly declares the bounded capture set
2. the runtime captures and evaluates it
3. the runtime emits a live receipt and route

This stage proves the contract shape.

### Stage 2: auto-detect ordinary execution

Current truth:

1. the runtime chooses the detection profile from config for supported
   ordinary-execution operators
2. the runtime rewrites the committed result for `prefer-stable`
3. the runtime can stop the downstream command suffix for `abstain`

This stage is already real for:

1. `matmul.logits`
2. `rmsnorm.output`
3. `attention.output`

### Stage 3: profile hardening and measured defaults

Next step:

1. the runtime keeps the same live trio
2. ordinary execution selects a named execution profile from config
3. route choice becomes an explicit surface:
   - default
   - cautious
   - observe-only
4. package/native callers can measure profile choice, route mix, and device
   fragility before widening the operator set

This keeps behavior explainable while moving defaults out of code and into
config-visible policy.

### Stage 4: next operator expansion

Next step:

1. the runtime chooses the next operator family automatically
2. it performs only the bounded rerun allowed by the profile
3. it returns `accept-fast`, `prefer-stable`, or `abstain`

This is the clean path from a live trio to a broader runtime-governance
portfolio.

### Stage 5: suffix replay assisted

Later step:

1. operator-local rerun remains the default
2. short suffix replay activates only for families where operator-local
   rerun does not explain the semantic effect well enough
3. replay windows stay bounded by config budget

This stage is for attention-like families, not the default path.

## Detection signals

The runtime should combine multiple signals instead of pretending one scalar is
enough.

The canonical signal set is:

1. operator family
2. bounded margin
3. reference surprisal
4. outsider lead
5. fast/stable disagreement
6. persistence across adjacent decode steps
7. device and kernel identity

The important design rule is:

1. margins and surprisal tell you the decision boundary is brittle
2. fast/stable disagreement tells you numeric policy already matters
3. persistence tells you the effect is not a one-step fluke
4. device and kernel identity lets Doe learn host-specific fragility without
   hidden runtime folklore

Current proposed thresholds and stage bindings live in:

- [`config/numeric-stability-auto-detection-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-auto-detection-plan.json)

## Ranked operator expansion

The current live trio is already in place:

1. `matmul.logits`
2. `rmsnorm.output`
3. `attention.output`

The next ranked operator families after the live trio are:

1. `softmax.denominator`
2. `layernorm.output`
3. `mlp.output`
4. `residual.add`
5. `task-head.score`

Reasoning:

### 1. `softmax.denominator`

Why first:

1. it is a classic numeric cliff with a clear semantic explanation
2. it broadens Doe beyond norm and projection operators
3. the bounded normalization story stays honest without full replay

### 2. `layernorm.output`

Why second:

1. it reuses much of the live `rmsnorm.output` machinery
2. it is cheaper to land than MLP or residual expansion
3. it keeps the next implementation step operationally straightforward

The current ranking and capture assumptions live in:

- [`config/numeric-stability-operator-expansion-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-operator-expansion-plan.json)

## Bounded capture and rerun design

The runtime should keep the same discipline as the current `matmul.logits`
path:

1. capture only the operands needed for the candidate operator
2. rerun only that operator by default
3. compare the smallest semantic object that still explains the decision
4. never default to full-model rerun

Recommended bounded capture shapes:

### `matmul.logits`

Capture:

1. hidden-state vector
2. bounded candidate weight rows
3. fast logits buffer

Rerun:

1. single operator
2. stable serial path
3. optional CPU reference path

### `rmsnorm.output`

Capture:

1. pre-norm activation window
2. scale vector
3. fast output window

Rerun:

1. single operator over the bounded normalization window
2. stable serial path
3. optional CPU reference path

### `attention.output`

Capture:

1. bounded score window
2. bounded value window
3. fast output window

Rerun:

1. operator-local first
2. bounded suffix replay only if operator-local drift persists

## Checkpoint and suffix replay strategy

Suffix replay is not the default answer. It is the escalation path when
operator-local rerun is too local to explain downstream semantic movement.

The preferred order is:

1. single-operator rerun
2. single-operator plus one-step sample check
3. short suffix replay

Checkpoint sources should be prioritized this way:

1. semantic trace capture already emitted by the runtime
2. explicit capture ledger emitted by the monitored operator family
3. later, a future checkpoint format if Doe adds one

The suffix window should stay tiny:

1. one token for norm families
2. one or two tokens for attention families
3. no unbounded replay in the automatic path

Current proposed replay windows and fallback routes live in:

- [`config/numeric-stability-auto-detection-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-auto-detection-plan.json)

## Overhead budget

Automatic detection only becomes believable if cost is bounded up front.

The runtime should budget:

1. bytes read back
2. extra operator reruns
3. activation frequency
4. fallback route when budget is exceeded

The default bias should be conservative:

1. if the budget is exceeded, prefer `abstain`
2. only keep `accept-fast` as the budget fallback where the operator family is
   already known to be low-risk and the rerun window is tiny

That keeps the cost model honest and stops auto-detection from quietly turning
into “rerun everything.”

The proposed budget envelope lives in:

- [`config/numeric-stability-auto-detection-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-auto-detection-plan.json)

## Migration path from the live trio to broader auto-detection

The migration path should be:

1. keep `matmul.logits`, `rmsnorm.output`, and `attention.output` as the live
   reference implementations
2. harden default versus cautious versus observe-only execution profiles
3. measure trigger quality and per-device fragility before widening
4. add `softmax.denominator`
5. add `layernorm.output`
6. widen into MLP, residual, and task-head families only after the cheaper
   next operators are measured

Blocking requirements at each stage should remain config-visible and route
taxonomy should stay unchanged. This work should not invent new live routes.

## Smallest genuinely new next step

The smallest next step that feels materially new is:

1. make ordinary-execution defaults fully config-backed through named
   execution profiles
2. publish measured route quality and overhead for the live trio
3. land `softmax.denominator` as the next ranked operator family
4. keep rerun bounded to one operator and the existing live route taxonomy

That would move Doe from:

1. a real but still narrow live trio

to:

1. a productized default/configurable policy surface
2. a broader operator portfolio
3. a more credible runtime-governance story for ordinary execution
