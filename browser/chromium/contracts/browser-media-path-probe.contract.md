# Browser media path probe contract

Status: `draft`

## Objective

Define browser-lane probes for `GPUExternalTexture`,
`copyExternalImageToTexture`, and shared texture/import behavior. Probe
artifacts must use media digests instead of raw media payloads and must reject
hidden fallback.

## Input shape

The probe schema is
[`config/browser-media-path-probe.schema.json`](../../../config/browser-media-path-probe.schema.json).
Each artifact declares runtime identity, media sources, media-path probes,
capture-policy binding, fallback policy, and origin-scoped privacy policy.
When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_media_path_probe`. Probe artifacts are diagnostic
until Chromium-generated runs provide output digests and runtime identity under
the forced-Doe browser lane. The smoke report builder extracts
`copyExternalImageToTexture` and `importExternalTexture` evidence from
Playwright smoke output and marks shared texture import unsupported when the
smoke report does not exercise that path.

## Failure taxonomy

The structural checker reports:

- `missing_probe_kind`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `unknown_media_source`
- `unsafe_artifact_path`
- `missing_capture_policy`
- `wrong_capture_surface`
- `missing_capture_policy_path`
- `unsafe_capture_policy_path`
- `missing_capture_policy_file`
- `invalid_capture_policy`
- `invalid_capture_policy_kind`
- `missing_capture_surface`
- `unsafe_capture_surface`
- `missing_capture_surface_reason`
- `hidden_fallback_allowed`
- `missing_fallback_reason`
- `unsafe_privacy_policy`
- runtime identity reference failures from the shared browser runtime-identity
  reference checker

## Fallback policy

Hidden fallback is never allowed. Unsupported or fallback-applied media probes
must carry a reason code.
Media source paths and probe evidence paths must be repo-relative references;
absolute paths and parent traversal are rejected before promotion checks.
Artifacts must reference the `media_path_probe` row in the browser capture
policy. That row must be origin scoped, developer visible, gated by secure
context plus DevTools opt-in, hash raw page data, emit only hashes/redacted
metadata, and disallow replay.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Builder:
  `python3 browser/chromium/scripts/build-browser-media-path-probe.py --report <browser-smoke.json> --mode doe --out <media-path-probe.json>`
- Smoke runner hook:
  `./browser/chromium/scripts/run-smoke.sh --mode doe --media-path-probe-out <media-path-probe.json> --media-path-probe-mode doe`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-media-path-probe.py --probe examples/browser-media-path-probe.sample.json --capture-policy-root . --runtime-identity-root .`

## Promotion criteria

Promotion requires browser-generated evidence for external texture, external
image copy, and shared texture/import probes under forced Doe, with output
digests and typed unsupported/fallback reasons.
