# Browser shader links contract

Status: `draft`

## Objective

Expose developer-visible shader provenance from page source to Doe IR to backend
output without claiming browser runtime replacement from the package shim.

## Input shape

The builder consumes a `browser_gpu_flight_recorder` artifact. Each shader link
requires:

- shader ID
- source language
- source path and hash
- Doe IR path and hash
- WGSL lowering receipt path and row ID
- backend target
- backend output path and hash

## Output artifacts

The artifact kind is `browser_shader_links`, validated by
[`config/browser-shader-links.schema.json`](../../../config/browser-shader-links.schema.json).
The Playwright smoke runner can materialize this artifact directly after a
flight recorder by passing `--shader-links-out`.
The checker can resolve `sourceFlightRecorderPath` with
`--verify-flight-recorder-root` and reject missing, duplicate, extra, or drifted
shader-link rows before checking lowering receipts.

## Failure taxonomy

- `invalid_schema_version`
- `invalid_artifact_kind`
- `invalid_flight_recorder`
- `missing_shader_anchor`
- `empty_shader_links`
- `missing_flight_recorder_path`
- `unsafe_flight_recorder_path`
- `missing_flight_recorder`
- `flight_recorder_capture_mismatch`
- `flight_recorder_runtime_mismatch`
- `missing_shader_link`
- `duplicate_shader_link`
- `extra_shader_link`
- `flight_recorder_shader_mismatch`
- `missing_lowering_receipt`
- `invalid_lowering_receipt`
- `lowering_receipt_row_missing`
- `lowering_receipt_hash_mismatch`

## Fallback policy

Shader links are diagnostic metadata. Missing links do not change runtime
selection, but they block developer-visible shader-link promotion.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-shader-links.py --flight-recorder <flight-recorder.json> --out <shader-links.json>`
- Checker:
  `python3 browser/chromium/scripts/check-browser-shader-links.py --links examples/browser-shader-links.sample.json --verify-flight-recorder-root . --verify-lowering-root .`
- Smoke hook:
  `node browser/chromium/scripts/webgpu-playwright-smoke.mjs --flight-recorder-components <component-manifest.json> --flight-recorder-out <flight-recorder.json> --shader-links-out <shader-links.json>`

## Promotion criteria

Promotion requires generated browser flight-recorder artifacts whose shader rows
carry source, IR, backend, and WGSL lowering-receipt anchors. A row with only
browser timing data is not enough.
