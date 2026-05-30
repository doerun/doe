# Browser pipeline cache receipts contract

Status: `draft`

## Objective

Define developer-visible browser receipts for cache hit/miss state and pipeline
creation. Receipts must preserve workload identity, shader identity, cache key,
cache state, pipeline creation path, fallback status, and the source workload
artifact that produced the receipt set.

## Input shape

The receipt schema is
[`config/browser-pipeline-cache-receipts.schema.json`](../../../config/browser-pipeline-cache-receipts.schema.json).
The builder consumes `browser_local_ai_workloads` artifacts and emits one
receipt per workload cache row. The emitted artifact records
`sourceWorkloadsPath` and `sourceWorkloadSetId`, and each receipt copies the
source shader, Doe IR, and backend-output hashes from the workload row.
When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_pipeline_cache_receipts`. Passing artifacts carry
developer-visible cache receipts. Failing artifacts carry typed failures and no
partial receipts.

The Playwright smoke runner can materialize this artifact directly after local
AI workload emission by passing `--pipeline-cache-receipts-out`.
The checker can also resolve `sourceWorkloadsPath` with
`--verify-workloads-root` and reject missing, duplicate, extra, or drifted
workload receipts.

## Failure taxonomy

The builder reports:

- `missing_cache_receipt_field`
- `hidden_fallback_allowed`
- `missing_fallback_reason`

The checker additionally reports source-linkage and coverage failures when
`--verify-workloads-root` is supplied. It reports runtime identity reference
failures when `--runtime-identity-root` is supplied. It also rejects
top-level `schemaVersion` and `artifactKind` drift with
`invalid_schema_version` and `invalid_artifact_kind`. Source workload paths
must be repo-relative; unsafe paths fail with `unsafe_source_workloads_path`,
and invalid source JSON fails with `invalid_source_workloads`.

## Fallback policy

Hidden fallback is never allowed. Any applied fallback must carry a reason code
into the cache receipt.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-pipeline-cache-receipts.py --workloads examples/browser-local-ai-workloads.sample.json --out /tmp/browser-pipeline-cache-receipts.json`
- Checker:
  `python3 browser/chromium/scripts/check-browser-pipeline-cache-receipts.py --receipts examples/browser-pipeline-cache-receipts.sample.json --verify-workloads-root . --runtime-identity-root .`
- Smoke hook:
  `node browser/chromium/scripts/webgpu-playwright-smoke.mjs --local-ai-workloads-out <browser-local-ai-workloads.json> --pipeline-cache-receipts-out <browser-pipeline-cache-receipts.json>`

## Promotion criteria

Promotion requires browser-generated workload artifacts that emit cache receipts
from real pipeline creation and cache lookup paths under forced-Doe execution.
