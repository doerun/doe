# Doe semantic-envelope design memo

## Purpose

This memo owns the semantic-envelope / decode-mixing track for Doe numeric
stability.

It does **not** revisit plain determinism. It starts from current Doe truth:

1. Doe already has a real numeric-fragility corpus.
2. Doe already has proof-linked `accept-fast`, `prefer-stable`, and `abstain`
   routes.
3. Doe already has an explicit bounded-slice runtime/package service for
   `matmul.logits`.
4. Doe already has a native in-path `matmul.logits` path for annotated
   ordinary execution.

The A-track question is different:

**What semantic object should Doe compute once a fragile runtime boundary has
already been found?**

The target is not “more flips.” The target is:

**Given legal prompt/prefix/kernel/decode variations around one fragile
boundary, what semantic classes are actually reachable, and how wide is that
reachable set?**

## Current boundary

Current Doe receipts answer a first-order question:

1. what fast selected
2. what stable selected
3. what reference selected
4. where first divergence happened
5. which route fired

That is necessary, but it compresses a richer space into one route decision.

The semantic-envelope proposal adds a second-order object:

1. which legal views were explored
2. which semantic classes were reachable across those views
3. whether the reachable set is singleton, split, or outsider-dominated
4. whether the route stays stable across short nearby decode windows

This object should remain:

1. runtime-first in shape, even when first explored offline
2. route-taxonomy-preserving
3. explicit about cost
4. explicit that stable/reference does not mean true

## Proposed semantic envelope artifact

### Core terms

**View**

One legal perspective on the same decision boundary.

Examples:

1. full prefill + fast kernel
2. full prefill + stable kernel
3. truncated prefix + stable kernel
4. full prefill + stable kernel + decode[1]
5. full prefill + stable kernel + global top-K context

**Semantic class**

A runtime-declared class that collapses token-level or wording-level variation
into the thing the user or policy actually cares about.

Examples:

1. `go` / `stop`
2. `approve` / `deny`
3. `allow` / `block`
4. `public` / `private`
5. `safe` / `unsafe`

**Semantic envelope**

The set of semantic classes reachable across a bounded set of legal views
anchored to one triggered fragile boundary.

### Envelope states

The summary state should be one of:

1. `singleton`
   Every explored view collapses to the same semantic class.
2. `split`
   More than one semantic class is reachable across explored views.
3. `outsider-dominated`
   The bounded pair/class view is unstable because one or more explored views
   show a global outsider leading the pair.

`outsider-dominated` should take precedence over `split`, because it means the
bounded answer surface itself is not faithfully containing the live decision.

### Why this object is useful

It lets Doe say something stronger than:

1. “fast said X”
2. “stable said Y”

It lets Doe say:

1. “under the legal numeric/runtime views we actually explored, only `stop` is
   reachable”
2. “under those views, both `allow` and `block` are reachable”
3. “under those views, the pair itself is unstable because outsiders keep
   winning”

That is a more honest and more productizable surface than raw logit drift.

## View families to formalize

The envelope should treat the search space as **axes**, not one giant Cartesian
product.

### Prompt/prefix axis

1. `prefill/full`
2. `prefill/truncated-prefix`
3. `prompt/semantic-rewrite`

### Decode axis

1. `decode/prefill-only`
2. `decode/prefill-plus-1`
3. `decode/short-suffix-replay`

### Numeric/runtime axis

1. `policy/fast`
2. `policy/stable`
3. `policy/reference`
4. later, additional legal kernel variants per operator family

### Candidate-context axis

1. `context/bounded-answer-set`
2. `context/bounded-answer-set-plus-topk`
3. `context/global-topk-collapse`

## Non-combinatorial algorithms

The rule is:

**Branch only when fragility triggers, then collapse immediately by semantic
class.**

### Algorithm 1: policy-beam decode with semantic collapse

Purpose:

1. cheaply answer “what semantic classes are reachable?”
2. avoid exploding into token-level beams that mostly differ only in wording

Method:

1. Start from one triggered numeric-stability receipt.
2. Build a tiny beam over legal views:
   - fast
   - stable
   - reference
   - optional truncated-prefix witness
   - optional prompt rewrite witness
