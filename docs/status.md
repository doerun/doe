# Doe status

This file is the front door for Doe project status.

Read this file first. Use the shard files under
[`docs/status/`](/Users/xyz/deco/doe/docs/status) for the dated history.

## How to use the status log

- Keep this file concise. It is the mandatory-reading summary, not the full
  ledger.
- Current shard: [`docs/status/2026-04.md`](/Users/xyz/deco/doe/docs/status/2026-04.md).
- Add new dated status entries to the current shard at the top of that shard
  file.
- Historical shard files are append-only. Do not rewrite old entries except for
  deliberate archive maintenance like this sharding change.
- When a task leaves placeholders, temporary methodology choices, or follow-up
  work, record that in the current shard and refresh this front door only if
  the current summary materially changes.

## Current status summary

- The CSL emitter floor has moved to Cerebras SDK 2.10. Generated PE programs
  now use the SDK 2.10 untyped parameter form for `memcpy_params` /
  `c2d_params`, fabric DSDs bind colors through explicit queues instead of
  `fabric_color`, and the E2B self-check has a source hygiene lock for removed
  SDK-1.4-only constructs.
  Existing SDK 1.4 simulator receipts remain historical until regenerated.
- Gemma-4 E2B manifest-shape evidence now includes a CPU/Numpy oracle at
  `bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json`.
  It executes the raw BF16 text checkpoint at upstream tensor dimensions and
  keeps Doe/CSL runtime, hardware, Doppler production parity, and performance
  claims blocked. See the current April shard for the scope boundary.
- Apple Metal native Doe-vs-Dawn compare defaults are now fair-cold: default Metal executor ids pass `--no-pipeline-cache`, cache-enabled runs require explicit opt-in executor ids, report-level comparability coherence is default-on in `run_blocking_gates.py`, and the committed Metal archive is documented as a benchmark fixture rather than a product runtime contract. See `bench/docs/metal-pipeline-cache-policy.md` and the current April shard.
- A fresh Mac fair-cold compare at `bench/out/apple-metal/compare/20260416T212500Z/dawn-vs-doe.apple.metal.compare.{json,claim.json}` recovers four of the seven previously cache-asymmetric compute workloads as strict claimable on `mac.lan` with Doe faster: `compute_workgroup_atomic_1024` (+9.6%), `compute_workgroup_non_atomic_1024` (+10.9%), `compute_zero_initialize_workgroup_memory_256` (+69.1%), `compute_concurrent_execution_single` (+4.3%). Both sides carry `pipelineCache.state="disabled" reason="cli-flag"`, confirming the end-to-end schema round-trip on Mac. Three matvec workloads still need a fair-cold Mac rerun.
- Pipeline-cache direction differs by backend: Metal has Doe-ahead (Doe opens `MTLBinaryArchive`, Dawn delegate does not), Vulkan has Dawn-ahead (Dawn uses `PipelineCacheVk`, Doe passes `VK_NULL_U64`), D3D12 has Dawn-ahead (Dawn populates `CachedPSO.pCachedBlob`, Doe zero-initializes). The three-backend audit is at `bench/docs/pipeline-cache-backend-audit.md`. Existing AMD Vulkan claimable evidence is unchanged -- current Doe wins are runtime-engineering wins despite the Vulkan cache gap -- and the path to "Doe faster across all boards" splits into two programs: Metal Dawn-cache shim (Push 4 design) and Doe-side Vulkan + D3D12 cache implementation.
- Doe-side Vulkan `VkPipelineCache` has landed (with optional disk persistence via `--pipeline-cache-dir`). Fresh strict AMD Vulkan compare at `bench/out/amd-vulkan/compare/20260417T114917Z/dawn-vs-doe.amd.vulkan.compare.{json,claim.json}` shows 10 of 11 workloads individually claimable -- including `compute_matvec_32768x2048_f32_swizzle1` (+11.26%), `compute_workgroup_atomic_1024` (+48.05%), `compute_workgroup_non_atomic_1024` (+49.90%), `pipeline_compile_stress` (+86.83%), and all 4 upload rows. The matvec naive_swizzle0 regression narrowed from -38.62% to -4.33% once Doe had cache parity with Dawn; the remaining Vulkan-side cache work is D3D12 CachedPSO (pending Windows host).
- Apple Metal package compute has narrow claimable warm package artifacts on
  `mac.lan`. The current Node artifacts are
  `bench/out/apple-metal/20260414T010826Z/gemma64.node-package.warm.ir.compare.json`
  and `bench/out/apple-metal/20260414T010826Z/gemma64.node-package.warm.ir.claim.json`.
  The current Bun artifacts are
  `bench/out/apple-metal/20260414T010736Z/gemma64.bun-package.warm.ir.compare.json`
  and `bench/out/apple-metal/20260414T010736Z/gemma64.bun-package.warm.ir.claim.json`.
  A stale home-level Bun install briefly caused fresh incumbent reruns to fall
  onto a Null adapter, but `bun install` restored Metal bring-up on the current
  host; see the current April shard plus
  `bench/out/scratch/bun-null-backend-20260415.meta.json` and
  `bench/out/scratch/gemma64.bun-package.warm.ir.compare.postinstall.json`.
  These remain narrow Apple Metal package lanes, not a blanket Metal claim.
