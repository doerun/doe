# Numeric stability decode fragility plan

## Purpose

This document owns the track-2 mining and promotion layer for the next numeric-
stability step:

1. use the live `sample.token` receipt surface
2. consume the live sampled-decode fields when the expanded sample ABI is present
3. rank decode states by fragility
4. promote only cases where the real selected token changes
5. require short suffix consequence before treating a case as a flagship

This is intentionally narrower than the runtime and moat documents. It does not
change live runtime behavior.

Planning surfaces:

- [`config/numeric-stability-decode-fragility-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-fragility-plan.json)
- [`config/numeric-stability-decode-fragility-plan.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-fragility-plan.schema.json)
- [`config/numeric-stability-decode-harvest-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-harvest-plan.json)
- [`config/numeric-stability-decode-harvest-plan.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-harvest-plan.schema.json)
- [`config/numeric-stability-decode-signature.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-signature.schema.json)
- [`config/numeric-stability-decode-promoted-catalog.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-promoted-catalog.json)
- [`config/numeric-stability-decode-promoted-catalog.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-promoted-catalog.schema.json)
- [`config/numeric-stability-decode-row.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-row.schema.json)
- [`config/numeric-stability-decode-row-enrichment.schema.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-row-enrichment.schema.json)
- [`bench/lib/sampled_decode_fragility.py`](/Users/xyz/deco/doe/bench/lib/sampled_decode_fragility.py)
- [`bench/runners/harvest_sampled_decode_fragility.py`](/Users/xyz/deco/doe/bench/runners/harvest_sampled_decode_fragility.py)
- [`bench/runners/enrich_sampled_decode_rows.py`](/Users/xyz/deco/doe/bench/runners/enrich_sampled_decode_rows.py)
- [`bench/runners/promote_sampled_decode_fragility.py`](/Users/xyz/deco/doe/bench/runners/promote_sampled_decode_fragility.py)
- [`bench/runners/replay_promoted_sampled_decode_vulkan.py`](/Users/xyz/deco/doe/bench/runners/replay_promoted_sampled_decode_vulkan.py)
- [`bench/runners/normalize_decode_fragility_rows.py`](/Users/xyz/deco/doe/bench/runners/normalize_decode_fragility_rows.py)
- [`bench/runners/rank_decode_fragility_states.py`](/Users/xyz/deco/doe/bench/runners/rank_decode_fragility_states.py)

## Current truth

Doe already has a real runtime receipt surface for the normal decode boundary
at `sample.token`.

That live receipt now carries decode-boundary-local metrics:

1. `fastTop1Margin`
2. `stableTop1Margin`
3. `referenceTop1Margin`
4. `actualSelectedTokenChanged`
5. `liveSelectedMatchesFast`
6. `liveSelectedMatchesStable`
7. `liveSelectedMatchesReference`

When the expanded sample ABI is present, the receipt now also carries live
sampled-decode config:

1. `temperature`
2. `topK`
3. `topP`
4. `rngSeed`
5. `rngDraw`
6. sampled selected token under `fast`, `stable`, and `reference`

So the remaining gap is no longer receipt shape or missing pipeline plumbing.
Doe now has a real harvest/enrichment/promotion path. The remaining gap is live
harvest quality:

1. mining real sampled rows from production-like workloads
2. attaching within-policy stability and suffix replay evidence
3. promoting only meaningful sampled flips instead of controls

The current checked Metal harvest already exercises that pipeline on two live
cases:

1. the sampled decode demo
2. a first-5-step truncated `gemma3_270m` ordinary decode

See:

- [`bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/sampled_decode_harvest.manifest.json`](/Users/xyz/deco/doe/bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/sampled_decode_harvest.manifest.json)
- [`bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/numeric_stability_decode_fragility.report.json`](/Users/xyz/deco/doe/bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/numeric_stability_decode_fragility.report.json)

That run produced only `reject` rows, which is the honest current state. The
decode promotion catalog remains empty until a sampled flip is both real and
meaningful.

## Normalized mining input

The ranking runner consumes a normalized JSONL row shape so the receipt lane,
the enrichment lane, and the ranking lane can move independently.

The normalization step now lives in:

- [`bench/runners/normalize_decode_fragility_rows.py`](/Users/xyz/deco/doe/bench/runners/normalize_decode_fragility_rows.py)

It consumes live `decode.sample_token` receipts plus an optional enrichment
sidecar for prompt text, decode step index, semantic-priority overrides,
within-policy stability, and short suffix replay evidence.

The normalization step now prefers the decode-boundary metrics emitted by the
runtime itself and only falls back to local derivation when a field is still
absent in the live receipt.

Required fields:

1. `caseId`
2. `promptText`
3. `decodeStepIndex`
4. `semanticPriorityClass`
5. `sourceArtifactPath`
6. `selectedToken.fast`
7. `selectedToken.stable`
8. `selectedToken.reference`
9. `metrics.postTemperatureTop1Margin`
10. `metrics.actualSelectedTokenChanged`
11. `metrics.meaningfulToken`
12. `metrics.withinPolicyStable`
13. `upstream.fastStableDisagreement`
14. `suffixReplay.available`
15. `suffixReplay.divergent`

Optional fields carry the rest of the decode-boundary detail:

1. `metrics.topKBoundaryGap`
2. `metrics.topPBoundaryGap`
3. `metrics.cdfDistanceToDraw`
4. `metrics.adjacentDecodePersistence`
5. `decodeConfig.temperature`
6. `decodeConfig.topK`
7. `decodeConfig.topP`
8. `decodeConfig.rngSeed`
9. `decodeConfig.randomDraw`
10. `upstream.firstDivergenceSemanticOpId`
11. `selectedTokenText.fast`
12. `selectedTokenText.stable`
13. `selectedTokenText.reference`
14. `suffixReplay.replayStepCount`

This keeps the mining contract explicit while still letting track 2 consume the
live sampled receipt as soon as those fields appear.

## Replay predicates

Track 2 only promotes real decode flips.

Greedy predicate:

1. selected token under `fast` differs from `stable` or `reference`

Sampling predicate:

1. the runtime decode function produces a different token under the same decode
   config and the same random draw `u`

This is why the plan treats `sample.token` as the required boundary.
The receipt contract is now real for both greedy fallback and sampled ordinary
execution. What remains is finding real promotable sampled flips, not
inventing the receipt surface itself.

## Fragility signals

The plan ranks decode states using the signals most likely to produce real
token changes:

1. post-temperature top-1 margin
2. `top-k` cutoff proximity
3. `top-p` cutoff proximity
4. sampled CDF distance to the draw `u`
5. adjacent decode persistence
6. upstream fast/stable disagreement
7. early decode position

The current weighted signal set lives in:

- [`config/numeric-stability-decode-fragility-plan.json`](/Users/xyz/deco/doe/config/numeric-stability-decode-fragility-plan.json)

## Semantic priority

Probability alone is not enough. The promotion loop should prioritize cases
that matter semantically:

1. tool choice
2. JSON booleans
3. moderation labels
4. policy actions
5. short structured answers

This keeps the future demo set closer to product behavior and farther from
whitespace or junk-token flips.

## Promotion standard

The current bar is intentionally strict.

A case is promotable only if:

1. the actual selected token changes
2. the token is semantically meaningful
3. the step is early in decode
4. each policy is internally stable
5. upstream disagreement is present
6. short suffix replay stays divergent
7. the weighted fragility score clears the configured threshold

If a case is semantically real but still misses suffix replay or within-policy
stability evidence, it stays `investigate`. If it fails the hard semantic bar,
such as unchanged selection or meaningless token text, it is `reject`.

## Seed families

The search should start from semantically sharp prompt families already present
in the repo:

1. `go/stop`
2. `allow/block`
3. `approve/deny`
4. `public/private`
5. phishing / SSH / access-control prompts
6. tool choice, moderation, and JSON booleans

These are seed families, not proof by themselves.

## Backends

The backend order should stay simple:

1. Apple Metal first
2. AMD Vulkan second

Metal is where the strongest current ordinary-execution evidence already lives.
Vulkan matters once the decode-boundary receipt and promotion loop are real, so
the claim becomes runtime-portable instead of backend-local.
