# Browser WebGPU effect experiment contract

Status: `draft`

## Objective

Define browser effect experiments that keep HTML, CSS, layout, accessibility,
permissions, and security semantics owned by Chromium while allowing explicit
WebGPU-backed visual effect probes through Doe-visible artifacts.

## Input shape

The experiment schema is
[`config/browser-webgpu-effect-experiment.schema.json`](../../../config/browser-webgpu-effect-experiment.schema.json).
Each artifact declares effect surfaces, WGSL-backed pipelines, structural
probes, fallback policy, runtime identity, and capture privacy policy.
When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_webgpu_effect_experiment`. Experiment artifacts
remain diagnostic until forced-Doe browser runs generate them with runtime
identity, no hidden fallback, and output evidence.

`browser/chromium/scripts/build-browser-webgpu-effect-experiment.py` converts
Playwright smoke output into a WebGPU-backed visual-effect experiment for the
selected runtime mode. The builder uses smoke render output as the visual probe
while keeping layout, accessibility, and security ownership explicitly browser
owned.

## Failure taxonomy

The structural checker reports:

- `surface_not_webgpu_backed`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `duplicate_surface_id`
- `duplicate_pipeline_id`
- `duplicate_probe_id`
- `invalid_doe_boundary`
- `browser_semantics_escaped`
- `unknown_pipeline_surface`
- `missing_probe_kind`
- `unknown_probe_surface`
- `missing_fallback_reason`
- `hidden_fallback_allowed`
- `unsafe_privacy_policy`
- runtime identity reference failures from the shared browser runtime-identity
  reference checker

## Fallback policy

Hidden fallback is never allowed. Fallback-behavior probes must carry an
explicit reason code.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Smoke artifact builder:
  `python3 browser/chromium/scripts/build-browser-webgpu-effect-experiment.py --report <browser-smoke.json> --mode doe --out <browser-webgpu-effect-experiment.json>`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-webgpu-effect-experiment.py --experiment examples/browser-webgpu-effect-experiment.sample.json --runtime-identity-root .`

## Promotion criteria

Promotion requires browser-generated artifacts that prove the effect is
WebGPU-backed, keep browser semantics browser-owned, record output hashes, and
explain every unsupported capability or fallback path.
