# Browser CTS subset contract

Status: `draft`

## Objective

Define browser-level CTS subset artifacts for paired Dawn and forced-Doe lanes.
The contract keeps CTS browser evidence separate from package/native CTS
evidence and rejects hidden fallback in forced-Doe rows.

## Input shape

The subset schema is
[`config/browser-cts-subset.schema.json`](../../../config/browser-cts-subset.schema.json).
Each artifact declares CTS source, revision, Dawn artifact path,
forced-Doe artifact path, query rows, parity status, and fallback policy.

## Output artifacts

The artifact kind is `browser_cts_subset`. Sample artifacts are diagnostic and
use `not_run` rows until Chromium browser CTS runs generate Dawn and forced-Doe
evidence.

`browser/chromium/scripts/build-browser-cts-subset.py` converts paired
Playwright smoke output into a browser CTS subset diagnostic. The builder is
not a CTS runner; it projects existing smoke evidence into the same bucket
contract so Dawn/forced-Doe browser lanes have a schema-backed paired artifact
until real browser CTS runs replace the diagnostic source.

## Failure taxonomy

The structural checker reports:

- `missing_browser_lane`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `missing_cts_bucket`
- `hidden_fallback_allowed`
- `unsafe_artifact_path`
- `missing_reason_code`
- `cts_parity_status_mismatch`

## Fallback policy

Hidden fallback is never allowed. Diagnostic or mismatch rows must carry a
reason code.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-cts-subset.py --report <browser-smoke-both.json> --out <browser-cts-subset.json>`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-cts-subset.py --subset examples/browser-cts-subset.sample.json`

## Promotion criteria

Promotion requires generated browser CTS artifacts for both Dawn and forced Doe,
runtime-selector identity, no hidden fallback, and CTS rows covering the
declared browser-visible buckets.