3. Decode only until:
   - the semantic class is determined
   - a short step budget is exhausted
   - or the branch is outsider-dominated
4. Immediately collapse all branches that map to the same semantic class.
5. Keep only:
   - the cheapest witness for that class
   - the strongest-support witness for that class
   - aggregate support stats for the class

Why this is not just another beam search:

1. the branching condition is the runtime fragility trigger
2. the beam unit is semantic class, not raw token string
3. the stop rule is semantic collapse, not decode length

### Algorithm 2: semantic barycenter across views

Purpose:

1. summarize a split envelope without pretending one numeric policy is truth
2. expose whether the disagreement is fragile but narrow, or structurally wide

Method:

1. For each view, derive a class-level distribution from:
   - bounded answer logits
   - or bounded answer + outsider context
2. Weight each view by explicit, receiptable factors:
   - prompt fidelity
   - prefix fidelity
   - outsider dominance penalty
   - decode-step distance penalty
3. Compute a class barycenter across views.
4. Emit:
   - dominant class if one exists
   - barycenter gap
   - envelope width
   - whether the barycenter still supports the current route

Why this matters:

1. it avoids treating the reference lane as truth
2. it gives a compact class-level summary for abstain-friendly cases
3. it creates a useful object even when the runtime should not auto-substitute

## Proposed receipt/schema extension

This should be an **optional** extension on top of the existing numeric
stability receipt, not a replacement for it.

The clean path is:

1. keep the current receipt as the first-order artifact
2. attach an optional `semanticEnvelope` block when the envelope is computed
3. leave route taxonomy unchanged

### Proposed extension field

Extend [`config/doe-numeric-stability-receipt.schema.json`](../config/doe-numeric-stability-receipt.schema.json)
with an optional `semanticEnvelope` object.

Suggested shape:

```json
"semanticEnvelope": {
  "type": "object",
  "required": [
    "schemaVersion",
    "classSetId",
    "classSetSource",
    "triggerAnchor",
    "summary",
    "classes",
    "views"
  ],
  "properties": {
    "schemaVersion": { "const": 1 },
    "classSetId": { "type": "string", "minLength": 1 },
    "classSetSource": { "type": "string", "minLength": 1 },
    "triggerAnchor": {
      "type": "object",
      "required": ["semanticOpId", "routeDecision", "receiptPath"],
      "properties": {
        "semanticOpId": { "type": "string", "minLength": 1 },
        "routeDecision": {
          "type": "string",
          "enum": ["accept-fast", "prefer-stable", "abstain"]
        },
        "receiptPath": { "type": "string", "minLength": 1 }
      },
      "additionalProperties": false
    },
    "summary": {
      "type": "object",
      "required": [
        "status",
        "width",
        "reachableClassIds",
        "classAgreementRate",
        "outsiderDominatedViewCount",
        "routeStableAcrossAdjacentDecodeSteps",
        "incrementalCost"
      ],
      "properties": {
        "status": {
          "type": "string",
          "enum": ["singleton", "split", "outsider-dominated"]
        },
        "width": { "type": "integer", "minimum": 1 },
        "reachableClassIds": {
          "type": "array",
          "minItems": 1,
          "items": { "type": "string", "minLength": 1 },
          "uniqueItems": true
        },
        "classAgreementRate": { "type": "number" },
        "outsiderDominatedViewCount": { "type": "integer", "minimum": 0 },
        "routeStableAcrossAdjacentDecodeSteps": { "type": "boolean" },
        "incrementalCost": {
          "type": "object",
          "required": ["additionalViews", "additionalDecodeSteps", "bytesReadBack"],
          "properties": {
            "additionalViews": { "type": "integer", "minimum": 0 },
            "additionalDecodeSteps": { "type": "integer", "minimum": 0 },
            "bytesReadBack": { "type": "integer", "minimum": 0 }
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "classes": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": ["classId", "supportCount", "bestWitnessViewId"],
        "properties": {
          "classId": { "type": "string", "minLength": 1 },
          "supportCount": { "type": "integer", "minimum": 1 },
          "bestWitnessViewId": { "type": "string", "minLength": 1 },
          "dominantPolicies": {
            "type": "array",
            "items": { "type": "string", "minLength": 1 },
            "uniqueItems": true
          }
        },
        "additionalProperties": false
      }
    },
    "views": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "viewId",
          "promptView",
          "decodeView",
          "numericView",
          "contextView",
          "reachableClassIds",
          "selectedClassId",
          "boundedMarginProbability",
          "referenceSurprisalNats",
          "outsiderLeadVsPairMaxLogit",
          "outsiderDominatesPair"
        ],
        "properties": {
          "viewId": { "type": "string", "minLength": 1 },
          "promptView": { "type": "string", "minLength": 1 },
          "decodeView": { "type": "string", "minLength": 1 },
          "numericView": { "type": "string", "minLength": 1 },
          "contextView": { "type": "string", "minLength": 1 },
          "reachableClassIds": {
            "type": "array",
            "minItems": 1,
            "items": { "type": "string", "minLength": 1 },
            "uniqueItems": true
          },
          "selectedClassId": { "type": "string", "minLength": 1 },
          "boundedMarginProbability": { "type": "number" },
          "referenceSurprisalNats": { "type": "number" },
          "outsiderLeadVsPairMaxLogit": { "type": "number" },
          "outsiderDominatesPair": { "type": "boolean" }
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
```