- The promoted package compare front door now covers Apple Metal, AMD Vulkan,
  and local D3D12 for Node/Bun cold and warm Gemma64/Gemma1B package profiles.
  D3D12 remains a promoted contract pending Windows/D3D12 host evidence; older
  AMD Vulkan Gemma270M package compares remain explicit config-backed local
  claim surfaces outside the promoted package profile set.
- A repo-only same-stack Bun ORT WebGPU provider-compare lane now exists at
  `bench/native-compare/compare.config.bun.ort-webgpu-provider.gemma270m.prefill32.decode1.json`.
  The current local Bun host artifacts at
  `bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.compare.json`
  and `bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.claim.json`
  record a strict comparable local Doe-advantage claim against the `bun-webgpu`
  package surface on Gemma-3 270M `prefill 32 / decode 1`.
- A broader two-shape repo-only Bun ORT WebGPU package matrix now also exists
  at `bench/native-compare/compare.config.bun.ort-webgpu-provider.breadth.json`.
  Its current local artifact at
  `bench/out/bun-ort-webgpu-provider-breadth/20260413T181619Z/breadth.compare.json`
  is still mixed across the short and prefill-heavy Gemma-3 270M shapes.
- A repo-only same-stack Node ORT WebGPU provider-compare lane now exists at
  `bench/native-compare/compare.config.node.ort-webgpu-provider.gemma270m.json`.
  The current AMD RADV host artifacts at
  `bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.compare.json`
  and `bench/out/node-ort-webgpu-provider-compare/20260413T191817Z/gemma270m.claim.json`
  record a strict comparable local Doe-advantage claim against the hardware-pinned
  `node-webgpu` package surface. The current Node provider-compare scenarios now
  also use the local Transformers cache root, matching the Bun contract instead
  of mixing model-id lookup on Node with local-model lookup on Bun.
- A repo-only same-stack browser ORT WebGPU Playwright surface now exists at
  `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`, and it now also
  has a repo-only strict comparable `bench/` surface at
  `bench/native-compare/compare.config.browser.ort-webgpu.json`. The browser
  harness supports the vendored DistilBERT `sentiment`, `sentiment_medium`, and
  `sentiment_longform` workloads on this Linux host. The current canonical
  browser compare artifact at
  `bench/out/browser-ort-webgpu-compare/20260420T203851Z/browser.compare.json`
  is strict/comparable across all three workloads with report-level
  comparability coherence passing on this host.
- A broader five-shape repo-only Node ORT WebGPU package matrix now also exists
  at `bench/native-compare/compare.config.node.ort-webgpu-provider.breadth.json`.
  Its current AMD RADV host artifact at
  `bench/out/node-ort-webgpu-provider-breadth/20260413T192150Z/breadth.compare.json`
  has a positive overall mean after the Node local-model contract normalization,
  but it is still mixed across the current `64/64`, short, prefill-heavy,
  decode-heavy, and 1B shapes, so the broader matrix still does not support a
  blanket Doe-over-Dawn ORT package claim today.
- The repo-only ONNX Runtime plugin EP now crosses the line from pure scaffold
  to a narrow non-trivial native slice: Doe claims, compiles, and executes
  same-shape float32 ONNX `Identity`, `Add`, `Relu`, rank-2 `MatMul`, and
  exact two-node `MatMul -> Add` / `Add -> Relu` plus exact three-node
  `MatMul -> Add -> Relu` session-smoke cases, with
  proof recorded in
  `runtime/bridge/onnxruntime-ep/artifacts/20260413T172955Z/doe-ort-ep-session-smoke.json`.
- The repo now also has a repo-only single-runtime native ORT EP bench surface
  for the current `Identity`, `Add`, `Relu`, rank-2 `MatMul`, and exact
  `MatMul -> Add` / `MatMul -> Add -> Relu` / `Add -> Relu` slice under
  `bench/workloads/workloads.native.ort-doe-ep-smoke.json`, with current local
  reports in `bench/out/native-ort-doe-ep/`.
- The repo now also has a repo-only strict native ORT compare and local-claim
  surface for the shared `Add`, `Relu`, rank-2 `MatMul`, exact
  `MatMul -> Add`, exact `MatMul -> Add -> Relu`, and exact `Add -> Relu`
  slice under
  `bench/native-compare/compare.config.native.ort-webgpu-provider.basic-ops.json`,
  with the current strict compare artifact at
  `bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.compare.json`
  and the current local claim artifact at
  `bench/out/native-ort-webgpu-provider/20260413T175708Z/basic-ops.claim.json`.
