# Browser GPU scheduler contract

Status: `draft`

## Objective

Define a page-level scheduler probe contract for WebGPU, canvas, video, CSS
effects, local AI, and compositor-adjacent GPU work. The contract records
scheduler evidence without moving browser policy, layout, or accessibility
semantics into Doe.

## Input shape

The probe schema is
[`config/browser-gpu-scheduler.schema.json`](../../../config/browser-gpu-scheduler.schema.json).
Each probe declares work classes, covered surfaces, probe kind, evidence path,
status, fallback policy, and privacy policy.
When `--runtime-identity-root` is supplied, the checker resolves
`runtimeIdentity.runtimeIdentityPath` and requires its selected runtime and
fallback state to match either a `browser_runtime_identity` artifact or the
referenced browser smoke report.

## Output artifacts

The artifact kind is `browser_gpu_scheduler_probe`. Probe artifacts are
diagnostic until forced-Doe browser runs generate them with runtime identity and
no hidden fallback.

`browser/chromium/scripts/build-browser-gpu-scheduler.py` converts Playwright
smoke output into a scheduler probe for the selected runtime mode. It binds the
six required work surfaces and marks scheduler behavior that the smoke lane does
not measure as typed diagnostic evidence.

## Failure taxonomy

The structural checker reports:

- `missing_surface`
- `invalid_schema_version`
- `invalid_artifact_kind`
- `duplicate_work_class_id`
- `duplicate_probe_id`
- `missing_probe_kind`
- `unknown_work_class`
- `missing_fallback_reason`
- `hidden_fallback_allowed`
- `unsafe_privacy_policy`
- runtime identity reference failures from the shared browser runtime-identity
  reference checker

## Fallback policy

Hidden fallback is never allowed. Any fallback behavior probe must carry a
reason code.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Smoke artifact builder:
  `python3 browser/chromium/scripts/build-browser-gpu-scheduler.py --report <browser-smoke.json> --mode doe --out <browser-gpu-scheduler.json>`
- Structural check:
  `python3 browser/chromium/scripts/check-browser-gpu-scheduler.py --probe examples/browser-gpu-scheduler.sample.json --runtime-identity-root .`

## Promotion criteria

Promotion requires generated browser artifacts covering priority, fairness,
frame deadline, origin quota, device loss, and fallback behavior for the
declared work classes.