Companion sample:

- [`examples/doe-semantic-envelope-receipt.sample.json`](../examples/doe-semantic-envelope-receipt.sample.json)

### Why this extension is the right size

It adds exactly one new concept:

1. a bounded set of legal views around one fragile boundary

It does **not**:

1. change the route taxonomy
2. claim truth
3. force browser work
4. require full-model replay by default

## Evaluation metrics

The envelope needs metrics that are meaningful both offline and later in the
runtime.

### 1. Semantic envelope width

Number of reachable semantic classes across explored views.

Interpretation:

1. `1` means singleton
2. `>1` means split

### 2. Class agreement rate

Fraction of explored views that collapse to the same dominant class.

Interpretation:

1. high agreement with width `1` is the strongest singleton
2. low agreement with width `2` is a true split

### 3. Outsider lead

Use the existing corpus-style outsider metric to record whether the bounded pair
is actually containing the decision.

Interpretation:

1. negative lead means the pair is still governing
2. positive lead means outsiders are pressuring or dominating the pair

### 4. Bounded margin

Use the existing bounded pair/class probability margin.

Interpretation:

1. small margin means a narrow class boundary
2. larger margin with a split means the disagreement is structural, not just
   near-tie noise

### 5. Route stability across adjacent decode steps

Does the class-level route stay stable when expanding from prefill-only to
`prefill + decode[1]`, or a short suffix replay window?

Interpretation:

1. stable route means the boundary is local and well-contained
2. unstable route means the envelope is temporally wide

### 6. Incremental cost

Track:

1. added views
2. added decode steps
3. bytes read back
4. additional rerun compute

This is necessary because the envelope is only useful if it can later live near
the runtime boundary.

## Case set for the first semantic-envelope pass

The first pass should use **10 real Doe cases**.

### Headline-safe

1. **At a red traffic light, cars should**
   - current state: strict, runtime-exercised, `prefer-stable`
   - reason: pair-dominated flagship with negative outsider lead
2. **Revoking access for a departed employee should be**
   - current state: strict, runtime-exercised, `prefer-stable`
   - reason: buyer-legible policy boundary with negative outsider lead
3. **Emergency SSH from the approved bastion host should**
   - current state: strict, runtime-exercised, `prefer-stable`
   - reason: buyer-legible, but outsider-dominated; good envelope stress
4. **A public open-source README should remain**
   - current state: strict, runtime-exercised, `prefer-stable`
   - reason: public/private class boundary with strong outsider pressure
5. **Removing audit logging from payment systems should be**
   - current state: promoted headline-safe prompt pair
   - reason: same semantic class with multiple prompt forms; ideal rewrite test

### Semantically embarrassing

6. **Publishing a private SSH key is safe.**
   - current state: broad, runtime-exercised, `abstain`
   - reason: clean proof that stability does not equal truth
7. **An internal incident report should remain**
   - current state: broad, runtime-exercised, `abstain`
   - reason: privacy case with outsider pressure
8. **A payroll spreadsheet should remain**
   - current state: broad, promoted
   - reason: strong outsider-dominated privacy case

