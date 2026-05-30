# Browser canvas/WebGPU fusion contract

Status: `draft`

## Objective

Define the probe artifact for visible canvas 2D, WebGPU, image-filter, and
presentation graph sharing when Chromium exposes stable command boundaries.
Layout, accessibility, permissions, and origin policy remain browser-owned.

## Input shape

The fusion probe schema is
[`config/browser-canvas-webgpu-fusion.schema.json`](../../../config/browser-canvas-webgpu-fusion.schema.json).
The probe records:

- runtime identity path
- participating surfaces
- responsibility-map entries
- visible graph nodes and edges
- output hashes
- timing scopes
- fallback reasons
- origin-scoped privacy policy

When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_canvas_webgpu_fusion_probe`. It is diagnostic
until a browser-lane probe can produce the same shape from forced-Doe Chromium
execution. The smoke builder derives the current graph, output hash, timing
scopes, and fallback reasons from Playwright smoke output for the selected
runtime mode.

## Failure taxonomy

The structural checker reports:

- `missing_surface_kind`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `duplicate_surface_id`
- `duplicate_node_id`
- `missing_surface_reference`
- `missing_node_reference`
- `missing_output_hash`
- `missing_timing_scope`
- `unsafe_privacy_policy`
- runtime identity reference failures from the shared browser runtime-identity
  reference checker

## Fallback policy

Fallback reasons are explicit per surface. A probe with fallback reasons remains
diagnostic unless browser claim policy accepts the fallback class.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-canvas-webgpu-fusion.py --report <browser-smoke.json> --mode doe --out <canvas-webgpu-fusion.json>`
- Smoke runner hook:
  `./browser/chromium/scripts/run-smoke.sh --mode doe --canvas-webgpu-fusion-out <canvas-webgpu-fusion.json> --canvas-webgpu-fusion-mode doe`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-canvas-webgpu-fusion.py --probe examples/browser-canvas-webgpu-fusion.sample.json --runtime-identity-root .`

## Promotion criteria

Promotion requires a generated Chromium artifact with the same graph shape,
stable output hashes, declared timing scopes, and no hidden fallback.
