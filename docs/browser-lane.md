# Browser lane

This file is a routing note, not a second task list.

The canonical Chromium WebGPU task list is
[`chromium-webgpu-dominance.md`](./chromium-webgpu-dominance.md). The executable
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
  [`chromium-webgpu-dominance.md`](./chromium-webgpu-dominance.md)
- Browser plan:
  [`../browser/chromium/plan.md`](../browser/chromium/plan.md)
- Milestone manifest:
  [`../browser/chromium/bench/workflows/browser-milestones.json`](../browser/chromium/bench/workflows/browser-milestones.json)
- Runtime selector contract:
  [`../browser/chromium/contracts/runtime-selector-and-fallback.contract.md`](../browser/chromium/contracts/runtime-selector-and-fallback.contract.md)
- Browser benchmark contract:
  [`../browser/chromium/contracts/browser-benchmark-superset.contract.md`](../browser/chromium/contracts/browser-benchmark-superset.contract.md)
- Browser claim methodology:
  [`../browser/chromium/contracts/browser-claim-methodology.contract.md`](../browser/chromium/contracts/browser-claim-methodology.contract.md)

## Archived module note

The old Track B module designs for SDF rendering, path processing, effects,
compute services, and resource scheduling are archived. Use them only as
contract references. New browser work starts from the canonical task list and
must promote through schema, trace, gate, and artifact contracts before it can
affect runtime behavior.