- D3D12 drop-in queue submit now retains submitted command lists behind the
  runtime fence and drains them at explicit completion boundaries instead of
  forcing a wait at every submit entry, and the native compute/render runtime
  paths now also retain deferred command lists behind explicit drain points
  instead of fence-waiting inside every hot submission. Deferred compute no
  longer forces a pre-dispatch flush just to protect the shared dispatch-info
  CBV path; upload/query drain work still remains for follow-up.
- Apple Metal submit-entry serialization is now fixed for the shared-event queue
  path: `doeNativeQueueSubmit` no longer blocks every submit unless deferred CPU
  copies/resolves are pending or the shared-event fallback is unavailable. The
  warm Node/Bun package lanes are now strict/comparable and claimable on
  `mac.lan`; broader Metal coverage still remains follow-up work. See
  `docs/status/2026-04.md` for the diagnosis and implementation notes.
- Benchmark reporting now treats `bench/out` as a portable JSON surface:
  compare/claim/run receipts plus cube/inventory/pipeline summary JSONs are
  commit-eligible, generated HTML is no longer the default path, and the single
  tracked local viewer is `bench/viewers/bench_out_viewer.html`.
- AMD Vulkan Gemma-270M package compute is now a claimable local compare
  surface on both Node and Bun package lanes, with current compare artifacts at
  `bench/out/amd-vulkan/20260410T235522Z/gemma270m.node-package.ir.compare.json`
  and
  `bench/out/amd-vulkan/20260410T235541Z/gemma270m.bun-package.ir.compare.json`.
- Current status terminology refers to the numeric stability surface as
  `numeric-stability-strategy.md`.
- Shader proof-backed robustness now covers additional 3D storage and texture
  coord families in the native Zig runtime path.
- Lean artifact regeneration and `-Dlean-verified=true` WGSL builds are green
  again after the comparability-contract drift and extractor build gaps were
  repaired.
- Apple `node-webgpu` package execution on `mac.lan` was restored after keeping
  the provider root alive through async completion.
- Benchmark/package compare cleanup in early April moved more of the compare
  stack onto artifact-first, config-backed paths.
- Cerebras-facing Gemma-4 lane is in outreach phase: the current local
  side-by-side evidence includes L1 synthetic layer-block parity, E2B L1
  BF16-derived real-weight smoke-contract parity, a structural
  Doppler RDRR/int4ple artifact-readability probe, RDRR-derived
  Q4_K_M L1 smoke-contract parity, declared-depth smoke diagnostics,
  and an E2B manifest-shape tensor-contract probe for the upstream local/global
  head-dim plus grouped-KV contract. The model receipt now
  reports `executionStatus=real_weight_layer_block_success` for that narrow
  L1 layer-block contract and includes `sdkLayoutModelExecutionEvidence` for
  the generated SdkLayout smoke promotion plus
  `sdkLayoutDepthDiagnosticEvidence` for non-claimable L35 BF16/RDRR smoke
  diagnostics. Promoted deeper receipts, full E2B, Doppler production
  inference parity, 31B manifest-shape and real-weight receipts, MoE, and
  hardware remain gated in the current April shard and in
  `docs/hardware-validation-appendix.md`.
  The E2B receipt also now binds a Doppler WebGPU capture graph as the
  shared JS/WGSL input surface, plus a first capture-to-CSL attention-core
  lowering receipt with CPU-oracle parity. That capture-lowering rung is
  still non-claimable for full Doppler production inference, full graph
  lowering, logits parity, hardware, or performance.

## Current follow-up highlights

- Proof-backed shader metric evidence is now front-doored at
  `bench/out/proof-metrics/latest/proof_metrics_summary.{json,md}`; the
  reporter entrypoint, build flavors, and refresh pattern are documented in
  `bench/README.md` under "Proof-backed shader metric front door". A fresh
  Vulkan-host timing pass is still the next refresh step.
- Status history is now sharded; future follow-ups should go into the current
  shard instead of bloating this front door.

## Archive shards

- [2026-04.md](/Users/xyz/deco/doe/docs/status/2026-04.md)
- [2026-03-30-to-2026-03-28.md](/Users/xyz/deco/doe/docs/status/2026-03-30-to-2026-03-28.md)
- [2026-03-27-to-2026-03-24.md](/Users/xyz/deco/doe/docs/status/2026-03-27-to-2026-03-24.md)
- [2026-03-23-to-2026-03-01.md](/Users/xyz/deco/doe/docs/status/2026-03-23-to-2026-03-01.md)
- [2026-02-and-legacy.md](/Users/xyz/deco/doe/docs/status/2026-02-and-legacy.md)

## Historical note

The shard split preserves original top-to-bottom ordering from the former
single-file log. The `2026-02-and-legacy` shard intentionally keeps some older
early-2026 backfilled sections in their original order rather than
reclassifying them retroactively.
