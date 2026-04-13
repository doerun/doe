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

- A repo-only same-stack Bun ORT WebGPU provider-compare lane now exists at
  `bench/native-compare/compare.config.bun.ort-webgpu-provider.gemma270m.prefill32.decode1.json`.
  The current local Bun host artifacts at
  `bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.compare.json`
  and `bench/out/bun-ort-webgpu-provider-compare/gemma270m-prefill32-decode1.claim.json`
  record a strict comparable local Doe-advantage claim against the `bun-webgpu`
  package surface on Gemma-3 270M `prefill 32 / decode 1`.
- A repo-only same-stack Node ORT WebGPU provider-compare lane now exists at
  `bench/native-compare/compare.config.node.ort-webgpu-provider.gemma270m.json`.
  The current AMD RADV host artifacts at
  `bench/out/node-ort-webgpu-provider-compare/20260413T011722Z/gemma270m.compare.json`
  and `bench/out/node-ort-webgpu-provider-compare/20260413T011722Z/gemma270m.claim.json`
  record a strict comparable local Doe-advantage claim against the hardware-pinned
  `node-webgpu` package surface.
- A repo-only same-stack browser ORT WebGPU Playwright surface now exists at
  `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`. The current local
  Chromium artifact at
  `browser/chromium/artifacts/20260413T023500Z/dawn-vs-doe.browser-ort-bench.diagnostic.json`
  records a Doe-faster result on the vendored DistilBERT sentiment workload on
  this Linux host.
- A broader four-shape repo-only Node ORT WebGPU package matrix now also exists
  at `bench/native-compare/compare.config.node.ort-webgpu-provider.breadth.json`.
  Its current AMD RADV host artifacts show mixed results across short,
  prefill-heavy, decode-heavy, and 1B shapes, so the broader matrix does not
  support a blanket Doe-over-Dawn ORT package claim today.
- The repo-only ONNX Runtime plugin EP now crosses the line from pure scaffold
  to a narrow non-trivial native slice: Doe claims, compiles, and executes
  same-shape float32 ONNX `Identity`, `Add`, `Relu`, rank-2 `MatMul`, and
  exact two-node `MatMul -> Add` / `Add -> Relu` session-smoke cases, with
  proof recorded in
  `runtime/bridge/onnxruntime-ep/artifacts/20260413T170900Z/doe-ort-ep-session-smoke.json`.
- The repo now also has a repo-only single-runtime native ORT EP bench surface
  for the current `Identity`, `Add`, `Relu`, rank-2 `MatMul`, and exact
  `MatMul -> Add` / `Add -> Relu` slice under
  `bench/workloads/workloads.native.ort-doe-ep-smoke.json`, with current local
  reports in `bench/out/native-ort-doe-ep/`.
- D3D12 drop-in queue submit now retains submitted command lists behind the
  runtime fence and drains them at explicit completion boundaries instead of
  forcing a wait at every submit entry, and the native compute/render runtime
  paths now also retain deferred command lists behind explicit drain points
  instead of fence-waiting inside every hot submission. Deferred compute no
  longer forces a pre-dispatch flush just to protect the shared dispatch-info
  CBV path; upload/query drain work still remains for follow-up.
- Apple Metal submit-entry serialization is now fixed for the shared-event queue
  path: `doeNativeQueueSubmit` no longer blocks every submit unless deferred CPU
  copies/resolves are pending or the shared-event fallback is unavailable. Fresh
  Metal package receipts are still pending, and the Bun package surface now also
  routes pure compute-dispatch batches through the native Metal batch flush path
  instead of JS command replay; see `2026-04.md` for the diagnosis and
  implementation note.
- Benchmark reporting now treats `bench/out` as a portable JSON surface:
  compare/claim/run receipts plus cube/inventory/pipeline summary JSONs are
  commit-eligible, generated HTML is no longer the default path, and the single
  tracked local viewer is `bench/viewers/bench_out_viewer.html`.
- AMD Vulkan Gemma-270M package compute is now a claimable local compare
  surface on both Node and Bun package lanes.
- Current status terminology now treats numeric stability as a `strategy`
  surface rather than a `moat` surface.
- Shader proof-backed robustness now covers additional 3D storage and texture
  coord families in the native Zig runtime path.
- Lean artifact regeneration and `-Dlean-verified=true` WGSL builds are green
  again after the comparability-contract drift and extractor build gaps were
  repaired.
- Apple `node-webgpu` package execution on `mac.lan` was restored after keeping
  the provider root alive through async completion.
- Benchmark/package compare cleanup in early April moved more of the compare
  stack onto artifact-first, config-backed paths.

## Current follow-up highlights

- Proof-backed shader metric collection currently lives in a scratch evidence
  bundle rather than a promoted benchmark lane; see the current April shard for
  the reporter entrypoint and artifact path.
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
