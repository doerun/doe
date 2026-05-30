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
- Require the Chromium source checkout gate with `--require-runtime-selector`
  before claiming source-level runtime selector ownership.
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
  hash, Dawn fallback runtime hash, runtime selector version, adapter identity,
  and fallback state.
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
- Require browser pipeline cache receipts to cover every source local-AI
  workload and match its shader source/IR/backend identity hashes.
- Add a developer-visible runtime identity surface that exposes which runtime
  compiled and executed a workload.
- Require derived browser artifacts to verify `runtimeIdentityPath` against
  the referenced runtime identity artifact or smoke report before accepting
  selected-runtime and fallback state.
- Add developer-visible shader links from page source to Doe IR to backend
  output.
- Require browser shader links to match the source flight-recorder shader rows
  before checking their WGSL lowering receipt rows.
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
- Browser responsibility map:
  [`../browser/chromium/contracts/browser-responsibility-map.contract.md`](../browser/chromium/contracts/browser-responsibility-map.contract.md)
- Browser responsibility map checker:
  [`../bench/tools/check_browser_responsibility_map.py`](../bench/tools/check_browser_responsibility_map.py)
- Browser GPU flight recorder:
  [`../browser/chromium/contracts/browser-gpu-flight-recorder.contract.md`](../browser/chromium/contracts/browser-gpu-flight-recorder.contract.md)
  with replay checks for resource references, unique node/submit IDs, edge
  ordering, timing nodes, frame presentation nodes, and responsibility-map
  version binding.
- Browser canvas/WebGPU fusion:
  [`../browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md`](../browser/chromium/contracts/browser-canvas-webgpu-fusion.contract.md)
- Browser canvas/WebGPU fusion builder:
  [`../browser/chromium/scripts/build-browser-canvas-webgpu-fusion.py`](../browser/chromium/scripts/build-browser-canvas-webgpu-fusion.py)
- Browser shader links:
  [`../browser/chromium/contracts/browser-shader-links.contract.md`](../browser/chromium/contracts/browser-shader-links.contract.md)
- Browser shader links checker:
  [`../browser/chromium/scripts/check-browser-shader-links.py`](../browser/chromium/scripts/check-browser-shader-links.py)
  with flight-recorder and WGSL lowering receipt verification.
- Browser GPU scheduler:
  [`../browser/chromium/contracts/browser-gpu-scheduler.contract.md`](../browser/chromium/contracts/browser-gpu-scheduler.contract.md)
- Browser GPU scheduler builder:
  [`../browser/chromium/scripts/build-browser-gpu-scheduler.py`](../browser/chromium/scripts/build-browser-gpu-scheduler.py)
- Browser WebGPU effect experiment:
  [`../browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md`](../browser/chromium/contracts/browser-webgpu-effect-experiment.contract.md)
- Browser WebGPU effect experiment builder:
  [`../browser/chromium/scripts/build-browser-webgpu-effect-experiment.py`](../browser/chromium/scripts/build-browser-webgpu-effect-experiment.py)
- Browser local AI workloads:
  [`../browser/chromium/contracts/browser-local-ai-workloads.contract.md`](../browser/chromium/contracts/browser-local-ai-workloads.contract.md)
- Browser local AI workloads builder:
  [`../browser/chromium/scripts/build-browser-local-ai-workloads.py`](../browser/chromium/scripts/build-browser-local-ai-workloads.py)
- Browser pipeline cache receipts:
  [`../browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md`](../browser/chromium/contracts/browser-pipeline-cache-receipts.contract.md)
  with source local-AI workload coverage and shader source/IR/backend hash
  linkage.
- Browser fallback explanations:
  [`../browser/chromium/contracts/browser-fallback-explanations.contract.md`](../browser/chromium/contracts/browser-fallback-explanations.contract.md)
- Browser fallback explanations builder:
  [`../browser/chromium/scripts/build-browser-fallback-explanations.py`](../browser/chromium/scripts/build-browser-fallback-explanations.py)
- Browser unsupported/fallback reason taxonomy:
  [`../config/browser-unsupported-reason-taxonomy.json`](../config/browser-unsupported-reason-taxonomy.json)
- Browser media path probe:
  [`../browser/chromium/contracts/browser-media-path-probe.contract.md`](../browser/chromium/contracts/browser-media-path-probe.contract.md)
- Browser media path probe builder:
  [`../browser/chromium/scripts/build-browser-media-path-probe.py`](../browser/chromium/scripts/build-browser-media-path-probe.py)
- Browser media path probe checker:
  [`../browser/chromium/scripts/check-browser-media-path-probe.py`](../browser/chromium/scripts/check-browser-media-path-probe.py)
- Browser recovery parity:
  [`../browser/chromium/contracts/browser-recovery-parity.contract.md`](../browser/chromium/contracts/browser-recovery-parity.contract.md)
- Browser recovery parity builder:
  [`../browser/chromium/scripts/build-browser-recovery-parity.py`](../browser/chromium/scripts/build-browser-recovery-parity.py)
