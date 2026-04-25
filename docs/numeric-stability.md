# Doe numeric stability

## Purpose

This is the single planning and claim-boundary document for Doe numeric
stability. It replaces the older split strategy, claim ladder, demo
ladder, contract-roadmap, auto-detection, decode-validation, and
semantic-envelope planning notes.

The strategy boundary is narrow:

1. Doe can observe and receipt numeric fragility.
2. Doe becomes meaningfully differentiated only when that observation
   governs live runtime execution through a versioned, proof-linked
   contract.

The hunt for fragile prompts or operators can happen in Doe, Doppler,
PyTorch, Triton, CUDA, or a research WebGPU harness. The runtime
governance contract must belong to Doe.

## Current repo-true state

Doe already has:

1. a real numeric-fragility corpus
2. proof-linked route semantics
3. a bounded-slice runtime/package service
4. a native ordinary-execution path for annotated `matmul.logits`
5. live `accept-fast`, `prefer-stable`, and `abstain` outcomes

Doe does not yet have:

1. automatic fragile-operator detection in ordinary execution
2. multiple live in-path operator families
3. a route that changes the committed downstream result of ordinary
   execution
4. ordinary package execution that inherits native in-path behavior
5. browser-lane consumption of the same promoted runtime contract

The current numeric-stability contract is real but narrow. It can be
claimed as a governed runtime contract under construction, not as a
general numerical-reliability product surface.

## Claim boundary

Safe current wording:

> Doe has a proof-linked numeric-stability route contract and a live
> bounded runtime/package path for selected fragile cases.

Safe next wording, after in-path governance affects committed execution:

> Doe can detect a numerically fragile decision boundary during runtime
> execution, rerun the fragile operator under a stronger declared policy,
> and emit a receipt for the route it took.

Do not claim yet:

1. automatic fragile-operator detection across ordinary execution
2. broad model quality improvement
3. browser-wide adoption
4. multi-operator governance
5. general robustness against hallucination, prompt ambiguity, or
   semantic disagreement
6. performance neutrality without measured receipts

The concise product thesis remains:

> Doe is a WebGPU runtime that can detect numerically fragile decisions,
> rerun only the fragile operator under a stronger declared policy, and
> govern the live outcome with a receipted route decision.

## Contract surface

The live route outcomes are:

| Route | Meaning |
| --- | --- |
| `accept-fast` | Fast path and stable/reference evidence agree enough to commit the fast result. |
| `prefer-stable` | Stable/reference evidence indicates the fast result sits on a fragile boundary; use the stable result when the caller has opted into route effect. |
| `abstain` | The route is too ambiguous to choose safely; surface the receipt instead of silently promoting a result. |

The source artifacts are:

- `config/numeric-stability-policy.json`
- `config/numeric-stability-policy.schema.json`
- `config/numeric-stability-auto-detection-plan.json`
- `config/numeric-stability-auto-detection-plan.schema.json`
- `config/numeric-stability-decode-fragility-plan.json`
- `config/numeric-stability-decode-fragility-plan.schema.json`
- `config/numeric-stability-decode-validation-plan.json`
- `config/numeric-stability-decode-validation-plan.schema.json`
- `config/numeric-stability-semantic-envelope-plan.json`
- `config/numeric-stability-semantic-envelope-plan.schema.json`
- `config/numeric-stability-semantic-envelope.schema.json`
- `examples/numeric-stability-semantic-envelope.sample.json`
- `pipeline/lean/Doe/Core/NumericStabilityPolicy.lean`

## What is left

| ID | Area | Status | Work left | Done when |
| --- | --- | --- | --- | --- |
| N-1 | Evidence freeze | Active | Keep the promoted corpus, policy config, route semantics, and Lean proof surface synchronized. | Config schemas validate, promoted cases replay, and policy route proofs still match the runtime route enum. |
| N-2 | Runtime receipt | Active | Keep the runtime receipt contract explicit for operator family, policy, route, fast/stable/reference values, and proof/config identity. | A receipt from ordinary execution can be validated against schema and traced back to config + proof artifacts. |
| N-3 | Auto-detection | Pending | Move from annotated `matmul.logits` to automatic fragile-operator detection during ordinary execution. Start with `matmul.logits`, then expand to `softmax.denominator`, `rmsnorm.output`, `layernorm.output`, and `attention.output` only after measured overhead is acceptable. | Ordinary execution emits a numeric-stability receipt without requiring an explicit capture override for the first operator family. |
| N-4 | Route effect | Pending | Make `prefer-stable` change the committed downstream result under an explicit policy, not just report an observation. | A runtime test proves the committed output differs when the route selects the stable path, and the receipt records that route effect. |
| N-5 | Decode boundary | Pending | Promote `sample.token` from mined fragility states into a receipt surface with meaningful-token filtering, short suffix consequence, and backend promotion rules. | Decode-boundary cases are promoted only when they change a meaningful token or short suffix, not just a junk tie. |
| N-6 | Semantic envelope | Design | Represent semantic equivalence and ambiguity across prompt, decode, numeric, and candidate-context views without combinatorial explosion. | A `numeric-stability-semantic-envelope` artifact validates against schema and is attached to at least one promoted case. |
| N-7 | Package surface | Pending | Expose the same route semantics through `doe-gpu` package APIs without creating a separate product contract. | `stableToken`, `stableChoice`, and `reviewedChoice` consume the same runtime receipt shape as native Doe. |
| N-8 | Browser promotion | Pending | Carry promoted runtime receipts into the browser lane. | Browser evidence uses the same config/proof/receipt identity chain, with no separate browser-only semantics. |
| N-9 | Performance budget | Pending | Bound rerun overhead through operator-local capture, suffix replay, and measured defaults. | Receipts include cost fields, and promotion rules reject cases that exceed the configured overhead budget. |

## Semantic envelope

The semantic envelope is a receipt extension, not a replacement for
numeric evidence. It should answer whether adjacent outputs are:

1. equivalent enough to treat as stable
2. different but still policy-acceptable
3. ambiguous enough to abstain
4. clearly divergent

The first pass should stay small:

1. use the existing envelope schema and sample
2. attach envelope state to selected promoted cases
3. avoid raw natural-language promises that are not reducible to a
   bounded artifact
4. keep algorithmic experiments behind config and schema, not prose

Recommended experiment order:

1. pair-dominated strict baseline
2. outsider-dominated headline-safe boundary
3. semantic rewrite stability
4. live abstain envelope
5. privacy outsider family
6. operator bridge
7. prefix truncation stress
8. negative control

## Demo boundary

The live demo should show three outcomes:

1. `prefer-stable`: a fragile boundary where a stronger policy changes
   the committed result under opt-in route effect
2. `accept-fast`: a control where fast and stable agree
3. `abstain`: an ambiguous case where Doe refuses to over-claim

Demo cases should be promoted only when the artifact shows the route,
the affected operator family, the policy, the source identity, and the
downstream consequence.

## Reading order

1. `docs/status.md` for current status
2. `bench/README.md` for evidence and runner commands
3. `config/numeric-stability-policy.json` for the live route policy
4. `config/numeric-stability-decode-validation-plan.json` for decode
   promotion rules
5. `examples/numeric-stability-semantic-envelope.sample.json` for the
   envelope artifact shape
