# Numeric stability semantic envelope plan

## Purpose

This document is the A-track design pass.

The goal is to move beyond “fast versus stable picked different tokens” and
define a richer semantic object that Doe could compute when numeric fragility
appears at a runtime boundary.

The proposed object is the **semantic envelope**:

1. what semantic classes were considered
2. which legal numeric, kernel, and prompt/decode views were evaluated
3. which semantic answers were reachable
4. whether the answer set stays singleton, splits, or gets dominated by
   outsiders

The semantic envelope is a planning surface only. It does not change the live
route taxonomy or current runtime behavior.

## Proposed artifact

Canonical schema:

- [`config/numeric-stability-semantic-envelope.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-semantic-envelope.schema.json)

Sample:

- [`examples/numeric-stability-semantic-envelope.sample.json`](/Users/xyz/deco/doe/examples/numeric-stability-semantic-envelope.sample.json)

The artifact records:

1. source case references
2. semantic classes
3. evaluated views
4. reachable answers
5. one envelope status:
   - `singleton`
   - `split`
   - `outsider-dominated`
6. metrics over the envelope

This keeps the object compact enough to be receipted while still being richer
than one selected token.

## Combination families

The semantic envelope should explore only a small set of legal view families:

1. full prefill
2. truncated prefix subsequences
3. semantically equivalent rewrites
4. prefill plus `decode[1]`
5. short suffix replay windows
6. fast/stable/reference kernel or numeric variants
7. bounded pair aggregation alongside global top-K outsider context

Important rule:

1. branch only when fragility triggers
2. collapse immediately by semantic class
3. do not keep large token-level trees alive

That is the difference between a runtime-governed semantic object and an
expensive search harness.

The config-backed family list lives in:

- [`config/numeric-stability-semantic-envelope-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-semantic-envelope-plan.json)

## Algorithms

The two non-combinatorial algorithms worth pursuing first are:

### 1. Policy-beam decode with semantic collapse

Idea:

1. start from the live runtime case
2. branch only when the numeric-stability trigger fires
3. retain one branch per semantic class, not per token sequence

Why it matters:

1. it keeps cost bounded
2. it makes the output legible
3. it turns numeric variation into a class-level object, not a token jungle

### 2. Semantic barycenter across views

Idea:

1. treat each legal view as evidence for one or more semantic classes
2. aggregate them at the class level
3. penalize outsider-dominated views instead of pretending they are clean

Why it matters:

1. it tells us whether the fragility boundary is a genuine semantic split
2. it avoids over-trusting any one numeric policy
3. it gives Doe a richer runtime summary than “stable won”

## Evaluation metrics

The envelope should be judged on:

1. semantic envelope width
2. class agreement rate
3. outsider lead
4. bounded margin
5. route stability across adjacent decode steps
6. incremental cost

These are now pinned in:

- [`config/numeric-stability-semantic-envelope-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-semantic-envelope-plan.json)

That is deliberate. The semantic-envelope work should not drift into vague
“interesting examples” language.

## Ranked experiments

Recommended first 10 experiments are now fixed in config:

- [`config/numeric-stability-semantic-envelope-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-semantic-envelope-plan.json)

The list includes:

1. 5 headline-safe cases
2. 3 semantically embarrassing controls
3. 2 abstain-friendly cases

Best starting set:

1. `At a red traffic light, cars should`
2. `Revoking access for a departed employee should be`
3. `Emergency SSH from the approved bastion host should`
4. `A public open-source README should remain`
5. `Publishing a private SSH key is safe.`
6. `An internal incident report should remain`

Those are the best candidates because they already have runtime or promoted
evidence and represent different route shapes.

The ranked list now distinguishes evidence stage explicitly:

1. `runtime-exercised`
2. `promoted`
3. `corpus-only`

That keeps the experiment plan source-backed without pretending every case has
already graduated into the same runtime contract stage.

## What would actually be novel here

The novel thing is not “more decode branches.”

The novel thing would be:

1. Doe computes a semantic object richer than a single token
2. it does so only inside legal runtime and numeric variations
3. it branches only when fragility triggers
4. it collapses immediately by semantic class
5. it can say whether the semantic boundary is singleton, split, or
   outsider-dominated

That would be more interesting than plain determinism or plain uncertainty
because it connects:

1. numeric variation
2. runtime policy
3. semantic consequence

without pretending stable/reference is automatically correct.

## Smallest next step

The smallest useful A-track next step is:

1. implement a read-only semantic-envelope exporter over existing promoted and
   runtime-exercised cases
2. start with:
   - full prefill
   - fast/stable/reference views
   - one-step decode
   - bounded pair plus global top-K outsider context
3. emit the envelope artifact for 3 to 5 cases

That would be enough to test whether the object is genuinely informative before
adding richer replay windows or package exposure.