- Browser CTS subset:
  [`../browser/chromium/contracts/browser-cts-subset.contract.md`](../browser/chromium/contracts/browser-cts-subset.contract.md)
- Browser CTS subset builder:
  [`../browser/chromium/scripts/build-browser-cts-subset.py`](../browser/chromium/scripts/build-browser-cts-subset.py)
- Runtime selector contract:
  [`../browser/chromium/contracts/runtime-selector-and-fallback.contract.md`](../browser/chromium/contracts/runtime-selector-and-fallback.contract.md)
- Runtime selector policy:
  [`../config/browser-runtime-selector-policy.json`](../config/browser-runtime-selector-policy.json)
- Browser capture policy:
  [`../config/browser-capture-policy.json`](../config/browser-capture-policy.json)
- Browser artifact identity coverage:
  [`../config/browser-artifact-identity-coverage.json`](../config/browser-artifact-identity-coverage.json)
- Browser unsupported/fallback reason taxonomy checker:
  [`../bench/tools/check_browser_unsupported_reason_taxonomy.py`](../bench/tools/check_browser_unsupported_reason_taxonomy.py)
- Chromium fork maintenance policy:
  [`../config/chromium-fork-maintenance-policy.json`](../config/chromium-fork-maintenance-policy.json)
- Chromium patch manifest:
  [`../config/chromium-patch-manifest.json`](../config/chromium-patch-manifest.json)
- Chromium source checkout preflight:
  [`../bench/tools/check_chromium_source_checkout.py`](../bench/tools/check_chromium_source_checkout.py)
- Browser release artifact bundle:
  [`../bench/tools/build_browser_release_artifact_bundle.py`](../bench/tools/build_browser_release_artifact_bundle.py),
  [`../bench/tools/check_browser_release_artifact_bundle.py`](../bench/tools/check_browser_release_artifact_bundle.py)
- Browser claim promotion receipt:
  [`../bench/tools/build_browser_claim_promotion_receipt.py`](../bench/tools/build_browser_claim_promotion_receipt.py),
  [`../bench/tools/check_browser_claim_promotion_receipt.py`](../bench/tools/check_browser_claim_promotion_receipt.py)
- Browser benchmark superset contract:
  [`../browser/chromium/contracts/browser-benchmark-superset.contract.md`](../browser/chromium/contracts/browser-benchmark-superset.contract.md)
- Native command graph receipt:
  [`../bench/tools/build_native_command_graph_receipt.py`](../bench/tools/build_native_command_graph_receipt.py)
- Native command graph replay:
  [`../bench/tools/replay_native_command_graph_receipt.py`](../bench/tools/replay_native_command_graph_receipt.py)
- Native no-fallback report:
  [`../bench/tools/build_native_no_fallback_report.py`](../bench/tools/build_native_no_fallback_report.py)
- Native pipeline cache receipts:
  [`../bench/tools/check_native_pipeline_cache_receipts.py`](../bench/tools/check_native_pipeline_cache_receipts.py)
- Native upload path receipts:
  [`../bench/tools/check_native_upload_path_receipts.py`](../bench/tools/check_native_upload_path_receipts.py)
- Native resource reuse receipts:
  [`../bench/tools/check_native_resource_reuse_receipts.py`](../bench/tools/check_native_resource_reuse_receipts.py)
- Native backend coverage matrix:
  [`../config/native-backend-coverage-matrix.json`](../config/native-backend-coverage-matrix.json)
- Compare output partition gate:
  [`../bench/gates/compare_output_partition_gate.py`](../bench/gates/compare_output_partition_gate.py)
- Compiler evidence gate:
  [`../bench/gates/tint_compiler_evidence_gate.py`](../bench/gates/tint_compiler_evidence_gate.py)
- Browser WGSL corpus manifest:
  [`../config/wgsl-browser-corpus.json`](../config/wgsl-browser-corpus.json)
- WGSL corpus materializer:
  [`../bench/tools/materialize_wgsl_corpus_manifest.py`](../bench/tools/materialize_wgsl_corpus_manifest.py)
- WGSL CTS shader subset:
  [`../bench/tools/build_wgsl_cts_shader_subset.py`](../bench/tools/build_wgsl_cts_shader_subset.py)
- WGSL diagnostic fixtures:
  [`../config/wgsl-diagnostic-fixtures.json`](../config/wgsl-diagnostic-fixtures.json)
- WGSL minimization receipt:
  [`../bench/tools/minimize_wgsl_corpus_failure.py`](../bench/tools/minimize_wgsl_corpus_failure.py)
- WGSL lowering link receipt:
  [`../bench/tools/build_wgsl_lowering_link_receipt.py`](../bench/tools/build_wgsl_lowering_link_receipt.py)
- WGSL robustness fixtures:
  [`../config/wgsl-robustness-fixtures.json`](../config/wgsl-robustness-fixtures.json)
- Runtime compare policy:
  [`performance-strategy.md`](./performance-strategy.md)
