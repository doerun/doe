# Numeric stability decode validation plan

## Purpose

This document is the track-3 plan for decode-boundary numeric fragility.

Track 1 is responsible for making `sample.token` a real runtime receipt.
Track 2 is responsible for mining likely fragile decode states.
Track 3 is responsible for deciding which decode flips actually matter and
which ones are strong enough to promote beyond a single backend.

The track-3 job is:

1. reject junk-token flips
2. keep only semantically meaningful flips
3. require short suffix consequence
4. require within-policy stability
5. promote Metal first, then Vulkan

Canonical planning surface:

- [`config/numeric-stability-decode-validation-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-validation-plan.json)

Schema:

- [`config/numeric-stability-decode-validation-plan.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-validation-plan.schema.json)

This is planning-only. It does not change live runtime behavior by itself.

## Core rule

The thing that matters is not “the logits changed.”

The thing that matters is:

1. the actual selected token changed under the same decode function
2. the token is semantically meaningful
3. the semantic consequence persists for a short suffix window
4. the case is stable within each compared policy

Until those conditions hold, a decode flip should not become a promoted Doe
story.

## Meaningful versus junk token flips

Not every token flip deserves attention.

Track 3 should keep only flips that fall into declared meaningful token
classes such as:

1. JSON literals
2. policy-action words
3. visibility labels
4. moderation labels
5. tool identifiers
6. approval labels
7. whole-word answers

Track 3 should reject flips that are only:

1. whitespace
2. newlines
3. punctuation
4. delimiters
5. BPE fragments
6. casing changes
7. formatting changes

This is the shortest path to keeping the decode-boundary work honest.

If the only observed difference is `true` versus `True`, or `allow` versus
` allow`, or a trailing brace or comma, the runtime may still record it, but
the promotion pipeline should not treat it as a meaningful decode-boundary
case.

## Semantically sharp scenario buckets

Track 2 should seed the mining funnel with semantically sharp prompt families.
Track 3 is where those buckets are declared and normalized.

Current bucket set:

1. tool choice
2. JSON booleans
3. moderation labels
4. policy-action words
5. visibility labels
6. approval labels
7. tool-call targets

These buckets are intentionally narrow. They are the decode surfaces where a
single token can actually change what the application does.

## Within-policy stability

Before a decode flip is promoted, each compared policy must be internally
stable.

That means:

1. rerun the same captured decode state multiple times
2. use the same seed
3. use the same decode config
4. require full agreement within each policy lane

If the fast path itself is unstable across identical replays, that is a
different problem than a clean fast-versus-stable decode divergence.

The current planning contract requires:

1. same seed
2. same decode config
3. repeated replay per policy
4. full agreement rate

See the concrete replay parameters in:

- [`config/numeric-stability-decode-validation-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-validation-plan.json)

## Short suffix consequence

A token flip is more interesting when it still matters one to four steps later.

Track 3 should require short suffix replay using:

1. the same seed
2. the same decode config
3. the same decode policy
4. the same captured boundary state

The replay only needs to prove one of two consequence kinds:

1. selected-token divergence continues
2. semantic-class divergence continues

This is intentionally modest. The point is not to replay the whole request.
The point is to prove the decode-boundary flip is not immediately washed out by
the next token.

## Metal first, then Vulkan

Track 3 should treat backend validation as a promotion ladder, not as one big
all-at-once goal.

The planned stages are:

1. `metal-exercised`
2. `metal-promoted`
3. `vulkan-reproduced`
4. `cross-backend-promoted`

The rule is simple:

1. prove the case end to end on Metal first
2. make it demo-quality on Metal
3. then repeat it on Vulkan using the same prompt/model/decode contract
4. only then present it as a runtime contract example rather than a one-lane
   artifact

This matters because a cross-policy decode flip on one backend is interesting,
but a semantically meaningful decode flip that survives backend expansion is
much closer to a real Doe moat.

## Relationship to existing planning surfaces

This track-3 plan is not a replacement for the existing A-track and B-track
plans.

It sits on top of them:

1. Track 1 emits the decode-boundary receipt
2. Track 2 ranks likely fragile decode states
3. Track 3 decides whether the case is meaningful, consequential, and portable

Related surfaces:

- semantic envelopes:
  [`config/numeric-stability-semantic-envelope-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-semantic-envelope-plan.json)
- operator expansion and auto-detect planning:
  [`config/numeric-stability-auto-detection-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-auto-detection-plan.json)
- existing runtime promotion policy:
  [`config/fragility-promotion-policy.json`](/Users/xyz/deco/doe/config/fragility-promotion-policy.json)
- current demo ladder:
  [`docs/numeric-stability-demo-ladder.md`](/Users/xyz/deco/doe/docs/numeric-stability-demo-ladder.md)

## Demo implications

The first decode-boundary demo set should include:

1. one buyer-legible `prefer-stable`
2. one real `accept-fast` control
3. one real `abstain`
4. one cross-backend repeat
5. one semantically embarrassing control

That is the minimum set that teaches the right lesson:

1. Doe can correct
2. Doe can refrain from false correction
3. Doe can refuse to force a winner
4. the decode-boundary effect is not tied to one backend
5. Doe still governs consistency, not truth

## Smallest next step

The smallest useful track-3 step is:

1. wait for the first real `sample.token` receipt shape from Track 1
2. map the captured token text into the meaningful-token and rejection rules
3. add one short suffix replay evaluator over the same seed/config
4. classify the first Metal cases into semantic scenario buckets
5. mark which ones are ready for Vulkan reproduction

That gives Track 1 and Track 2 a clean target without blocking their runtime
or mining work.
