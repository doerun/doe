# Browser lane

This file is a routing note, not a second task list.

The canonical Chromium WebGPU task list is
[`chromium-webgpu-task-list.md`](./chromium-webgpu-task-list.md). The executable
browser integration layer is [`../browser/chromium/`](../browser/chromium/README.md).

## Boundaries

- `packages/doe-gpu/src/browser.js` is only the package browser wrapper. It
  delegates to the browser's existing `navigator.gpu` and does not prove Doe
  browser execution.
- `browser/chromium/` owns contracts, scripts, diagnostics, and lane-local
  artifacts for forced-Doe Chromium work.
- `browser/chromium_webgpu_lane/` or `FAWN_CHROMIUM_LANE_DIR` owns the actual
  Chromium checkout/build workspace.
- Browser smoke, layered browser benchmarks, browser claim gates, and native
  Dawn-vs-Doe runtime claims are separate artifact lanes.

## Required task sources

- Task list:
  [`chromium-webgpu-task-list.md`](./chromium-webgpu-task-list.md)
- Browser plan:
  [`../browser/chromium/plan.md`](../browser/chromium/plan.md)
- Milestone manifest:
  [`../browser/chromium/bench/workflows/browser-milestones.json`](../browser/chromium/bench/workflows/browser-milestones.json)
- Runtime selector contract:
  [`../browser/chromium/contracts/runtime-selector-and-fallback.contract.md`](../browser/chromium/contracts/runtime-selector-and-fallback.contract.md)
  with policy at
  [`../config/browser-runtime-selector-policy.json`](../config/browser-runtime-selector-policy.json)
- Browser benchmark contract:
  [`../browser/chromium/contracts/browser-benchmark-superset.contract.md`](../browser/chromium/contracts/browser-benchmark-superset.contract.md)
- Browser claim methodology:
  [`../browser/chromium/contracts/browser-claim-methodology.contract.md`](../browser/chromium/contracts/browser-claim-methodology.contract.md)
- Browser responsibility map:
  [`../browser/chromium/contracts/browser-responsibility-map.contract.md`](../browser/chromium/contracts/browser-responsibility-map.contract.md)
  with schema-backed map at
  [`../config/browser-responsibility-map.json`](../config/browser-responsibility-map.json)
- Browser GPU flight recorder:
  [`../browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`](../browser/chromium/contracts/browser-gpu-flight-recorder.contract.md)
  with sample artifact schema at
  [`../examples/browser-gpu-flight-recorder.sample.json`](../examples/browser-gpu-flight-recorder.sample.json);
  replay checks command graph identity, ordering, and responsibility-map version
  binding before accepting the capture.
- Browser canvas/WebGPU fusion:
  [`../browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md`](../browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md)
  with sample probe at
  [`../examples/browser-canvas-webgpu-fusion.sample.json`](../examples/browser-canvas-webgpu-fusion.sample.json);
  derived probe checkers can verify `runtimeIdentity.runtimeIdentityPath`
  against either a `browser_runtime_identity` artifact or the source smoke
  report with `--runtime-identity-root`.
- Browser shader links:
  [`../browser/chromium/contracts/browser-shader-links.contract.md`](../browser/chromium/contracts/browser-shader-links.contract.md)
  with sample artifact at
  [`../examples/browser-shader-links.sample.json`](../examples/browser-shader-links.sample.json);
  checker verification links rows back to both the flight recorder and WGSL
  lowering receipt.
- Browser GPU scheduler:
  [`../browser/chromium/contracts/browser-gpu-scheduler.contract.md`](../browser/chromium/contracts/browser-gpu-scheduler.contract.md)
  with sample probe at
  [`../examples/browser-gpu-scheduler.sample.json`](../examples/browser-gpu-scheduler.sample.json);
  runtime identity reference verification rejects selected-runtime or
  fallback-state drift when enabled.
- Browser WebGPU effect experiment:
  [`../browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md`](../browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md)
  with sample artifact at
  [`../examples/browser-webgpu-effect-experiment.sample.json`](../examples/browser-webgpu-effect-experiment.sample.json)
- Browser local AI workloads:
  [`../browser/chromium/contracts/browser-local-ai-workloads.contract.md`](../browser/chromium/contracts/browser-local-ai-workloads.contract.md)
  with sample artifact at
  [`../examples/browser-local-ai-workloads.sample.json`](../examples/browser-local-ai-workloads.sample.json);
  runtime identity reference verification binds workload rows back to the
  runtime evidence named by `runtimeIdentityPath`.
- Browser pipeline cache receipts:
  [`../browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`](../browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md)
  with sample artifact at
  [`../examples/browser-pipeline-cache-receipts.sample.json`](../examples/browser-pipeline-cache-receipts.sample.json);
  receipts carry source workload linkage and shader source/IR/backend hashes.
- Browser fallback explanations:
  [`../browser/chromium/contracts/browser-fallback-explanations.contract.md`](../browser/chromium/contracts/browser-fallback-explanations.contract.md)
  with sample artifact at
  [`../examples/browser-fallback-explanations.sample.json`](../examples/browser-fallback-explanations.sample.json)
- Browser unsupported/fallback reason taxonomy:
  [`../config/browser-unsupported-reason-taxonomy.json`](../config/browser-unsupported-reason-taxonomy.json)
  with checker
  [`../bench/tools/check_browser_unsupported_reason_taxonomy.py`](../bench/tools/check_browser_unsupported_reason_taxonomy.py)
- Browser media path probe:
  [`../browser/chromium/contracts/browser-media-path-probe.contract.md`](../browser/chromium/contracts/browser-media-path-probe.contract.md)
  with sample probe at
  [`../examples/browser-media-path-probe.sample.json`](../examples/browser-media-path-probe.sample.json)
  and `media_path_probe` capture-policy binding in
  [`../config/browser-capture-policy.json`](../config/browser-capture-policy.json)
- Browser artifact identity coverage:
  [`../config/browser-artifact-identity-coverage.json`](../config/browser-artifact-identity-coverage.json)
  with checker
  [`../bench/tools/check_browser_artifact_identity_coverage.py`](../bench/tools/check_browser_artifact_identity_coverage.py)
- Browser recovery parity:
  [`../browser/chromium/contracts/browser-recovery-parity.contract.md`](../browser/chromium/contracts/browser-recovery-parity.contract.md)
  with sample artifact at
  [`../examples/browser-recovery-parity.sample.json`](../examples/browser-recovery-parity.sample.json)
- Browser CTS subset:
  [`../browser/chromium/contracts/browser-cts-subset.contract.md`](../browser/chromium/contracts/browser-cts-subset.contract.md)
  with sample artifact at
  [`../examples/browser-cts-subset.sample.json`](../examples/browser-cts-subset.sample.json)

## Archived module note

The old Track B module designs for SDF rendering, path processing, effects,
compute services, and resource scheduling are archived. Use them only as
contract references. New browser work starts from the canonical task list and
must promote through schema, trace, gate, and artifact contracts before it can
affect runtime behavior.
