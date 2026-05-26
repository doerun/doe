# Chromium WebGPU task list

This is the canonical task list for making Doe a stronger Chromium WebGPU
implementation path than the Dawn/Tint incumbent. Keep this file task-only:
what to build, gate, prove, or remove. Strategy prose belongs in
[`thesis.md`](./thesis.md); current evidence belongs in
[`status.md`](./status.md) and artifact reports.

## Task routing

- Keep browser execution tasks under [`../browser/chromium/`](../browser/chromium/README.md).
- Keep compiler work under [`../runtime/zig/src/doe_wgsl/`](../runtime/zig/src/doe_wgsl/).
- Keep runtime backend work under [`../runtime/zig/src/backend/`](../runtime/zig/src/backend/).
- Keep benchmark and claim gates under [`../bench/`](../bench/README.md).
- Keep contracts and schemas under [`../config/`](../config/).
- Keep live status in [`status/compiler-and-webgpu.md`](./status/compiler-and-webgpu.md) and
  [`status/runtime-backends-and-bench.md`](./status/runtime-backends-and-bench.md).

## Non-negotiable task gates

- Every performance claim must pass strict Dawn/Tint comparability gates.
- Every forced-Doe Chromium claim must prove hidden fallback is disabled.
- Every browser artifact must identify the browser executable, Doe runtime,
  Dawn fallback runtime, shader compiler, workload, adapter, and trace chain.
- Every unsupported path must emit a typed failure code.
- Every task that changes runtime-visible behavior must update schema, docs, and
  status in the same change.

## Compiler tasks: Doe vs Tint

- Build and maintain a WGSL corpus manifest covering browser shaders, canvas
  workloads, WebGPU samples, model inference kernels, game-engine shaders, and
  invalid diagnostic fixtures.
- Add or extend corpus materializers so every shader row records source path,
  normalized source hash, expected validity, expected backend targets, and
  provenance.
- Run Doe and Tint on the same corpus rows with matched parse, validation,
  lowering, emit, and validation phases where both toolchains expose comparable
  boundaries.
- Require every claimable compiler row to carry Doe tool identity, Tint tool
  identity, warm Tint benchmark identity, source hash, IR hash, backend output
  hash, validation result, and diagnostic status.
- Expand `bench/gates/tint_compiler_evidence_gate.py` when a new compiler
  artifact field becomes required for claimability.
- Close WGSL frontend gaps found by the corpus: parsing, semantic validation,
  address-space handling, builtins, type rules, diagnostic spans, and error
  taxonomy.
- Close backend emission gaps for MSL, SPIR-V, DXIL/HLSL, and any browser-lane
  target promoted into the support matrix.
- Add robustness-transform fixtures for every bounds, aliasing, texture
  dimension, and guard pattern used by browser-facing workloads.
- Add invalid-shader diagnostic quality fixtures and compare Doe/Tint failure
  messages by typed category, not free-form text.
- Add shader minimization tooling for corpus failures so a failing browser
  shader can be reduced without losing source/backend identity.
- Add CTS shader-subset ingestion and make the compiler evidence report link
  CTS rows to the same source/output hash contract.
- Emit source-to-IR-to-backend receipts from compiler runs so browser artifacts
  can link a page shader to the exact lowered output.

## Runtime tasks: Doe vs Dawn

- Keep strict native Dawn-vs-Doe compare reports on matched workload contracts
  with structural work equivalence.
- Audit every claimable workload for command count, dispatch count, resource
  setup, submit/wait scope, readback scope, and success count on both sides.
- Reject claimability when either side skips a command, reports zero dispatches
  for executed work, or reports a timing phase that the other side measures.
- Expand Metal runtime coverage for upload, pipeline creation, compute,
  readback, small command streams, cache behavior, concurrency, and tails.
- Expand Vulkan runtime coverage for the same workload classes before any
  cross-platform claim is promoted.
- Add D3D12/DXIL runtime coverage before any Windows browser path is promoted.
- Implement and benchmark pipeline cache behavior with explicit cold/warm mode
  contracts.
- Implement and benchmark allocation-light upload paths without hiding
  hardware-path asymmetry.
- Implement and benchmark command encoder/resource reuse where workload
  semantics allow it.
- Emit command graph receipts from native runtime runs: buffers, textures,
  pipeline IDs, bind group IDs, command ordering, submit IDs, and trace hashes.
- Add deterministic replay checks for native command graph receipts.
- Keep no-fallback reports for strict Doe runtime paths.
- Keep `diagnostic` output separate from `claimable` output in every compare
  artifact and gate.

## Chromium seam tasks

- Keep the browser wrapper path separate from Chromium integration; the package
  wrapper does not prove Doe browser execution.
- Wire Chromium runtime selection to explicit `dawn`, `doe`, and `auto` modes.
- Add an emergency kill switch that selects Dawn without changing schemas or
  artifact history.
- Add deterministic denylist/profile fallback with typed reason codes.
- Make forced `doe` mode fail closed when Doe cannot initialize; do not silently
  select Dawn.
- Bind Doe at the `navigator.gpu` WebGPU runtime seam without changing the
  renderer process model, GPU process boundary, sandbox model, layout engine,
  media policy, or accessibility policy.
- Keep Dawn available as the compatibility runtime until replacement gates say
  otherwise.
