# Doe numeric-stability demo ladder

## Purpose

This document chooses the first demo set for Doe numeric stability.

The goal is not to maximize the number of flips. The goal is to prove the right
system behavior:

1. `prefer-stable`
2. `accept-fast`
3. `abstain`

It also separates:

1. headline-safe demos
2. research/control demos
3. candidate promotions that are real but not yet ready

## Demo principles

A good Doe demo should show:

1. a real prompt or real operator family
2. a named numeric policy difference
3. a first-divergence story
4. a route decision
5. an honest interpretation

The best demos are not always the most flattering ones. We need both:

1. buyer-legible danger cases
2. semantically embarrassing cases that prove Doe governs consistency, not
   truth

## Live v1 starter set

This is the minimum live set that should exist before the feature is pitched as
runtime-shape rather than bench-shape.

### 1. `prefer-stable`

Case:

1. red traffic light `go/stop`

Why it matters:

1. real prompt
2. real bounded answer set
3. real operator family
4. clean first-divergence story at `matmul.logits`
5. current flagship evidence already exists

Current status:

1. live in native ordinary execution
2. first current flagship for `prefer-stable`

### 2. `accept-fast`

Case:

1. `rmsnorm` operator-family control

Why it matters:

1. proves Doe is not fake “always prefer stable” theater
2. shows the route can keep fast when the stricter rerun is worse
3. strengthens trust in the whole contract

Current status:

1. `rmsnorm` remains the best real operator-family bench/probe control
2. the first live native `accept-fast` route is currently the synthetic
   `matmul.logits` in-path control
3. a real in-path operator-family `accept-fast` case is still the next target

### 3. `abstain`

Case:

1. first live runtime case where neither fast nor stable should be forced

Why it matters:

1. prevents the feature from collapsing into binary override behavior
2. creates a clean path for future route growth
3. proves the runtime can say “do not force a winner”

Current status:

1. live in native ordinary execution for current broad prompt cases such as:
   - `Publishing a private SSH key is safe.`
   - `An internal incident report should remain`
2. this route is now part of the live demo ladder, not just schema truth

## Headline-safe expansion set

These are the best candidates for early product-facing numeric-stability demos.

1. schema migration without backup
2. revoking access for a departed employee
3. removing audit logging from payment systems
4. enabling audit logging on privileged actions
5. phishing email
6. request from known malicious botnet IP
7. suspicious newly registered outbound domain
8. red X lane signal

These are strong because a numeric flip crosses a clear policy boundary a buyer
would care about.

## Research/control set

These should be kept visible, even if they are not headline demos.

1. publishing a private SSH key is safe
2. revoking a leaked API token is unnecessary
3. MFA reduces account security
4. encrypting user data at rest is required here
5. HTTPS encrypts traffic in transit
6. session signing key should remain public/private
7. production database password should remain private/public

These matter because they prove a critical point:

1. stable/reference does not equal truth
2. Doe governs consistency, not semantic correctness

## Hold-out or weaker cases

These are still useful for research, but should not lead the first runtime
story.

1. top-prefix-only prompt flips
2. answer-set slices with awkward bounded words such as `not`
3. casing-only flips
4. cases where the intended pair is not the actual bounded answer surface

## Promotion rules

A case should be promoted into the live runtime demo ladder only if:

1. the bounded answer set is legible
2. the route outcome is interpretable
3. the first divergent operator is named
4. fast versus stable is reproducible
5. the case adds something new to the ladder

The ladder should not be filled with 10 copies of the same story.

## Target v1 demo mix

The first real runtime set should include at least:

1. one live `prefer-stable`
2. one live `accept-fast`
3. one live `abstain`
4. one buyer-legible danger case beyond the flagship
5. one semantically embarrassing control case

That gives a minimum of 5 demos worth showing internally or externally.

Current native ordinary-execution coverage now includes:

1. live `prefer-stable`
2. live `accept-fast`
3. live `abstain`

The remaining v1 demo work is:

1. promote a real operator-family `accept-fast` beyond the synthetic control
2. add another buyer-legible prompt case beyond the red-light flagship

Important caveat:

1. the current native ladder proves live route outcomes and receipts
2. it does not yet prove moat-grade route effect on downstream execution for
   ordinary callers

## Target v2 demo mix

After the first runtime promotion, expand to:

1. 5-10 live runtime demos
2. multiple prompt families
3. at least two operator families
4. at least one negative control shown alongside the headline cases

## Target moat demo mix

The first demo set that should count as moat-grade should include:

1. one case where `prefer-stable` changes the committed downstream result
2. one case where `accept-fast` explicitly preserves the fast path in the live
   execution contract
3. one case where `abstain` prevents a forced winner instead of merely logging
   a receipt
4. one second operator family beyond `matmul.logits`
5. one ordinary package-facing example that exercises the same promoted
   contract

Until those exist, treat the current ladder as a strong runtime capability
demo, not the final moat demo.

## Future decode-boundary demo filter

When Doe adds a real `sample.token` receipt, the decode-boundary demo ladder
should be stricter than the operator-boundary ladder.

Promote only cases where:

1. the actual selected token changes
2. the token is semantically meaningful
3. the change happens early enough to matter
4. each compared policy is internally stable
5. a short suffix replay stays semantically divergent
6. Metal proof comes first and Vulkan reproduction follows later

This keeps the future decode story from filling up with whitespace, casing, or
one-backend curiosities.

## Demo reading order

When presenting the feature, the recommended order is:

1. red traffic light `prefer-stable`
2. `rmsnorm` `accept-fast`
3. first live `abstain`
4. one buyer-legible policy case
5. one semantically embarrassing control case

That order teaches the right lesson:

1. the runtime can correct
2. the runtime can refrain from false correction
3. the runtime can decline to force a choice
4. the system is useful
5. the system is honest
