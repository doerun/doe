# Browser GPU flight recorder contract

Status: `draft`

## Objective

Define the page-level browser artifact shape required before Doe can claim
browser-local GPU capture, replay, or developer-visible workload provenance.

The artifact schema is
[`config/browser-gpu-flight-recorder.schema.json`](../../../config/browser-gpu-flight-recorder.schema.json).
A schema-valid sample is
[`examples/browser-gpu-flight-recorder.sample.json`](../../../examples/browser-gpu-flight-recorder.sample.json).

## Input shape

A browser flight-recorder artifact must bind one page scenario to:

- browser runtime identity
- adapter identity
- active browser responsibility map version
- shader source, Doe IR, and backend output hashes
- bind groups, buffers, and textures
- command graph nodes, edges, and submit IDs
- timing phases
- frame hashes
- typed failure codes
- origin-scoped privacy policy

## Output artifacts

The recorder writes `browser_gpu_flight_recorder` artifacts. The artifact can
cite lower-level capture graphs, compiler evidence, and browser diagnostics, but
it is the page-level object used by browser replay, developer surfaces, and
claim-adjacent audits.

## Failure taxonomy

Failure codes must name the source subsystem:

- `runtime_selection`
- `browser_policy`
- `shader_compilation`
- `command_execution`
- `capture`
- `replay`
- `presentation`

Each code also carries severity so diagnostic artifacts can stay separate from
claimable artifacts.
Replay rejects top-level source artifact drift with `invalid_schema_version`
and `invalid_artifact_kind` before accepting graph replay.

## Fallback policy

Fallback state belongs in `runtimeIdentity`. A flight-recorder artifact with
`fallbackApplied=true` remains diagnostic unless the browser claim policy
explicitly accepts that fallback class.

## Privacy boundary

Capture artifacts are origin-scoped. Page data must be hashed or redacted unless
an explicit debug-capture policy is present in the artifact.

## Gate coverage

- Schema validation: `python3 bench/gates/schema_gate.py`
- Artifact builder:
  `python3 browser/chromium/scripts/build-browser-gpu-flight-recorder.py --report <browser-report.json> --components <component-manifest.json> --capture-policy config/browser-capture-policy.json --out <flight-recorder.json>`
- Browser smoke emission:
  `./browser/chromium/scripts/run-smoke.sh --mode doe --flight-recorder-components <component-manifest.json> --flight-recorder-out <flight-recorder.json> --flight-recorder-mode doe`
- Contract sample: `examples/browser-gpu-flight-recorder.sample.json`
- Structural replay:
  `python3 browser/chromium/scripts/replay-browser-gpu-flight-recorder.py --flight-recorder examples/browser-gpu-flight-recorder.sample.json --capture-policy config/browser-capture-policy.json --responsibility-map-root .`
  Replay checks command graph resource references, unique node and submit IDs,
  edge endpoints, forward ordering for ordering/presentation edges, timing
  node references, frame presentation nodes, and the referenced browser
  responsibility-map version.
- Focused regression:
  `PYTHONPATH=bench:. python3 -m pytest bench/tests/test_browser_gpu_flight_recorder_contract.py -q`

## Promotion criteria

The flight-recorder prototype can promote only after generated browser artifacts
validate against the schema, replay failures are typed, and the browser claim
policy rejects hidden fallback and unbound responsibility-map surfaces.