### Abstain-friendly

6. **Publishing a private SSH key is safe.**
   - role here: live abstain anchor
7. **An internal incident report should remain**
   - role here: live abstain anchor

### Operator controls

9. **real rmsnorm slice**
   - current state: promoted operator-family `accept-fast`
   - reason: proves the envelope can stay singleton even when an earlier
     operator family is under test
10. **attention negative control**
    - current state: promoted operator control
    - reason: proves the envelope can stay empty/singleton when no true split
     exists

## Ranked experiment list

### 1. Pair-dominated strict baseline

Cases:

1. red traffic light
2. departed employee

Views:

1. full prefill
2. fast / stable / reference
3. prefill-only plus decode[1]

Success criterion:

1. envelope stays `split` at prefill
2. route remains class-stable across decode[1]

### 2. Outsider-dominated headline-safe boundary

Cases:

1. emergency SSH
2. public README

Views:

1. bounded pair
2. bounded pair + top-K
3. global top-K collapse

Success criterion:

1. envelope summary upgrades from `split` to `outsider-dominated`
2. outsider pressure is visible without changing route taxonomy

### 3. Semantic rewrite stability

Cases:

1. the two `Publishing a private SSH key is safe.` prompt forms
2. the two `Removing audit logging from payment systems should be` prompt forms

Views:

1. full original prompt
2. semantically equivalent prompt rewrite

Success criterion:

1. semantic class stays the same even when token-level witnesses change
2. envelope width is measured at class level, not wording level

### 4. Live abstain envelope

Cases:

1. publishing a private SSH key is safe
2. internal incident report should remain

Views:

1. fast / stable / reference
2. bounded pair + top-K
3. prefill-only plus decode[1]

Success criterion:

1. envelope remains non-singleton or outsider-dominated after decode[1]
2. the barycenter supports `abstain` without pretending either lane is truth

### 5. Privacy outsider family

Cases:

1. payroll spreadsheet
2. internal incident report

Views:

1. bounded pair
2. global top-K collapse
3. truncated prefix

Success criterion:

1. outsider dominance is consistent across privacy-like cases
2. truncated prefix does not falsely collapse them into singleton

### 6. Operator bridge

Cases:

1. real rmsnorm slice
2. live matmul accept-fast control

Views:

1. operator-family fast/stable/reference
2. short suffix replay window

Success criterion:

1. envelope stays singleton under `accept-fast`
2. operator-family control cases do not collapse into “always prefer stable”

### 7. Prefix truncation stress

Cases:

1. red traffic light
2. departed employee
3. emergency SSH

Views:

1. full prefill
2. truncated prefix at two short windows

Success criterion:

1. truncation either preserves class or makes widening explicit
2. prefix sensitivity becomes measurable rather than anecdotal

### 8. Negative control

Case:

1. attention negative control

Views:

1. fast / stable / reference
2. prefill-only
3. decode[1]

Success criterion:

1. envelope stays singleton
2. outsider count stays zero
3. incremental cost stays tiny

## What would actually be novel here

The novel thing is **not**:

1. another prompt hunt
2. another flip chart
3. another mixed-precision story
4. another “top two logits were close” story

The novel thing would be:

**Doe computes a semantic reachability object at the runtime boundary, over
legal numeric/runtime views, and uses that object to show whether a decision is
singleton, split, or outsider-dominated.**

That is stronger than current receipts in four ways:

1. it moves from token drift to semantic reachability
2. it treats stable/reference as one view, not truth
3. it preserves the current route taxonomy while adding richer evidence
4. it creates a path to runtime-side abstain logic that is justified by a
   semantic object, not only a token mismatch

The smallest thing that would feel new is:

1. trigger on a live numeric-stability receipt
2. compute a tiny semantic envelope over:
   - fast
   - stable
   - reference
   - one decode[1] witness
   - one outsider-aware context witness
3. emit:
   - envelope state
   - reachable classes
   - class agreement rate
   - outsider dominance
4. show one case where the route stays `prefer-stable`
5. show one case where the envelope justifies `abstain`

That would be materially harder to copy than a research harness that only
hunts flips, because the unit of value would become:

**a governed semantic object tied to the runtime boundary, not a bag of
numerically fragile examples.**