- Require browser-lane reports to record browser executable hash, Doe runtime
  hash, Dawn delegate hash, runtime selector version, adapter identity, and
  fallback state.
- Add browser-level WebGPU smoke, layered workload, and CTS subset artifacts for
  both Dawn and forced Doe.
- Add canvas and presentation-path probes that verify `GPUCanvasContext`
  behavior under forced Doe.
- Add external texture and media-path probes for `GPUExternalTexture`,
  `copyExternalImageToTexture`, and shared texture/import behavior.
- Add ORT/browser model workloads that exercise model warmup, pipeline reuse,
  dispatch, upload, and readback inside Chromium.
- Add crash, hang, device-loss, validation-error, and recovery parity checks
  against the Dawn lane.
- Promote a browser claim lane only when repeated forced-Doe browser artifacts
  pass the browser claim policy and strict hidden-fallback checks.

## Browser end-to-end responsibility map tasks

- Add a browser responsibility map that separates CPU-owned browser duties from
  GPU-owned browser duties.
- CPU-owned map entries must include networking, cache, HTML parsing, CSS
  parsing, cascade, DOM, style tree, layout, JavaScript execution, event loop,
  accessibility tree, permissions, origin policy, scheduling, lifecycle,
  workers, service workers, and developer tooling.
- GPU-owned map entries must include rasterization, compositing, canvas 2D,
  WebGL, WebGPU, image filters, CSS effects, transforms, texture upload,
  readback, video presentation, swapchain/surface presentation, GPU memory
  residency, command submission, pipeline cache, shader compilation, and frame
  pacing.
- Boundary map entries must name every CPU/GPU crossing that Doe can observe,
  optimize, schedule, or receipt.
- Mark every map entry as one of: `not_doe_scope`, `webgpu_seam`,
  `doe_observable`, `doe_schedulable`, `doe_claim_candidate`, or
  `blocked_by_browser_policy`.
- Link each `doe_claim_candidate` entry to a contract, schema, workload, gate,
  and artifact path before any claim language is allowed.

## Browser capability tasks beyond current Chrome behavior

- Build a page-level GPU flight-recorder contract that captures shaders, IR,
  backend output, bind groups, buffers, textures, command graphs, timings,
  adapter identity, frame hashes, and failure codes.
- Implement a browser flight-recorder prototype for WebGPU workloads under
  forced Doe.
- Add replay tooling for flight-recorder artifacts and make replay failures
  typed.
- Add a canvas/WebGPU fusion contract that lets canvas 2D, WebGPU, image
  filters, and presentation work share a visible Doe graph when the browser path
  exposes stable command boundaries.
- Add canvas/WebGPU fusion probes that compare output hashes, timing scopes, and
  fallback reasons.
- Add a page-level GPU scheduler contract for WebGPU, canvas, video, CSS
  effects, local AI, and compositor-adjacent work.
- Add scheduler probes for priority, fairness, frame deadline, origin quota,
  device loss, and fallback behavior.
- Add inline HTML/CSS GPU effect experiments only as explicit WebGPU-backed
  effects; do not move layout, accessibility, or security semantics into Doe.
- Add a local AI browser workload set for embeddings, ranking, image/video
  transforms, and model inference under Chromium.
- Emit receipts for every local AI browser workload: model identity, shader
  identity, pipeline cache state, input contract, output digest, and fallback
  status.
- Add a developer-visible runtime identity surface that exposes which runtime
  compiled and executed a workload.
- Add developer-visible shader links from page source to Doe IR to backend
  output.
- Add developer-visible cache hit/miss and pipeline creation receipts.
- Add developer-visible unsupported-capability and fallback explanations.

## Security and fork-maintenance tasks

- Keep capture artifacts origin-scoped and redact or hash page data that must
  not leave the browser boundary.
- Add permission and policy checks for any developer-visible capture or replay
  surface.
- Keep Doe integration inside the WebGPU seam unless a browser responsibility
  map entry has a promoted contract and gate.
- Keep Chromium fork patches isolated enough to rebase with Chromium security
  updates.
- Keep a Dawn fallback path and rollback procedure for release builds.
- Add release artifacts that prove the shipped browser binary, Doe runtime,
  compiler, contracts, and browser claim reports match.

## Current task ledgers

- Browser milestone state:
  [`../browser/chromium/bench/workflows/browser-milestones.json`](../browser/chromium/bench/workflows/browser-milestones.json)
- Browser acceptance plan:
  [`../browser/chromium/plan.md`](../browser/chromium/plan.md)
- Browser claim methodology:
  [`../browser/chromium/contracts/browser-claim-methodology.contract.md`](../browser/chromium/contracts/browser-claim-methodology.contract.md)
- Runtime selector contract:
  [`../browser/chromium/contracts/runtime-selector-and-fallback.contract.md`](../browser/chromium/contracts/runtime-selector-and-fallback.contract.md)
- Browser benchmark superset contract:
  [`../browser/chromium/contracts/browser-benchmark-superset.contract.md`](../browser/chromium/contracts/browser-benchmark-superset.contract.md)
- Compiler evidence gate:
  [`../bench/gates/tint_compiler_evidence_gate.py`](../bench/gates/tint_compiler_evidence_gate.py)
- Runtime compare policy:
  [`performance-strategy.md`](./performance-strategy.md)
