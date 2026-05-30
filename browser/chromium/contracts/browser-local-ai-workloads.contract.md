# Browser local AI workloads contract

Status: `draft`

## Objective

Define the browser local AI workload set for embeddings, ranking, image/video
transforms, and model inference under Chromium. Each workload row must carry
the receipt fields needed to identify the model, shader, pipeline cache state,
input contract, output digest, and fallback status.

## Input shape

The workload schema is
[`config/browser-local-ai-workloads.schema.json`](../../../config/browser-local-ai-workloads.schema.json).
Each artifact declares runtime identity, workload rows, model identity, shader
identity, pipeline cache receipt, input contract, output digest, fallback
status, and capture privacy policy.
When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_local_ai_workloads`. Artifacts remain diagnostic
until Chromium-generated runs populate the same fields from forced-Doe browser
execution.

`browser/chromium/scripts/build-browser-local-ai-workloads.py` converts
Playwright smoke compute evidence into a hashed workload set for embeddings,
ranking, image/video transforms, and model inference. The builder carries
runtime identity, source/IR/backend shader hashes, and redacts input/output
values into digests.

## Failure taxonomy

The structural checker reports:

- `missing_workload_kind`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `duplicate_workload_id`
- `missing_receipt_field`
- `missing_output_digest`
- `hidden_fallback_allowed`
- `missing_fallback_reason`
- `unsafe_privacy_policy`
- runtime identity reference failures from the shared browser runtime-identity
  reference checker

## Fallback policy

Hidden fallback is never allowed. Any applied fallback must carry a reason code.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Smoke artifact builder:
  `python3 browser/chromium/scripts/build-browser-local-ai-workloads.py --report <browser-smoke.json> --mode doe --out <browser-local-ai-workloads.json>`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-local-ai-workloads.py --workloads examples/browser-local-ai-workloads.sample.json --runtime-identity-root .`

## Promotion criteria

Promotion requires browser-generated workload artifacts with all required
workload kinds, no hidden fallback, model identity, shader source/IR/backend
identity, cache receipt, input/output digests, and origin-scoped redaction.
