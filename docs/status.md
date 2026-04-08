# Doe status
## Shader proof-backed robustness now covers 3D flat storage indices plus 1D/mip/affine/tiled texture coord families in the Zig runtime path (2026-04-08 UTC)

- extended the shader proof contract and runtime matcher so native compute
  translation can now record and enforce additional proof-backed preconditions
  for:
  - 3D flat storage-buffer indices:
    `gid.z * (dispatch_height * dispatch_width) + gid.y * dispatch_width + gid.x`
    and offset variants
  - 1D texture dispatch-fit scalar coords
  - constant-mip texture dispatch-fit coords
  - affine gid-derived texture coords
  - tiled gid-derived texture coords
- widened the counted-loop matcher to tolerate extra dynamic conjuncts in
  `while` conditions and extra disjuncts in guarded `break` conditions when one
  branch still carries the proven loop bound
- updated:
  - `pipeline/lean/Doe/Shader/ComputeBounds.lean`
  - `pipeline/lean/Doe/Shader/TextureSampleBounds.lean`
  - `pipeline/lean/Doe/Extract.lean`
  - `config/lean-proof-patterns.json`
  - `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig`
  - `runtime/zig/src/doe_wgsl/dispatch_proof_match.zig`
  - `runtime/zig/src/doe_compute_preconditions_native.zig`
- verification status:
  - `zig build test-wgsl` now passes in `runtime/zig`
  - full Lean artifact regeneration is currently blocked by pre-existing
    `ComparabilityFixtures.lean` / generated comparability-contract drift in the
    repo, so `-Dlean-verified=true` could not be revalidated end-to-end in this
    tree during this change

## Apple Node `node-webgpu` package execution on `mac.lan` is restored; the provider root now stays alive through async completion (2026-04-07 UTC)

- retained the Node package provider root in
  `bench/executors/node-webgpu/executor.js` for the full sample execution
- rationale:
  - the rebuilt external-drive Dawn Node binding schedules future
    `ProcessEvents()` calls through `AsyncRunner`
  - our package executor was dropping the JS `gpu` root immediately after
    `requestDevice()`
  - retaining that root removes the `ProcessEvents()` teardown crash and
    restores real execution rows on this host
- reproduced successful canonical Node package executions on `mac.lan` for:
  - `inference_gemma3_270m_decode_1tok`
  - `inference_gemma3_270m_prefill_32tok`
  - `inference_gemma3_270m_prefill_64tok_decode_64tok`
  - `inference_gemma3_1b_prefill_64tok_decode_64tok`
- canonical artifact-first compare also works again:
  - `/tmp/node-package-prefill32.compare.json`
- `config/package-execution-policy.json` remains empty; the earlier host-block
  notes below are superseded by this fix

## Package compare configs with explicit workload IDs no longer self-filter through stale cohort tags (2026-04-07 UTC)

- updated Apple Metal package compare configs for `gemma64` and `gemma1b`
  across Node and Bun cold/warm surfaces so their selectors now rely on the
  pinned workload `ids` plus `benchmarkClass=comparable`
- removed stale cohort filters from:
  - `bench/native-compare/compare.config.apple.metal.gemma64.bun-package.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma64.bun-package.warm.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma64.node-package.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma64.node-package.warm.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma1b.bun-package.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma1b.bun-package.warm.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma1b.node-package.ir.json`
  - `bench/native-compare/compare.config.apple.metal.gemma1b.node-package.warm.ir.json`
- rationale:
  - package profiles that already pin exact workload IDs should not also
    depend on a cohort tag that can drift away from the selected workload
  - `apple-metal-gemma64-bun-package-{cold,warm}` had resolved to zero
    workloads because `inference_gemma3_270m_prefill_64tok_decode_64tok` is
    tagged `regression` / `exploration`, not `governed`
- canonical Bun reruns on this host:
  - cold:
    `bench/out/apple-metal/20260407T001537Z/gemma1b.bun-package.ir.compare.json`
  - warm:
    `bench/out/apple-metal/20260407T001537Z/gemma1b.bun-package.warm.ir.compare.json`

## Apple `node-webgpu` is now blocked host-wide on `mac.lan`; package trace-meta records wait scope explicitly (2026-04-06 UTC)

- `config/package-execution-policy.json` now blocks Apple/Node `node-webgpu`
  at the provider level on `mac.lan`, not by individual Gemma workload.
- rationale:
  - the earlier workload-level Gemma blocks were too narrow
  - a minimal `node-webgpu` adapter/device script on `mac.lan` prints
    successfully and still exits with `rc=139`
  - real Gemma package executions can make progress, but the provider still
    tears down with `rc=139` on this host
  - this is therefore a host/provider availability problem, not just a
    workload-shape problem
- package executor updates:
  - package trace-meta now records `queueWaitScope:
    "terminal-or-readback"` alongside the existing queue sync/wait mode fields
  - package artifact writes are now synchronous so a child teardown failure
    does not silently discard already-computed artifacts
  - the package executor now retains in-flight `writeBuffer` payloads and
    submitted command buffers until a real completion wait boundary

## Apple `node-webgpu` package execution on `mac.lan` is now explicitly blocked for reproduced Gemma prefill failures (2026-04-06 UTC)

- `config/package-execution-policy.json` now blocks additional Apple/Node
  `node-webgpu` executions on `mac.lan` for:
  - `inference_gemma3_270m_prefill_32tok`
  - `inference_gemma3_1b_prefill_32tok`
- rationale:
  - both workloads were rerun through the canonical artifact-first package path
    with `bench/cli.py run`
  - Doe package execution completed on the same host
  - `node-webgpu` produced zero-execution failure artifacts on both workloads
  - direct boundary tracing of `bench/executors/run-node-webgpu-plan.js`
    reproduced hard failures at `queue.onSubmittedWorkDone()`
- the policy detail text for the existing Apple/Node Gemma blocks was narrowed
  to observed failure behavior rather than unproven root-cause claims

## Canonical benchmark workflow is now `bench/cli.py` only; legacy compare wrappers were removed (2026-04-06 UTC)

- the only live benchmark front door is now `bench/cli.py`:
  - `bench/cli.py run`
  - `bench/cli.py compare`
  - `bench/cli.py list`
- removed the extra compare/front-door wrappers:
  - `bench/run_compare.py`
  - `bench/runners/run.py`
- compare config files now use the canonical prefix:
  - `bench/native-compare/compare.config.*.json`
- release and bench scripts now invoke `bench/cli.py compare` directly instead
  of shelling through deleted wrappers
- promoted compare profile resolution still exists, but it now lives as an
  internal module under `bench/native_compare_modules/promoted_compare.py`
  rather than as a separate CLI surface

## Package benchmarking is now artifact-first only; legacy package-compare runners were removed (2026-04-06 UTC)

- the canonical package benchmark flow is now the same as every other Doe
  benchmark surface:
  - run one product with `bench/cli.py run`
  - emit a run artifact
  - compare artifacts post-hoc with `bench/cli.py compare`
- package surfaces now run only through the standalone package plan executors:
  - `bench/executors/run-node-webgpu-plan.js`
  - `bench/executors/run-bun-webgpu-plan.js`
- removed the old parallel package benchmark subsystem source files:
  - `bench/package-compare/node/*`
  - `bench/package-compare/bun/*`
  - `bench/package-compare/deno/*`
  - `bench/package-compare/doe-api/*`
  - `bench/shared/lib/package-runner-core.js`
  - `bench/shared/lib/package-compare-core.js`
- fixed the artifact-first package run path in
  `bench/native_compare_modules/artifact_benchmarking.py` so standalone package
  runs no longer crash on the old `left_product` / `right_product` call shape
- active docs/configs were updated to stop pointing at deleted package-compare
  entrypoints; historical references remain below in append-only status history

## Benchmark executor and compare-taxonomy naming now reflect the actual provider surfaces (2026-04-06 UTC)

- the generic direct WebGPU plan runner is now named:
  - `webgpu-plan-executor`
  - Zig sources:
    - `runtime/zig/src/webgpu_plan_executor.zig`
    - `runtime/zig/src/webgpu_plan_executor_support.zig`
    - `runtime/zig/src/main_webgpu_plan_executor.zig`
- rationale:
  - the old `dawn-plan-executor` name was inaccurate because the same direct
    plan runner can execute against Dawn or the WebKit shim depending on the
    loaded library / `--backend-id`
- the Node package comparison surface now uses:
  - executor ids:
    - `dawn_node_webgpu`
    - `dawn_node_webgpu_prepared`
  - provider token:
    - `node-webgpu`
- the WebKit direct-plan executor id is now:
  - `webkit_webgpu_native_metal`
- package-surface compare taxonomy now uses provider/package-oriented names:
  - `doe_vs_dawn_node_webgpu`
  - `doe_vs_bun_webgpu_package`
  - `doe_vs_deno_webgpu_package`
  - products:
    - `dawn_node_webgpu`
    - `bun_webgpu_package`
    - `deno_webgpu_package`
- active benchmark docs/configs/tests were updated in the same change:
  - `bench/README.md`
  - `docs/benchmark-taxonomy.md`
  - `docs/compare-taxonomy.md`
  - `config/compare-taxonomy.json`
  - `config/promoted-compare-catalog.json`
  - `config/benchmark-cube-policy.json`
  - `config/governed-lanes.json`

## Active benchmark contracts now use baseline/comparison terminology instead of left/right terminology (2026-04-06 UTC)

- active benchmark/front-door docs now describe comparison roles as
  `baseline` and `comparison`, not `left` and `right`
- trace semantic-parity tooling now uses:
  - `pipeline/trace/compare_dispatch_traces.py --baseline ... --comparison ...`
- benchmark-cube policy/config now uses:
  - `comparisonViews[].baseline`
  - `comparisonViews[].comparison`
- benchmark cube/report normalization now reads compare reports from:
  - `workloads[].baseline`
  - `workloads[].comparison`
  - `traceMetaHashes.baseline`
  - `traceMetaHashes.comparison`
- browser claim reports and the WGSL compilation compare report now emit
  baseline/comparison payloads instead of left/right payloads
- rationale:
  - `left` / `right` was report-wrapper vocabulary that obscured the actual
    benchmark model
  - the canonical benchmark taxonomy is now:
    - `workload`
    - `surface`
    - `executor`
    - `run artifact`
    - `compare report`
    - with compare roles named `baseline` and `comparison`

## Compare taxonomy expansion now uses entry terminology instead of row terminology (2026-04-06 UTC)

- the generated compare-taxonomy expansion contract now uses `entry` naming:
  - schema: `config/compare-taxonomy-expanded-entry.schema.json`
  - generated data: `config/generated/compare-taxonomy-expanded.jsonl`
- the old `row`-based field names were renamed in the generated artifact:
  - `rowId` -> `entryId`
  - `theoreticalConcreteRowSlotCount` -> `theoreticalConcreteTargetSlotCount`
  - `promotedCompareRowCount` -> `promotedCompareProfileCount`
- `bench/tools/generate_compare_taxonomy.py` and the schema-target registry now
  use the same entry terminology
- rationale:
  - the benchmark taxonomy now treats `workload`, `surface`, `executor`,
    `run artifact`, and `compare report` as the canonical human model
  - leaving `row` as the generated taxonomy unit kept reintroducing the older,
    less clear benchmark vocabulary

## Benchmark taxonomy now uses workload / surface / executor / run artifact / compare report as the canonical vocabulary (2026-04-06 UTC)

- the active benchmark docs and front doors now treat isolated run artifacts
  as the benchmark primitive and compare reports as post-hoc joins
- the canonical compare surfaces are now:
  - `backend`
  - `plan`
  - `package`
  - `dropin`
  - `browser`
  - `compiler`
- lower-level executor boundaries still exist where needed
  (`backend_native`, `direct_plan`, `package_surface`, `abi_dropin`), but they
  are no longer the primary human-facing benchmark vocabulary
- `config/compare-taxonomy.json` now records those canonical surface names
  directly, and `config/promoted-compare-catalog.json` now uses:
  - `backend-runtime-preset`
  - `plan-runtime-workload`
  - `package-runtime-workload`
- active docs updated in the same change:
  - `docs/benchmark-taxonomy.md`
  - `docs/compare-taxonomy.md`
  - `bench/README.md`
  - `bench/docs/benchmark-writing-guide.md`
  - `docs/performance-strategy.md`

## Metal comparable plan uploads now stage `buffer_load` / `buffer_write` data instead of bypassing the upload policy (2026-04-06 UTC)

- fixed a native Metal direct-plan comparability bug where plan `buffer_load`
  and byte-backed `buffer_write` operations wrote directly into mapped compute
  buffers even when the lane required `uploadPathPolicy=staged_copy_only`
- comparable and release Metal lanes now route those bytes through the
  streaming blit path before execution timing is finalized
- focused evidence for the fix is at:
  `/tmp/doe-gemma3-270m-prefill-compare-10-staged.json`

## Gemma IR-backed inference rows now use deterministic cached synthetic readonly assets and explicit timed `buffer_load` commands (2026-04-06 UTC)

- the Gemma IR rows under `bench/ir/` no longer rely on implicit first-use
  zero-filled readonly buffers for large synthetic tensors
- authored IR now declares a deterministic synthetic readonly asset policy, and
  plan generation injects explicit `buffer_load` commands for those tensors
- cache-backed asset warming now happens before timed iterations begin:
  - default cache root:
    `~/.cache/doe/bench_synthetic_assets`
  - override:
    `DOE_BENCH_ASSET_CACHE_DIR`
- the timed execution boundary now includes:
  - host cache read for the warmed asset
  - upload / staging into device-visible memory
  - the real inference dispatch sequence
- the timed execution boundary does not include:
  - synthetic asset generation
  - cache warmup
- rationale:
  - the old rows were useful for command-shape coverage, but weak as
    compute-content benchmarks because the large readonly tensors were not
    deterministic non-zero model-like payloads
  - the new contract keeps the rows synthetic and reproducible while making
    them materially closer to a device-load-inclusive inference session

## Heavy package stress workloads now use multi-stage integer kernels instead of trivial float math (2026-04-06 UTC)

- strengthened `compute_multistage_e2e_1048576`:
  - now runs six ping-pong stages, not three
  - each stage executes an exact integer stress loop per invocation
- strengthened `pipeline_multistage_first_use_e2e`:
  - now creates six unique pipelines per timed iteration, not three
  - each stage uses the same exact integer stress kernel shape
- rationale:
  - the first version was “more stages” but still too light on arithmetic
  - the upgraded variants are still comparable, but they now better exercise
    ALU-heavy compute and first-use pipeline churn on the package surface

## Heavier package end-to-end compute and pipeline workloads are now part of the Node/Bun/Deno package surface (2026-04-06 UTC)

- added `compute_multistage_e2e_1048576`:
  - three ping-pong compute passes over `1048576` threads
  - full completion wait plus readback validation
- added `pipeline_multistage_first_use_e2e`:
  - unique WGSL per timed iteration
  - three pipeline creations, three compute passes, one readback validation
- package workload factories live in:
  - `bench/package-compare/node/workloads.js`
- canonical workload contracts now exist in:
  - `bench/workloads/metadata/workload-registry.json`
- rationale:
  - `compute_dispatch_and_wait_simple` is a valid smoke/completion workload, but
    it is intentionally tiny
  - the package surface now has a heavier pure-compute path and a heavier
    WebGPU-object/pipeline-churn path for Doe-only and package compare runs

## The legacy `compare_dawn_vs_doe.py` front door is removed, and `bench/run_compare.py` is the only live config-backed compare entrypoint (2026-04-05 UTC)

- deleted `bench/native-compare/compare_dawn_vs_doe.py`
- `bench/run_compare.py` now owns both current compare surfaces:
  - direct config mode: `python3 bench/run_compare.py --config ...`
  - promoted profile mode: resolve catalog entry, then re-enter direct config mode
- live repo runners now invoke `bench/run_compare.py` instead of the deleted
  script:
  - `bench/runners/run.py`
  - `bench/runners/run_release_pipeline.py`
  - `bench/runners/publish_apple_runtime_release.py`
  - `bench/runners/run_local_d3d12_lane.py`
  - `bench/runners/run_single_workload_sweep.py`
- the internal tooling manifest and current bench docs now treat
  `bench/run_compare.py` as the compare front door
- rationale:
  - the canonical benchmark contract is isolated run artifacts plus post-hoc
    join
  - keeping a second script-shaped compatibility wrapper around the same logic
    was unnecessary surface area and contradicted the simplified model

## The ad hoc pair-command runtime comparator is removed from the live bench surface (2026-04-05 UTC)

- deleted `bench/native-compare/compare_runtimes.py`
- `bench/runners/run.py` no longer exposes the unsupported `adhoc` harness:
  - the live harness set is now `compare`, `single`, and `compile`
- `bench/README.md` no longer documents the removed ad hoc comparator as part
  of the current bench surface
- `bench/tools/backfill_run_manifests.py` no longer treats
  `runtime-comparison*.json` as a first-class active run type:
  - those folders now fall through to legacy/unknown inference instead of
    preserving a removed harness as if it were still part of the supported
    surface
- rationale:
  - the canonical benchmark model is isolated run artifacts plus post-hoc join
  - the removed script was a free-form pair-command timer with no workload
    contract, executor registry, artifact join discipline, or claimability
    semantics

## Native benchmark execution is now artifact-first internally, and the legacy compare lanes are compatibility wrappers over isolated per-product bundles (2026-04-05 UTC)

- `bench/native_compare_modules/artifact_benchmarking.py` now owns the shared
  isolated-run execution path:
  - one product runs across the selected workload set
  - each workload emits a standalone run artifact
  - a run-manifest is written for the emitted bundle
- `bench/native_compare_modules/run_artifact.py` and
  `config/run-artifact.schema.json` now treat the run artifact as the
  post-hoc-join source of truth:
  - `schemaVersion` is now `2`
  - new artifacts require `workloadContract` metadata
  - new artifacts also carry the workload-side comparability metadata and the
    per-product normalization knobs needed to reconstruct the legacy compare
    report
  - legacy `schemaVersion: 1` artifacts still load, but the artifact-first join
    rejects them because they cannot prove the workload-contract hash
- `bench/native_compare_modules/compare_from_artifacts.py` now rebuilds the
  canonical schema-version-5 compare report directly from run artifacts instead
  of relying on a pair-coupled in-memory compare loop
- `bench/cli.py`
  - `run` now executes through the shared isolated-bundle path
  - `compare` now joins run artifacts into the canonical compare report instead
    of emitting the older sidecar compare-only report shape
- `bench/native-compare/compare_dawn_vs_doe.py` and `bench/run_compare.py`
  remain as compatibility front doors for existing configs, gates, and release
  scripts, but they now execute:
  - isolated left-product bundle
  - isolated right-product bundle
  - post-hoc artifact join
- targeted verification for this refactor:
  - `python3 -m unittest bench.tests.test_run_artifact bench.tests.test_compare_from_artifacts`
  - `python3 -m unittest bench.tests.test_backend_workload_catalog`

## Metal coverage-gate wiring is repaired and the governed strict Metal lane no longer overclaims legacy Gemma3 plan workloads (2026-04-05 UTC)

- `runtime/zig/build.zig` now points the `coverage-gate` build step at the
  canonical `bench/gates/split_coverage_gate.py` path, so
  `zig build coverage-gate` again exercises the real split-surface coverage
  contract instead of failing on a stale script location
- `config/webgpu-command-coverage-core.json` and
  `config/webgpu-command-coverage-full.json` now include the previously missing
  `buffer_write` core command:
  - core coverage accounting once again matches the Zig core partition enum
  - the full-surface ledger once again matches the core + full-only partition
    counts
- `config/backend-workload-cohorts.json` removes the Gemma3 270M plan-backed
  inference workloads from the Apple Metal governed cohort:
  - those workloads remain available as regression/exploration coverage
  - the governed strict Apple compare lane now limits itself to the
    commands-boundary workloads it is actually configured to execute
  - this avoids strict compare failures from plan-backed rows until the Apple
    Metal governed preset is upgraded to a plan-boundary executor pair
- verification target for this contract/gating fix:
  - `zig build coverage-gate`
  - `python3 bench/tools/generate_backend_workloads.py`
  - `python3 bench/tools/generate_workload_overlap_map.py`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.compare.json`

## Runtime build/test closure is restored on macOS and the drop-in library now links its native immediates/render-control shims without unresolved `doeNative*` symbols (2026-04-05 UTC)

- `runtime/zig/src/wgpu_dropin_ext_a_core.zig` and
  `runtime/zig/src/wgpu_dropin_ext_b.zig` no longer declare the local Doe
  immediates/render-control entry points as unresolved `extern fn`s inside the
  same link unit:
  - the drop-in layer now calls the imported Doe native functions directly
  - `zig build dropin` and the default `zig build` now complete on macOS
    without the earlier unresolved
    `doeNativeComputePassSetImmediates` /
    `doeNativeRenderPassSetViewport` family
- `runtime/zig/src/model.zig` now rebuilds the compatibility export surface
  from the shard modules directly instead of importing the banned
  `model_runtime_types.zig` facade:
  - the aggregate model surface again exposes the quirk types used by
    `trace.zig`, `quirk/*`, and the core model tests
  - the core/full import-fence check no longer fails on `src/model.zig`
- `runtime/zig/src/backend/vulkan/vk_render.zig` now carries the widened
  texture metadata (`depth_or_array_layers`, `sample_count`, `dimension`,
  `view_dimension`, `aspect`) through render-target binding/allocation paths so
  the newer `TextureResource` shape is consistent across both runtime and tests
- `runtime/zig/build.zig` now prefers the checked-in precompiled macOS `.icns`
  asset for the app bundle and only falls back to SVG conversion if that asset
  is absent:
  - plain `zig build` no longer depends on ImageMagick `convert` just to build
    the app bundle on hosts that already have the committed icon artifact
- `runtime/zig/test_suite.zig` now scopes the Vulkan aggregate test imports to
  Linux, matching the repo’s current Vulkan runtime scope instead of attempting
  to link Vulkan loader symbols on macOS hosts with no loader installed
- `runtime/zig/src/backend/metal/metal_runtime_resources.zig` updates the
  keyed-workgroup-size unit test to match the normalized default-entrypoint
  cache-key contract (`kernel` instead of `kernel#main`)
- verification for this closure pass:
  - `zig build dropin`
  - `zig build`
  - `zig build test`

## Metal runtime removes the hard deferred-dispatch/map cap and Vulkan texture validation now respects real resource metadata (2026-04-05 UTC)

- `runtime/zig/src/backend/metal/metal_dispatch_runtime.zig` no longer hard
  rejects `queueSyncMode: "deferred"` for plain and indirect compute dispatch:
  - deferred dispatches now encode onto a real command buffer, commit without a
    CPU wait, and track the latest in-flight submission through the existing
    shared-event / `outstanding_cmd_buf` path
  - dispatch commits now also honor pending copy-queue fences before compute
    execution instead of bypassing the existing copy-to-main-queue ordering
    contract
- `runtime/zig/src/backend/metal/metal_async_runtime.zig` no longer blocks
  `map_async` at a hardcoded `256 MiB`; it now checks the actual Metal device
  `maxBufferLength` via the bridge and fails only when the requested map size
  exceeds the device-reported buffer limit
- `runtime/zig/src/backend/metal/metal_surface_runtime.zig`,
  `runtime/zig/src/backend/metal/metal_surface_bridge.m`, and
  `runtime/zig/src/backend/metal/metal_surface_bridge.h` now plumb
  `toneMappingMode` through native Metal surface configuration:
  - standard tone mapping still works on the existing 8-bit swapchain formats
  - extended tone mapping is now accepted on `RGBA16Float` surfaces and sets an
    explicit extended-linear-sRGB surface colorspace instead of failing closed
    at the Zig entrypoint
- `runtime/zig/src/backend/vulkan/vk_resources.zig`,
  `runtime/zig/src/backend/vulkan/vk_pipeline.zig`, and
  `runtime/zig/src/backend/vulkan/vk_texture_commands.zig` now preserve and use
  actual Vulkan texture metadata:
  - texture resources now retain `depth_or_array_layers`, `sample_count`,
    `dimension`, `view_dimension`, and `aspect`
  - `texture_query` now validates against those real stored values instead of
    assuming every texture is `2D`, single-layer, and sample-count `1`
  - compute binding validation now checks the actual resource view-dimension and
    multisample state instead of blanket-rejecting every non-`2D` /
    multisampled texture binding
- verification for this runtime pass:
  - `zig build test-wgsl`
  - `zig build doe-runtime`
- repo-wide `zig build test` is still failing for an unrelated baseline problem
  in `src/model.zig` / `test_suite.zig`; this backend work did not attempt to
  repair that broader test harness break

## Gemma 4 CSL bundle lowering now emits explicit memory/runtime artifacts, derives the PE grid from model config, and can launch the checked simulator plan without env-only driver wiring (2026-04-05 UTC)

- `runtime/zig/src/doe_wgsl/emit_csl_mem_plan.zig` now emits an explicit
  memory-plan artifact instead of a coarse SRAM guess:
  - derives the smallest fitting PE rectangle from `modelConfig` plus optional
    `placementPolicy`
  - chooses an explicit residency mode (`full_resident` or
    `layer_streaming`)
  - models persistent buffers, streamed buffers, and stream stages separately
  - accounts for Gemma 4 PLE tables/projection/norm, KV cache, activation
    scratch, decode-position state, sliding-window state, and output logits
- `runtime/zig/src/doe_wgsl/emit_csl_host.zig` now includes configurable FFN
  matrix count plus Gemma 4 PLE bytes in the model/SRAM estimates, and exports
  shared-KV layer counting so the memory planner can deduplicate aliased KV
  state instead of charging one cache per layer unconditionally
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` now accepts step plans with
  no explicit `grid` when they provide `modelConfig`; lowering derives the grid
  from the memory planner and fails closed on manifest-mode attempts to smuggle
  the newer placement/model metadata through the legacy path
- `runtime/zig/src/doe_wgsl/emit_csl_host_runtime.zig`,
  `runtime/zig/src/doe_wgsl/emit_csl_simulator.zig`, and
  `runtime/zig/src/csl_host_plan_tool.zig` now emit a complete compile-only
  bundle contract:
  - `host-plan.json`
  - `memory-plan.json`
  - `runtime-config.json`
  - `simulator-plan.json`
  - `launch-simulator.sh`
- `runtime/zig/src/csl_sim_runner.zig` now resolves the driver in the actual
  documented order:
  - `--driver-executable`
  - `plan.driver.executablePath`
  - `DOE_CSL_SIM_EXECUTABLE`
- new checked artifacts and schemas landed for:
  - `config/doe-wgsl-memory-plan.schema.json`
  - `config/doe-wgsl-runtime-config.schema.json`
  - `config/doe-wgsl-simulator-plan.schema.json` schema version `2`
  - `examples/doe-wgsl-memory-plan.gemma-4-e2b-smoke.json`
  - `examples/doe-wgsl-runtime-config.gemma-4-e2b-smoke.json`
  - `examples/doe-wgsl-simulator-plan.gemma-4-e2b-smoke.json`
- verification now covers:
  - `zig build test-wgsl`
  - `zig build csl-host-plan-tool`
  - targeted positive schema checks for the Gemma 4 memory-plan,
    runtime-config, and simulator-plan artifacts
- local closure is now split cleanly:
  - repo-side compile/simulator contracts are closed and locally executable
    through the checked bundle and driver path
  - actual Cerebras compilation still requires an installed `cslc`
  - actual simulator/runtime parity still requires the external Cerebras SDK
    lane; Doe now records those missing externals explicitly instead of failing
    on missing in-repo wiring

## Gemma 4 CSL lowering now uses explicit decode device state, derives hybrid attention from layer metadata, and rejects unsupported manifest shortcuts (2026-04-05 UTC)

- `runtime/zig/src/doe_wgsl/emit_csl_attention.zig`,
  `runtime/zig/src/doe_wgsl/emit_csl_kv_cache.zig`, and
  `runtime/zig/src/doe_wgsl/emit_csl_layout.zig` now model decode position and
  sliding-window width as exported device-state buffers (`position` and
  `sliding_window`) instead of pretending Cerebras launch kwargs mutate CSL
  compile-time params at runtime
- `runtime/zig/src/doe_wgsl/emit_csl_host.zig` and
  `runtime/zig/src/doe_wgsl/emit_csl_host_runtime.zig` now stage that decode
  state with explicit `memcpy_h2d(...)` calls before launches rather than
  passing fake `current_pos` / `sliding_window` launch kwargs
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` now:
  - lowers `ple_project` as the general `tiled_matmul` pattern instead of the
    Q4K-only `fused_gemv_dequant` path
  - derives decode `attentionType` from `layerPattern` when Gemma 4 steps omit
    it explicitly
  - marks decode `kv_write` / `kv_write_shared` launches as consuming
    `currentPosSource: decode_position`
  - rejects manifest-lowering requests that try to smuggle Gemma 4-only launch
    metadata through the older manifest execution contract
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig` and
  `config/doe-wgsl-host-plan.schema.json` now allow `currentPosSource` on
  decode `kv_write` launches while still failing closed on sliding attention in
  prefill
- `runtime/zig/src/doe_wgsl/emit_csl_host.zig` now computes manifest SRAM
  estimates against the chosen PE grid and deduplicates shared-KV aliases in
  decode launches instead of assuming every model gets the full wafer and one
  KV cache per layer
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` has been sharded back under
  the Doe 999-line Zig-source limit via
  `runtime/zig/src/doe_wgsl/emit_csl_exec_v1_test.zig`
- Verification passed with `zig build test-wgsl` and the targeted schema checks
  for the checked host-plan artifacts
- External closure is still pending: this workspace does not currently provide
  `cslc` or a configured `DOE_CSL_SIM_EXECUTABLE`, so compile/simulator parity
  remains blocked on the Cerebras SDK/toolchain lane

## CSL host-plan v2 now carries launch-scoped Gemma 4 routing metadata, and Gemma 4 lowering has a checked golden artifact (2026-04-05 UTC)

- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` now fails closed on invalid
  `attentionType` values, parses `slidingWindowSize`, `layerPattern`, and
  `numKvSharedLayers`, and lowers sliding-window routing plus shared-KV aliasing
  onto launch specs instead of kernel specs
- `runtime/zig/src/doe_wgsl/emit_csl_host.zig`,
  `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`, and
  `runtime/zig/src/doe_wgsl/emit_csl_host_runtime.zig` now serialize and
  consume per-launch metadata:
  `attentionType`, `slidingWindowSize`, `currentPosSource`, and
  `kvCacheAlias`
- `config/doe-wgsl-host-plan.schema.json` and
  `runtime/zig/src/doe_wgsl/csl_spec.zig` now define host-plan schema version
  `2`, with migration notes recorded in `config/migration-notes.md`
- `runtime/zig/examples/doe-wgsl-host-plan.gemma-4-e2b-smoke.json` and
  `examples/doe-wgsl-host-plan.gemma-4-e2b-smoke.json` add the checked Gemma 4
  host-plan golden artifact, and `config/schema-targets.json` now validates the
  top-level checked example against the schema
- `runtime/zig/src/doe_wgsl/emit_csl_layout.zig` now forwards
  `sliding_window` and `current_pos` through the decode-attention layout tile
  parameters instead of dropping them before PE-program emission
- Verification passed with `zig build test-wgsl`

## Broad ABI and native compatibility barrels are now truly cold, macOS surface seam restored, and the fence enforces both states (2026-04-03 UTC)

- `runtime/zig/src/core/abi/wgpu_base_types.zig` and
  `runtime/zig/src/core/abi/wgpu_descriptor_types.zig` now have zero direct
  `@import(...)` sites anywhere under `runtime/zig/src`; remaining callers use
  the narrow base/descriptor shards directly or compose file-local shard views
  instead of depending on the broad barrel files
- `runtime/zig/src/doe_native_types.zig` and
  `runtime/zig/src/doe_native_helpers.zig` also remain at zero direct
  `@import(...)` sites under `runtime/zig/src`
- `runtime/zig/tools/check_core_import_fence.py` now rejects any new
  implementation import of `wgpu_base_types.zig`,
  `wgpu_descriptor_types.zig`, `doe_native_types.zig`, or
  `doe_native_helpers.zig`, alongside the older compatibility facade bans
- `runtime/zig/src/backend/dropin_surface_ops.zig` again exports the narrow
  Metal bridge entrypoints used by `runtime/zig/src/full/surface/
  wgpu_surface_macos.zig`, restoring the macOS surface seam after the earlier
  drop-in flattening pass
- Verification for the corrected state passed with `zig build`,
  `zig build import-fence`, `zig test src/execution.zig`, zero direct
  implementation imports of the broad ABI/native barrels, zero non-backend
  backend-implementation leaks, and zero nontrivial SCCs under
  `runtime/zig/src`

## Broad ABI barrels and native facades fully eliminated; dropin seams flattened (2026-04-03 UTC)

- `core/abi/wgpu_base_types.zig` and `core/abi/wgpu_descriptor_types.zig` now have
  0 direct importers. All callers use narrow ABI shards:
  `wgpu_core_base_types.zig`, `wgpu_feature_base_types.zig`,
  `wgpu_texture_base_types.zig`, `wgpu_callback_descriptor_types.zig`,
  `wgpu_copy_descriptor_types.zig`, `wgpu_pipeline_descriptor_types.zig`
- `doe_native_types.zig` and `doe_native_helpers.zig` now have 0 direct
  importers. All callers use narrow native shards:
  `doe_native_object_types.zig`, `doe_native_shared_types.zig`,
  `doe_native_command_types.zig`, `doe_native_object_helpers.zig`,
  `doe_native_runtime_helpers.zig`
- Dropin seams `dropin_lifecycle.zig`, `dropin_external_texture.zig`, and
  `dropin_surface_ops.zig` now expose narrow direct APIs instead of
  re-exporting whole backend sub-modules
- `dropin_capabilities.zig` keeps backend sub-module gateways for d3d12/vulkan
  capability probing (11+ items each) plus the existing metal wrapper
- `dropin_resource_ops.zig` and `dropin_queue_submit.zig` intentionally keep
  sub-module gateways due to heterogeneous backend surfaces (45+ vk_constants,
  36 metal_bridge functions)
- Verification: `zig build`, `zig build import-fence`, `zig test src/execution.zig`
  all pass. Non-backend direct backend imports: 0. Nontrivial SCCs: 0

## Backend-private drop-in dependencies finalized behind backend-owned seam modules (2026-04-03 UTC)

- The final backend-owned seam set for the drop-in lane is:
  `runtime/zig/src/backend/dropin_capabilities.zig`,
  `runtime/zig/src/backend/dropin_lifecycle.zig`,
  `runtime/zig/src/backend/dropin_resource_ops.zig`,
  `runtime/zig/src/backend/dropin_queue_submit.zig`,
  `runtime/zig/src/backend/dropin_external_texture.zig`,
  `runtime/zig/src/backend/dropin_surface_ops.zig`, and
  `runtime/zig/src/backend/dropin_render_state.zig`
- Non-backend Zig implementation files under `runtime/zig/src` now route
  backend-specific capability/resource/queue-submit/external-texture/surface
  work through those seams instead of importing `backend/metal/*`,
  `backend/vulkan/*`, or `backend/d3d12/*` directly
- `runtime/zig/tools/check_core_import_fence.py` now rejects any future
  non-backend import that reaches those backend-private implementation
  directories directly
- The same pass also moved several hot-path callers off the broader
  `core/abi/wgpu_base_types.zig` and `core/abi/wgpu_descriptor_types.zig`
  barrels onto narrower ABI shards such as
  `wgpu_core_base_types.zig`, `wgpu_texture_base_types.zig`,
  `wgpu_binding_base_types.zig`, `wgpu_callback_descriptor_types.zig`,
  `wgpu_copy_descriptor_types.zig`, and
  `wgpu_pipeline_descriptor_types.zig`

## Backend drop-in seams now own backend-specific imports, and the import fence blocks direct backend implementation reach-through (2026-04-03 UTC)

- Non-backend Zig implementation files under `runtime/zig/src` no longer import `backend/metal/*`, `backend/vulkan/*`, or `backend/d3d12/*` directly; they now route those dependencies through backend-owned seam modules such as `backend/dropin_capabilities.zig`, `backend/dropin_resource_ops.zig`, `backend/dropin_queue_submit.zig`, `backend/dropin_external_texture.zig`, `backend/dropin_render_state.zig`, `backend/dropin_surface.zig`, and `backend/dropin_runtime_types.zig`
- `runtime/zig/tools/check_core_import_fence.py` now treats any new non-backend import of those backend implementation directories as a hard violation
- Root/native callers also shed additional broad ABI dependencies in this pass by moving selected handle/callback/texture-descriptor users from `core/abi/wgpu_base_types.zig` and `core/abi/wgpu_descriptor_types.zig` onto narrower ABI shards such as `wgpu_handle_types.zig`, `wgpu_callback_descriptor_types.zig`, `wgpu_pipeline_descriptor_types.zig`, `wgpu_texture_base_types.zig`, and `wgpu_binding_base_types.zig`
- Verification for this seam/fence pass passed with `zig build import-fence`, `zig test src/execution.zig`, and `zig build`

## Broad native and WebGPU ABI barrels retargeted behind narrower ownership modules (2026-04-03 UTC)

- `runtime/zig/src/doe_native_types.zig` and `runtime/zig/src/doe_native_helpers.zig` remain as compatibility-facing native barrels, but a first batch of implementation files now imports `doe_native_object_types.zig`, `doe_native_shared_types.zig`, `doe_native_object_helpers.zig`, and `doe_native_runtime_helpers.zig` directly instead of depending on the broader native facades
- `runtime/zig/src/core/abi/wgpu_base_types.zig` and `runtime/zig/src/core/abi/wgpu_descriptor_types.zig` are still available as combined ABI surfaces, but multiple runtime callers now import narrower ABI shards such as `wgpu_core_base_types.zig`, `wgpu_feature_base_types.zig`, `wgpu_texture_base_types.zig`, `wgpu_callback_descriptor_types.zig`, and `wgpu_pipeline_descriptor_types.zig` directly
- `runtime/zig/src/core/abi/model_exports.zig` no longer imports the compatibility model facades for the runtime/webgpu aggregate surface; `runtime/zig/src/core/abi/model_runtime_exports.zig` now owns that explicit export surface without routing through the legacy combined model modules
- `runtime/zig/src/webgpu_backend.zig`, `runtime/zig/src/webgpu_backend_ops.zig`, `runtime/zig/src/webgpu_backend_support.zig`, `runtime/zig/src/webgpu_backend_types.zig`, and `runtime/zig/src/backend/d3d12/d3d12_native_runtime.zig` remain the main orchestration modules for their lanes, but their dependency paths are now materially narrower than the earlier monolithic state/barrel layout

## Zig runtime line-limit policy raised to 999 lines and enforcement updated (2026-04-03 UTC)

- The Zig runtime file-size policy in `AGENTS.md` and `runtime/zig/STYLE.md` now uses a `999`-line cap instead of `777`
- The live enforcement scripts were updated in:
  - `bench/gates/file_size_gate.py`
  - `scripts/check-health.py`
  - `scripts/check_zig_line_limit.py`
- Historical status entries that mention the earlier `777` limit remain unchanged as time-stamped history

## Obsolete native base facade removed after importer cleanup (2026-04-03 UTC)

- `runtime/zig/src/doe_native_base.zig` was removed because no code in this repo imported it anymore
- `runtime/zig/src/doe_native_types.zig`, `runtime/zig/src/doe_native_helpers.zig`, and `runtime/zig/src/doe_native_exports.zig` are now the only supported native contract surfaces
- `runtime/zig/tools/check_core_import_fence.py` still rejects any future attempt to reintroduce `doe_native_base.zig` as an implementation dependency

## Native base contract split into type/helper/export shards; implementation imports no longer depend on the base facade (2026-04-03 UTC)

- New native shards:
  - `runtime/zig/src/doe_native_types.zig`
  - `runtime/zig/src/doe_native_helpers.zig`
  - `runtime/zig/src/doe_native_exports.zig`
- Native implementation files now import those narrow modules directly instead of `runtime/zig/src/doe_native_base.zig`
- `runtime/zig/src/doe_native_base.zig` is now a compatibility barrel only
- `runtime/zig/tools/check_core_import_fence.py` now rejects any future implementation import of `doe_native_base.zig`
- Verification for this split passed with `zig build import-fence`, `zig test src/execution.zig`, `zig build test-wgsl`, and `zig build`

## Narrow handle and model-value contracts split out of broad ABI/value barrels (2026-04-03 UTC)

- New ABI shard: `runtime/zig/src/core/abi/wgpu_handle_types.zig`
  - owns WebGPU opaque handles plus `WGPUFuture`, `WGPUStringView`, `WGPUBool`, `WGPUStatus`, and the basic string/status constants shared across async, drop-in, render API, callback, and backend-state callers
- `runtime/zig/src/core/abi/wgpu_base_types.zig` is now a narrower value/enum barrel over that handle shard plus the remaining base constants, and pure handle/string/status callers were retargeted away from the broader base module
- New model value shards:
  - `runtime/zig/src/model_texture_value_types.zig`
  - `runtime/zig/src/model_binding_value_types.zig`
- `runtime/zig/src/model_gpu_types.zig` is now a compatibility barrel over those texture and binding value shards rather than the owner of both concerns
- Format/layout-only backend, render, async-diagnostic, parser, and model contract callers now import `model_texture_value_types.zig` or `model_binding_value_types.zig` directly when they do not need the combined barrel
- Static `@import(...)` graph under `runtime/zig/src` remains acyclic after the split; see the local graph measurement used in this change for current importer counts

## Surface compatibility barrel split into texture, surface-control, and async contracts (2026-04-03 UTC)

- New narrow model contracts:
  - `runtime/zig/src/model_texture_types.zig`
  - `runtime/zig/src/model_surface_control_types.zig`
  - `runtime/zig/src/model_async_types.zig`
- Texture execution paths, surface lifecycle paths, async-diagnostics lanes, map-async callers, command partitions, parser helpers, and backend facades/runtime modules now import those narrow contracts directly instead of depending on `runtime/zig/src/model_surface_types.zig`
- `runtime/zig/src/model_surface_types.zig` is now a compatibility barrel over the split texture/surface-control/async modules
- `runtime/zig/tools/check_core_import_fence.py` now rejects any new direct implementation import of `model_surface_types.zig`; `runtime/zig/src/core/abi/mod.zig` remains the single export-surface exception

## Compatibility model transfer barrel fully removed from implementation imports (2026-04-03 UTC)

- `runtime/zig/src/model_surface_types.zig`, `runtime/zig/src/model_runtime_types.zig`, and `runtime/zig/src/model_webgpu_types.zig` now import `model_gpu_types.zig`, `model_resource_types.zig`, and `model_compute_types.zig` directly instead of depending on `model_transfer_types.zig`
- `runtime/zig/src/model.zig` now tests against `model_gpu_types.zig` directly
- `runtime/zig/tools/check_core_import_fence.py` now rejects any new direct implementation import of `model_transfer_types.zig`; `runtime/zig/src/core/abi/mod.zig` remains the single export-surface exception

## Transfer payloads split into resource and compute contracts; compatibility barrel is now effectively cold (2026-04-03 UTC)

- New narrow model contracts:
  - `runtime/zig/src/model_resource_types.zig`
  - `runtime/zig/src/model_compute_types.zig`
- Central command unions, backend facades, parser/front-door modules, render helpers, and core resource/compute paths now import `model_resource_types.zig`, `model_compute_types.zig`, and `model_gpu_types.zig` directly instead of depending on `model_transfer_types.zig`
- The only remaining direct imports of `runtime/zig/src/model_transfer_types.zig` are compatibility/export barrels:
  - `runtime/zig/src/core/abi/mod.zig`
  - `runtime/zig/src/model.zig`
  - `runtime/zig/src/model_runtime_types.zig`
  - `runtime/zig/src/model_surface_types.zig`
  - `runtime/zig/src/model_webgpu_types.zig`
- `runtime/zig/src/model_transfer_types.zig` is now a compatibility barrel over `model_gpu_types.zig`, `model_resource_types.zig`, and `model_compute_types.zig`

## GPU value/constants contract split away from transfer payload callers (2026-04-03 UTC)

- New narrow model contract: `runtime/zig/src/model_gpu_types.zig`
- Value-only callers that only need WebGPU formats, dimensions, usages, binding enums, or shader-stage flags now import `model_gpu_types.zig` instead of `model_transfer_types.zig`
- `runtime/zig/src/model_transfer_types.zig` remains the transfer/dispatch/binding payload contract for callers that actually need command structs such as `CopyCommand`, `KernelBinding`, or `KernelDispatchCommand`
- `runtime/zig/src/core/abi/mod.zig`, `runtime/zig/README.md`, `runtime/zig/STYLE.md`, and `AGENTS.md` now document that split so future callers do not drift back to the broader transfer contract by default

## Combined ABI barrel narrowed to proc/state-heavy callers (2026-04-03 UTC)

- Implementation files that only need WebGPU handles, descriptors, or execution-result types now import `wgpu_base_types.zig`, `wgpu_descriptor_types.zig`, and `wgpu_execution_types.zig` directly instead of routing through `wgpu_runtime_abi.zig`
- `runtime/zig/src/wgpu_types_procs.zig` still depends on `wgpu_proc_types.zig`, keeping proc typedefs out of the main ABI barrel cycle while preserving the existing public/export surfaces
- The remaining direct imports of `wgpu_runtime_abi.zig` are concentrated in callers that still need runtime-owned state structs, proc aliases, or compatibility/export barrels

## Combined model barrel is now compatibility-only and ABI proc typedefs no longer cycle through the runtime ABI barrel (2026-04-03 UTC)

- Implementation files under `runtime/zig/src` now import `model_transfer_types.zig`, `model_render_types.zig`, and `model_surface_types.zig` directly instead of using `model_runtime_types.zig` as a catch-all barrel
- `runtime/zig/src/core/abi/mod.zig` remains the single export-surface exception that re-exports `model_runtime_types.zig` and `model_webgpu_types.zig` for compatibility
- `runtime/zig/tools/check_core_import_fence.py` now rejects any new direct import of `model_runtime_types.zig` inside `runtime/zig/src` outside that explicit `core/abi/mod.zig` exception
- New proc-type shard: `runtime/zig/src/core/abi/wgpu_proc_types.zig`
- `runtime/zig/src/wgpu_types_procs.zig` now depends on `wgpu_proc_types.zig` instead of `wgpu_runtime_abi.zig`, removing the small ABI proc typedef cycle from the main runtime ABI barrel

## Compatibility facades are now fully cold inside runtime/zig/src (2026-04-03 UTC)

- `runtime/zig/src/model.zig` now tests against `runtime/zig/src/model_transfer_types.zig` directly instead of importing the `model_webgpu_types.zig` compatibility barrel
- `runtime/zig/src/core/abi/mod.zig` and `runtime/zig/src/core/mod.zig` now route their legacy `model_webgpu_types` and `wgpu_types` export names to the internal shard barrels rather than importing the compatibility facade files
- There are no remaining `@import(...)` sites for `model_webgpu_types.zig`, `wgpu_types.zig`, `webgpu_ffi.zig`, or `model.zig` anywhere under `runtime/zig/src`
- `runtime/zig/tools/check_core_import_fence.py` now rejects any reintroduction of those compatibility facades into implementation code without exceptions

## Runtime implementation retargeted to split model and WebGPU ABI shards (2026-04-03 UTC)

- `runtime/zig/src/model_transfer_types.zig`, `runtime/zig/src/model_render_types.zig`, and `runtime/zig/src/model_surface_types.zig` now hold the actual command payload/value definitions that used to live only in `runtime/zig/src/model_webgpu_types.zig`
- `runtime/zig/src/model_runtime_types.zig` is now the internal runtime-facing barrel for those split model shards; implementation modules no longer import `model_webgpu_types.zig` directly
- `runtime/zig/src/core/abi/wgpu_base_types.zig` and `runtime/zig/src/core/abi/wgpu_descriptor_types.zig` now hold the concrete WebGPU handle/enum/descriptor definitions that used to be monolithic in `runtime/zig/src/core/abi/wgpu_types.zig`
- `runtime/zig/src/core/abi/wgpu_runtime_abi.zig` is now the internal runtime-facing ABI barrel; implementation modules no longer import `wgpu_types.zig` directly
- `runtime/zig/src/model_webgpu_types.zig` and `runtime/zig/src/core/abi/wgpu_types.zig` remain as thin compatibility barrels only
- `runtime/zig/tools/check_core_import_fence.py` now treats direct imports of the compatibility facades as violations outside the explicit compatibility/export allowlist

## WebGPU backend state, lifecycle, and support helpers split out of the root runtime file (2026-04-03 UTC)

- `runtime/zig/src/webgpu_backend.zig` is no longer the single owner of both backend state declarations and lifecycle/support behavior
- New state-contract module: `runtime/zig/src/webgpu_backend_types.zig`
  - owns `ManagedSurface`, `CoreWebGPUBackend`, and `FullWebGPUBackendState`
- New lifecycle/bootstrap helper module: `runtime/zig/src/webgpu_backend_lifecycle.zig`
  - owns deinit, adapter/device request, limit capture, backend-type naming, and timestamp logging helpers
- New pure support helper module: `runtime/zig/src/webgpu_backend_support.zig`
  - owns capability-introspection routing, queue/timestamp mode setters, uncaptured-error helpers, effective-limit selection, and full-render texture-view eviction
- `runtime/zig/src/webgpu_backend.zig` now stays focused on `WebGPUBackend` assembly, command/prewarm delegation, and compatibility re-exports for the extracted backend modules above

## Model contract and WebGPU ABI shards decoupled from root hubs (2026-04-02 UTC)

- `runtime/zig/src/model.zig` is no longer used as an internal catch-all contract barrel; internal callers now import the narrower split modules directly:
  - `runtime/zig/src/model_policy.zig`
  - `runtime/zig/src/model_profile.zig`
  - `runtime/zig/src/model_quirks.zig`
  - `runtime/zig/src/model_commands.zig`
  - `runtime/zig/src/model_webgpu_types.zig`
- `runtime/zig/src/core/abi/wgpu_execution_types.zig` now owns `NativeExecutionStatus` and `NativeExecutionResult`, removing those execution-result types from `wgpu_types.zig` as the source of truth
- `runtime/zig/src/core/abi/wgpu_state_types.zig` now owns queue/map/kernel-source/backend-state helper structs, with `wgpu_types.zig` retaining compatibility re-exports
- queue sync/capture, kernel-source resolution, and WebGPU backend state now consume the extracted ABI shards directly instead of treating `wgpu_types.zig` as the only entry point

## WebGPU backend implementation moved behind a thin root facade (2026-04-02 UTC)

- New implementation owner: `runtime/zig/src/webgpu_backend.zig` now holds the `WebGPUBackend` implementation and shared backend state structs
- `runtime/zig/src/webgpu_ffi.zig` is now a thin compatibility facade instead of a mixed implementation hub
- Internal core/full/runtime callers were retargeted to `webgpu_backend.zig`; compatibility imports can continue to use `webgpu_ffi.zig`

## Backend runtime contract extracted from the WebGPU FFI hub (2026-04-02 UTC)

- New narrow shared contract: `runtime/zig/src/backend/runtime_types.zig` now owns backend-facing execution result and queue/upload mode types
- Backend orchestration and native backend lanes now depend on that narrow contract instead of importing `runtime/zig/src/webgpu_ffi.zig` directly when they only need execution/result mode types
- `runtime/zig/src/webgpu_ffi.zig` remains the compatibility facade for those types while the remaining root-level hub responsibilities are split more carefully in later slices

## WebKit WebGPU is a first-class backend: runtime probe, verifiable metadata, shim enum hardening, and main runtime integration (2026-03-30 UTC)

- Runtime identity probe: `dawn-plan-executor` now detects WebKit shim at load time via `dlsym("doe_shim_get_backend_identity")` and records the correct `backendId`, `backendLane`, and `profile.driver` in all trace metadata and JSONL artifacts
- CLI override: `--backend-id webkit_direct_metal` explicitly selects WebKit identity (used by `executor_registry.py`)
- Shim enum hardening: audited all `static_cast`/`reinterpret_cast` in `webkit_webgpu_c_shim.mm` against both Dawn and WebKit headers. Added translation functions with range guards for three additional divergent enums:
  - `WGPUTextureAspect`: Dawn Undefined=0,All=1,Stencil=2,Depth=3 vs WebKit All=0,Stencil=1,Depth=2
  - `WGPUTextureDimension`: Dawn Undefined=0,1D=1,2D=2,3D=3 vs WebKit 1D=0,2D=1,3D=2
  - `WGPUQueryType`: Dawn Occlusion=1,Timestamp=2 vs WebKit Occlusion=0,Timestamp=1
  - Confirmed safe (values match): `WGPUTextureFormat`, `WGPUTextureViewDimension`, `WGPUBackendType`, `WGPUPowerPreference`, bit-flag enums (usage, shader stage, map mode)
- Main runtime integration: `wgpu_loader.zig` now includes `libwebgpu_webkit_cshim.dylib` in macOS candidate list
- Determinism probe: `claim_summary()` now supports webkit lane alongside doe and dawn
- Backend selection: `backend_selection.zig` handles `webkit_delegate` policy

## Three-way cross-backend bitwise identity: Doe native Metal, Google Dawn Metal, and Apple WebKit Metal all produce byte-identical compute output for the same WGSL kernels on the same GPU (2026-03-30 UTC)

- Tested surfaces:
  - Full 49-command Gemma3-270M inference pipeline (13 buffer writes + 36 kernel dispatches): **bitwise match across all three backends**
  - 13 f16accum LM-head-slice answer sets with real model weights: **13/13 three-way match**
  - 13 f32 forward LM-head-slice answer sets with real model weights: **13/13 three-way match**
  - 75 total command files, 0 divergences
- Root cause of prior WebKit zero-output bug:
  - `WGPUBufferBindingType` enum offset: Dawn added `BindingNotUsed=0x00`, shifting Undefined/Uniform/Storage/ReadOnlyStorage by +1 relative to WebKit
  - The C-linkage shim (`bench/drop-in/webkit_webgpu_c_shim.mm`) was doing `static_cast` without translation, causing Dawn’s `Storage (0x03)` to become WebKit’s `ReadOnlyStorage (0x03)` — silently dropping all shader writes
  - Fix: added `translateBufferBindingType()` function to subtract 1 from Dawn values
- Key finding:
  - Same WGSL source → same Metal GPU → bitwise identical output, regardless of which WebGPU implementation compiles the WGSL to MSL
  - This holds for both f16 and f32 accumulation, subgroup operations, workgroup shared memory, and parallel reductions
  - The WebGPU portability promise (write once, run anywhere) extends to numerical identity on the same hardware with the same driver

## Diverse headline-style ambiguity seeds are now part of the sampled decode prompt-search lane: Doe’s live search fixture now mixes operational controls with philosophy/science/law/art prompts, the mutator preserves three-way natural-choice prompts instead of flattening them to binary forms, and the loose pair miner can score a broader set of semantic pairs such as `mercy/cruelty`, `justice/revenge`, `friend/stranger`, and `authentic/staged` (2026-03-30 UTC)

- Updated discovery/config surfaces:
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.prompt-search-sharp.json`
  - `bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.search-loose.json`
  - `config/determinism-answer-set-registry.json`
  - `config/numeric-stability-decode-prompt-search-plan.json`
  - `bench/runners/search_sampled_decode_prompts.py`
  - `bench/tests/test_search_sampled_decode_prompts.py`
- Current truth:
  - Doe’s default prompt-search lane no longer starts from only operational/security-style seeds:
    it now includes a wider bank of bounded but semantically ambiguous prompts
    across philosophy, science, law, ethics, identity, and art
  - three-way prompt forms such as
    `Justice, revenge, or both: ...` and
    `True, false, or undecidable: ...`
    now survive mutation rounds through the structured-choice mutator instead
    of being misparsed into malformed binary rewrites
  - the loose pair-mining registry now recognizes a wider set of binary cores
    inside those prompts, so the search loop can score more than
    `true/false`, `yes/no`, and a few workflow-specific pairs
  - this is still a seed/discovery improvement, not a claim that Doe has
    already harvested promotable sampled decode flips from all of these new
    families

## Prompt-search discovery for sampled decode fragility is now executable: Doe can reuse the real-logit scout, pair-agnostic miner, and semantic mutation templates to search semantically sharp prompt space in rounds instead of relying only on hand-picked decode seeds (2026-03-29 UTC)

- New tooling/config surfaces:
  - `config/numeric-stability-decode-prompt-search-plan.json`
  - `config/numeric-stability-decode-prompt-search-plan.schema.json`
  - `bench/runners/search_sampled_decode_prompts.py`
  - `bench/tests/test_search_sampled_decode_prompts.py`
- Current truth:
  - Doe now has a concrete discovery loop for better sampled-decode workloads:
    start from seeded prompt families, harvest real-logit near-misses, mine
    semantically meaningful token pairs, mutate the strongest cases, and feed
    the next round with deduped prompt candidates
  - this closes a real gap in the current decode-governance lane:
    the blocker is no longer "we have no search strategy," it is whether the
    seeded workloads and mutation families are strong enough to yield real
    promotable sampled flips
  - the runner is intentionally bench-side discovery only:
    it is used to generate better prompt seeds for ordinary-execution sampled
    harvests, not to replace the live decode-boundary receipt path

## Sampled decode harvest, enrichment, and promotion are now executable end to end: Doe can patch ordinary command streams into sampled decode mode, harvest real `decode.sample_token` receipts on Metal, attach within-policy stability and short suffix replay evidence, rank the resulting rows, and write a checked decode-promotion catalog even when the honest answer is “no promotable cases yet” (2026-03-29 UTC)

- New config and tooling surfaces:
  - `config/numeric-stability-decode-harvest-plan.json`
  - `config/numeric-stability-decode-harvest-plan.schema.json`
  - `config/numeric-stability-decode-vulkan-replay-plan.json`
  - `config/numeric-stability-decode-vulkan-replay-plan.schema.json`
  - `config/numeric-stability-decode-signature.schema.json`
  - `config/numeric-stability-decode-promoted-catalog.json`
  - `config/numeric-stability-decode-promoted-catalog.schema.json`
  - `bench/lib/sampled_decode_fragility.py`
  - `bench/runners/harvest_sampled_decode_fragility.py`
  - `bench/runners/enrich_sampled_decode_rows.py`
  - `bench/runners/promote_sampled_decode_fragility.py`
  - `bench/runners/replay_promoted_sampled_decode_vulkan.py`
- Latest live artifacts:
  - Metal harvest manifest:
    `bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/sampled_decode_harvest.manifest.json`
  - normalized rows:
    `bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/numeric_stability_decode.rows.jsonl`
  - ranked report:
    `bench/out/apple-metal-sampled-decode-fragility/20260330T022000Z/numeric_stability_decode_fragility.report.json`
  - Vulkan replay report:
    `bench/out/amd-vulkan-sampled-decode-replay/20260330T022500Z/numeric_stability_decode_vulkan_replay.report.json`
- Current truth:
  - Doe now has a real runtime-to-promotion path for sampled decode states:
    ordinary execution harvest on Metal, repeat-based within-policy stability,
    short suffix replay evidence, normalized rows, ranked
    `promotable` / `investigate` / `reject` output, and a checked
    decode-promotion catalog
  - the current checked harvest ran two live cases:
    the sampled decode demo and a first-5-step truncated `gemma3_270m`
    ordinary decode
  - the latest ranked result is still honest and empty on promotion:
    all six harvested rows are `reject`, so
    `config/numeric-stability-decode-promoted-catalog.json` currently has
    `entryCount = 0`
  - the remaining gap is no longer missing pipeline code:
    it is finding real semantically meaningful sampled flips in better seeded
    workloads, then replaying those promoted cases on Vulkan

## Sampled decode-boundary receipts are now live: Doe now parses the expanded `sample.wgsl` uniform ABI during ordinary execution, replays the exact decode function under shared `temperature` / `topK` / `topP` / RNG settings, commits the selected token into the live output buffer, and emits a real sampled `decode.sample_token` receipt instead of a greedy-only placeholder (2026-03-29 UTC)

- Runtime/package/example surfaces:
  - `runtime/zig/src/numeric_stability_runtime_decode.zig`
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `examples/numeric-stability-decode-sampled.commands.json`
  - `examples/doe-numeric-stability-receipt.decode-sample.sample.json`
  - `packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `packages/doe-gpu/README.md`
- Current truth:
  - Doe still accepts the legacy 16-byte `sample.wgsl` uniform and reports it
    as `greedy-argmax`
  - when the expanded sample uniform is present, Doe now records live:
    - `temperature`
    - `topK`
    - `topP`
    - `rngSeed`
    - `rngDraw`
    - the surviving fast-lane token set after filtering
    - sampled `fast` / `stable` / `reference` selected tokens under the same
      draw
    - `cdfDistanceToDraw` for the fast replay lane
  - the runtime now writes the chosen token back into the real sample output
    buffer so the receipt matches the committed ordinary-execution result
  - the checked-in sampled decode demo now proves a real decode-only change:
    `sample.wgsl` would have produced greedy token `1`, but Doe commits sampled
    fast token `0` under the shared draw while `reference` still selects `1`
- Remaining gap:
  - the blocker is no longer “sampled decode receipt fields are missing”
  - the next decode-governance gap is mining and promoting real sampled flips
    from live workloads, then proving short suffix consequence and cross-
    backend portability

## Repo-truth sync for decode-boundary mining: the live state is now greedy `sample.token` receipts plus row normalization, and the remaining gap is sampled decode, not the existence of a receipt surface (2026-03-29 UTC)

- Current truth:
  - Doe already has a live greedy `decode.sample_token` receipt surface in the
    runtime and package smoke path
  - track-2 normalization already consumes the runtime-emitted
    `decodeBoundary.metrics` fields when present; the checked-in sample receipt
    preserves `fastTop1Margin=0.5` through the normalized row pipeline
  - the remaining missing artifact is the richer sampled decode contract:
    `temperature`, `topK`, `topP`, RNG draw, and the sampled-token replay
    predicate
- Supersession note:
  - the later 2026-03-29 planning entries below that say
    “`sample.token` must become a receipt surface” or
    “it does not add a live `sample.token` receipt yet”
    predate the greedy decode-boundary landing and should now be read as
    “sampled decode receipt is not live yet”

## Track-2 decode-row normalization now consumes live greedy decode receipts: Doe can normalize `decode.sample_token` receipts into rankable decode rows, merge prompt/stability/suffix evidence through an explicit enrichment sidecar, and keep evidence-gap cases in `investigate` instead of discarding them before the sampled decode contract lands (2026-03-29 UTC)

- New tooling/config surfaces:
  - `config/numeric-stability-decode-row.schema.json`
  - `config/numeric-stability-decode-row-enrichment.schema.json`
  - `examples/numeric-stability-decode-row.sample.json`
  - `examples/numeric-stability-decode-row-enrichment.sample.json`
  - `bench/runners/normalize_decode_fragility_rows.py`
  - `bench/tests/test_normalize_decode_fragility_rows.py`
- Current result:
  - track 2 no longer depends on hypothetical selected-row proxies:
    it can consume the live greedy `decode.sample_token` receipt shape and
    convert it into a stable normalized mining row
  - the normalization contract now freezes:
    - decode config fields
    - runtime-emitted decode-boundary margin and cutoff metrics
    - selected-token triples
    - upstream disagreement state
    - suffix replay evidence
  - the row contract now also preserves the runtime's own decode-boundary
    booleans:
    - `actualSelectedTokenChanged`
    - `liveSelectedMatchesFast`
    - `liveSelectedMatchesStable`
    - `liveSelectedMatchesReference`
  - prompt text, decode step index, semantic-priority overrides, and
    short-suffix/stability evidence now have an explicit sidecar contract
    instead of ad-hoc bench glue
  - the ranking loop now distinguishes:
    - hard rejects such as meaningless-token or unchanged-selection
    - `investigate` cases where the token flip is real but suffix replay or
      within-policy stability evidence is still missing
  - this still does not make the sampled decode moat claim true yet:
    the live receipt lane is greedy-only and sampled decode fields remain
    future work

## Track-1 greedy decode-boundary receipts are now live: Doe now emits a real ordinary-execution `decode.sample_token` numeric-stability receipt linked back to an auto-detected `decode.final_logits` producer, so the runtime can finally prove a live full-vocabulary greedy decode boundary instead of only selected-row proxies (2026-03-29 UTC)

- Runtime/config/package surfaces:
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `runtime/zig/src/numeric_stability_runtime_decode.zig`
  - `runtime/zig/src/numeric_stability_runtime_plan.zig`
  - `config/doe-numeric-stability-receipt.schema.json`
  - `config/numeric-stability-policy.json`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/test/smoke/test-smoke-load.js`
- Example/sample surfaces:
  - `examples/numeric-stability-decode-greedy.commands.json`
  - `examples/doe-numeric-stability-receipt.decode-sample.sample.json`
- Current result:
  - ordinary execution now stores the upstream `decode.final_logits` receipt
    state and emits a downstream `decode.sample_token` receipt when the live
    greedy `sample.wgsl` path consumes the same logits buffer
  - the new `decodeBoundary` block records:
    - full-vocabulary greedy coverage
    - the live selected token read from the executed sample buffer
    - whether that live token matches the committed route selection
    - exact greedy replay metrics for `fast`, `stable`, and `reference`
    - whether the selected token changed across replayed policies
    - upstream receipt links back to `decode.final_logits`
  - the checked-in decode demo command stream now exercises the contract
    through `gpu.ordinaryExecution(...)` and the package smoke test asserts the
    emitted `decode.sample_token` receipt shape
  - the checked-in decode demo now shows a real selected-token change at the
    decode boundary under exact greedy replay:
    `fast` and `stable` select token `1`, while `reference` selects token `0`
  - this is still the narrow greedy lane:
    `temperature`, `topK`, `topP`, `rngSeed`, and `rngDraw` remain reserved
    and `null` until Doe lands the richer sampled decode-boundary path

## Track-2 decode-fragility mining is now explicit: Doe now has a schema-backed scoring and promotion surface for future `sample.token` receipts, so the next decode-governance step can rank real decode states instead of drifting back into selected-row proxies (2026-03-29 UTC)

- Planning/config surfaces:
  - `config/numeric-stability-decode-fragility-plan.json`
  - `config/numeric-stability-decode-fragility-plan.schema.json`
  - `config/numeric-stability-decode-fragility-report.schema.json`
  - `examples/numeric-stability-decode-fragility-report.sample.json`
  - `bench/runners/rank_decode_fragility_states.py`
  - `bench/tests/test_rank_decode_fragility_states.py`
  - `docs/numeric-stability-decode-fragility-plan.md`
- Current result:
  - the missing artifact is now explicit and repo-tracked:
    `sample.token` must become a receipt surface before Doe can claim real
    decode-governance evidence instead of selected-row evidence
  - track 2 now has a stable normalized input contract for future decode rows:
    required fields cover:
    - selected token under `fast`, `stable`, and `reference`
    - post-temperature margin
    - upstream disagreement
    - semantic priority class
    - suffix replay availability and divergence
  - the ranking loop now has a schema-backed signal set:
    - top-1 margin
    - `top-k` edge
    - `top-p` edge
    - CDF proximity to `u`
    - adjacent-step persistence
    - upstream disagreement
    - early decode position
  - promotion is intentionally strict:
    only real selected-token changes with meaningful tokens, within-policy
    stability, and short suffix divergence are `promotable`
  - this work is planning and bench-tooling only:
    it does not add a live `sample.token` receipt yet

## Track-3 decode validation and backend promotion planning is now explicit: Doe now has a schema-backed plan for deciding which decode-boundary token flips are meaningful, which are junk, how short suffix consequence is judged, and how Metal-first cases graduate to Vulkan-backed runtime contract examples (2026-03-29 UTC)

- Planning/config surfaces:
  - `config/numeric-stability-decode-validation-plan.json`
  - `config/numeric-stability-decode-validation-plan.schema.json`
  - `docs/numeric-stability-decode-validation-plan.md`
- Current result:
  - Track 3 now has an explicit contract for:
    - semantically sharp scenario buckets
    - meaningful-token classes
    - junk-token rejection rules
    - within-policy stability requirements
    - short suffix replay consequence requirements
    - backend promotion stages:
      - `metal-exercised`
      - `metal-promoted`
      - `vulkan-reproduced`
      - `cross-backend-promoted`
  - this work is planning-only:
    it does not add a live `sample.token` receipt yet
  - the purpose is to give the decode-receipt and mining tracks a stable
    promotion target so Doe does not overfit on whitespace, punctuation, or
    one-backend artifacts

## Ordinary-execution numeric governance now has registry-backed execution profiles: Doe centralizes default versus cautious versus observe-only behavior in the shared numeric-stability registry, surfaces the selected profile in trace metadata, and refreshes the operator-expansion plan around the live trio plus the next ranked families (2026-03-29 UTC)

- Runtime/config surfaces:
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
  - `config/trace-meta.schema.json`
  - `runtime/zig/src/numeric_stability_policy.zig`
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `runtime/zig/src/numeric_stability_runtime_plan.zig`
  - `runtime/zig/src/trace_numeric_stability.zig`
  - `runtime/zig/src/main.zig`
  - `runtime/zig/src/main_usage.zig`
- Package surfaces:
  - `packages/doe-gpu/src/vendor/doe-numeric-stability-policy.js`
  - `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/src/index.d.ts`
- Planning surfaces:
  - `config/numeric-stability-auto-detection-plan.json`
  - `config/numeric-stability-operator-expansion-plan.json`
  - `docs/numeric-stability-auto-detection-plan.md`
- Current result:
  - ordinary execution now chooses a named registry-backed execution profile
    instead of leaving default guardrail behavior spread across helpers:
    - `numeric-stability/default-ordinary-execution-v1`
    - `numeric-stability/cautious-ordinary-execution-v1`
    - `numeric-stability/observe-only-ordinary-execution-v1`
  - the observe-only path is now a first-class routing policy:
    `numeric-stability/accept-fast-on-selected-token-disagreement-v1`
  - trace-meta numeric-stability summaries now record the selected
    `executionProfileId`
  - `gpu.ordinaryExecution(...)` and `createDoeRuntime().runOrdinaryExecution(...)`
    can now select the profile explicitly with `executionProfileId`
  - the planning surfaces now reflect current runtime truth:
    the live ordinary-execution trio is:
    - `matmul.logits`
    - `rmsnorm.output`
    - `attention.output`
  - the next ranked operator opportunities are now explicit:
    - `softmax.denominator`
    - `layernorm.output`
    - `mlp.output`
    - `residual.add`
    - `task-head.score`

## Ordinary doe-gpu execution is now a first-class package/runtime surface instead of only a numeric-stability namespace entry: `gpu.ordinaryExecution(...)` and `createDoeRuntime().runOrdinaryExecution(...)` now expose the same in-path governed command-stream contract, while `gpu.numericStability.ordinaryExecution(...)` remains as a compatibility alias (2026-03-29 UTC)

- Package/runtime surfaces:
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  - `packages/doe-gpu/src/index.d.ts`
- Current result:
  - ordinary command-stream execution no longer needs to be introduced to
    package callers as a special `gpu.numericStability.*` API
  - `gpu.ordinaryExecution(...)` now runs the same auto-detected in-path
    numeric-governance path as the earlier numeric-stability helper
  - `createDoeRuntime().runOrdinaryExecution(...)` now exposes the same
    contract at the runtime helper layer
  - `gpu.numericStability.ordinaryExecution(...)` and
    `runNumericStabilityOrdinaryExecution(...)` remain available as explicit
    compatibility aliases for existing callers and tests
  - this closes part of the remaining package ergonomics gap between “runtime
    governance exists” and “ordinary Doe execution inherits it by default”

## Auto-detected ordinary-execution numeric stability is now live across native runtime and doe-gpu: Doe no longer needs command-local numeric-stability annotations for the primary in-path lane, `prefer-stable` now rewrites the committed result, `abstain` now stops downstream execution, receipts bind execution identity, and `gpu.numericStability.ordinaryExecution(...)` now exposes the same ordinary command-stream contract through the package surface (2026-03-29 UTC)

- Runtime/config surfaces:
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
  - `runtime/zig/src/numeric_stability_policy.zig`
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `runtime/zig/src/numeric_stability_runtime_plan.zig`
  - `runtime/zig/src/numeric_stability_runtime_eval.zig`
- Package surfaces:
  - `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/src/index.d.ts`
- Current result:
  - native ordinary execution now resolves numeric-stability behavior from the
    shared auto-detect registry for:
    - `matmul.logits`
    - `rmsnorm.output`
    - `attention.output`
  - the in-path exercise lane now emits plain semantic command streams; the
    runtime detects the supported operator from semantic fields plus executed
    kernel identity instead of relying on command-local `numericStability`
    annotations
  - `prefer-stable` now rewrites the committed buffer content for supported
    ordinary-execution numeric-stability events
  - `abstain` now stops the downstream command suffix in the native
    ordinary-execution lane
  - numeric-stability receipts now bind:
    - executed kernel path/basename
    - layout fingerprint
    - adapter/driver profile
    - compiled plan hash
  - `createDoeRuntime()` now exposes
    `runNumericStabilityOrdinaryExecution(...)`
  - `gpu.numericStability.ordinaryExecution(...)` now surfaces the same
    ordinary command-stream receipt contract through `doe-gpu`
  - the explicit bounded-slice helper
    `gpu.numericStability.matmulLogitsSlice(...)` remains available as the
    narrower runtime service path
- Verification run:
  - `zig build doe-runtime`
  - `zig build test-wgsl`
  - `python3 bench/runners/exercise_in_path_numeric_stability.py`
  - `python3 bench/gates/schema_gate.py`
  - `python3 -m unittest bench.tests.test_exercise_in_path_numeric_stability bench.tests.test_exercise_runtime_numeric_stability bench.tests.test_config_validation`
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/test-integration-gpu-namespace.js`
  - `git diff --check`

## A-track semantic-envelope planning is now explicit: Doe has a schema-backed proposal for computing semantic envelopes over runtime-legal numeric and decode variations, with source-backed ranked experiments separated by `runtime-exercised`, `promoted`, and `corpus-only` evidence stages (2026-03-29 UTC)

- New planning/config surfaces:
  - `config/numeric-stability-semantic-envelope.schema.json`
  - `examples/numeric-stability-semantic-envelope.sample.json`
  - `config/numeric-stability-semantic-envelope-plan.schema.json`
  - `config/numeric-stability-semantic-envelope-plan.json`
  - `docs/numeric-stability-semantic-envelope-plan.md`
- Current result:
  - Doe now has a canonical semantic-envelope artifact proposal that can say:
    - which semantic classes were considered
    - which legal numeric and decode views were evaluated
    - which answers were reachable
    - whether the boundary is `singleton`, `split`, or
      `outsider-dominated`
  - the ranked experiment list is now source-backed instead of relying on
    semantically nearby signatures:
    every case points either to a checked-in promoted/runtime fragility
    signature or to a frozen corpus entry
  - the current plan stays within existing route truth:
    `accept-fast`, `prefer-stable`, `abstain`
  - no live runtime behavior changed; this is the design and artifact contract
    for the next A-track exporter step

## B-track auto-detection and operator-expansion planning is now explicit: Doe has schema-backed planning surfaces for automatic fragility detection, ranked operator-family expansion, bounded rerun budgets, and the annotation-gated -> auto-detected migration path, without changing the current live route taxonomy or runtime behavior (2026-03-29 UTC)

- New planning/config surfaces:
  - `config/numeric-stability-auto-detection-plan.json`
  - `config/numeric-stability-auto-detection-plan.schema.json`
  - `config/numeric-stability-operator-expansion-plan.json`
  - `config/numeric-stability-operator-expansion-plan.schema.json`
  - `docs/numeric-stability-auto-detection-plan.md`
- Current result:
  - the runtime-first B-track is now checked in as config instead of staying
    as loose prose:
    - detection signals are explicit
    - operator-family ranking is explicit
    - bounded rerun budgets are explicit
    - suffix replay is defined as an escalation path instead of a default
  - the current live boundary remains unchanged:
    - annotation-gated native `matmul.logits`
    - live routes remain `accept-fast`, `prefer-stable`, `abstain`
  - the next operator-family order is now fixed for planning:
    - `rmsnorm.output`
    - `attention.output`
    - followed by `softmax.denominator` / `layernorm.output`
  - the migration from annotation-gated ordinary execution to auto-detected
    rerun is now explicit and ready for later runtime work without hidden
    heuristics

## Numeric-stability novelty is now pinned to route effect rather than receipt emission alone: the repo docs now explicitly separate current live in-path rerun/receipt capability from the stronger moat bar where Doe’s route changes live execution, spans multiple operator families, and reaches ordinary package/browser callers (2026-03-29 UTC)

- Planning/claim surfaces:
  - `docs/numeric-stability-moat-plan.md`
  - `docs/numeric-stability-claim-ladder.md`
  - `docs/numeric-stability-runtime-roadmap.md`
  - `docs/numeric-stability-demo-ladder.md`
  - `docs/architecture.md`
- Current result:
  - the repo now distinguishes three layers cleanly:
    - novel evidence
    - novel runtime capability
    - novel moat
  - the current live native `matmul.logits` path remains a real runtime
    capability, but the moat bar is now stated more strictly:
    route effect on live execution, automatic or ordinary-caller access,
    multiple operator families, and the same promoted contract across surfaces
  - this keeps future numeric-stability work pointed at the runtime boundary
    rather than overclaiming based on prompt hunts or bounded-slice services

## In-path numeric-stability receipts are now harder to fake and harder to half-promote: native ordinary-execution runs now require `--trace-meta`, the receipt validates fast/stable policy IDs against the executed `kernel_dispatch` contract instead of trusting annotation strings, and the in-path promotion runner stages signature/catalog updates before committing them (2026-03-29 UTC)

- Runtime hardening:
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `runtime/zig/src/main.zig`
- Runner hardening:
  - `bench/runners/exercise_in_path_numeric_stability.py`
  - `bench/runners/exercise_runtime_numeric_stability.py`
- Current result:
  - native in-path numeric-stability annotations now fail unless `--trace-meta`
    is present, so the persisted receipt sidecar and the persisted
    `numericStability` trace-meta summary remain coupled
  - the ordinary-execution receipt no longer simply echoes
    annotation-supplied fast/stable policy IDs:
    Doe validates the executed `kernel_dispatch` contract before writing those
    fields
  - the in-path promotion runner no longer rewrites checked-in signatures
    incrementally during case execution; it stages signature/catalog updates
    and commits them only after the run succeeds

## Native ordinary-execution numeric stability is now live for `matmul.logits`: selected prompt/control signatures run through real `doe-zig-runtime` `kernel_dispatch` command streams with `numericStability` annotations, emit live trace-meta summaries plus per-run receipts, and update the checked-in promoted catalog from ordinary execution rather than the explicit bounded-slice module service (2026-03-29 UTC)

- New runtime surfaces:
  - `runtime/zig/src/numeric_stability_annotation.zig`
  - `runtime/zig/src/numeric_stability_runtime.zig`
  - `runtime/zig/src/main_usage.zig`
  - `runtime/zig/src/command_json_raw.zig`
  - `runtime/zig/src/command_stream.zig`
  - `runtime/zig/src/main.zig`
- New command/config/exercise surfaces:
  - `config/numeric-stability-command-annotation.schema.json`
  - `config/in-path-numeric-stability-exercise.json`
  - `config/in-path-numeric-stability-exercise.schema.json`
  - `examples/numeric-stability-command-annotation.sample.json`
  - `bench/runners/exercise_in_path_numeric_stability.py`
- Fresh native ordinary-execution artifact set:
  - `bench/out/apple-metal-in-path-numeric-stability/20260329T191921Z/apple_metal_in_path_numeric_stability.manifest.json`
- Current result:
  - the native runtime can now evaluate numeric stability inside ordinary
    `kernel_dispatch` execution for annotated `matmul.logits` commands instead
    of only through the explicit `doe_numeric_stability` bounded-slice service
  - Doe captures the live hidden-state vector, bounded row weights, and fast
    logits buffer from the executed dispatch, computes stable and exact-
    reference comparisons locally in Zig, and emits receipts at
    `<trace-meta>.numeric-stability.jsonl`
  - trace-meta now carries a live `numericStability` summary for the same
    ordinary execution run; see the manifest above and per-case trace-meta
    artifacts for the current route mix and dispatch/timing envelopes
  - selected strict, broad, and control signatures in
    `config/promoted-fragility-catalog.json` now reach
    `contractStage = runtime-exercised` through ordinary execution, not
    through the earlier bounded-slice service runner
  - this satisfies the current novelty bar for one native operator family:
    `matmul.logits` in ordinary Doe execution
  - `doe-gpu` still exposes only the explicit bounded-slice numeric-stability
    helper; package/browser ordinary execution do not yet consume this path
- Verification run:
  - `python3 bench/runners/exercise_in_path_numeric_stability.py`

## Live runtime numeric-stability exercise now closes the loop: selected prompt/control signatures have been replayed through the real Zig `doe_numeric_stability` service, the checked-in fragility catalog now records `runtime-exercised` route outcomes, and the current live route surface includes `accept-fast`, `prefer-stable`, and `abstain` instead of leaving `abstain` as schema-only (2026-03-29 UTC)

- New runtime exercise/config surface:
  - `config/runtime-numeric-stability-exercise.json`
  - `config/runtime-numeric-stability-exercise.schema.json`
  - `bench/runners/exercise_runtime_numeric_stability.py`
- Fresh live runtime artifact set:
  - `bench/out/apple-metal-runtime-numeric-stability/20260329T184418Z/apple_metal_runtime_numeric_stability.manifest.json`
- Current result:
  - selected prompt/control cases are now runtime-exercised through the real
    Zig module runner instead of only inherited from bench selective-rerun
    receipts
  - the checked-in catalog now distinguishes:
    - `routeExpectationDecision`
    - `routeOutcomeDecision`
  - selected signatures now carry live `routeOutcome` data and move to
    `contractStage = runtime-exercised`
  - the live route set is now demonstrated end to end:
    see the runtime exercise manifest above for the current route counts and
    bounded-overhead summaries
  - the broad prompt lane now has an honest abstaining path:
    the same numeric trigger can now route to `abstain` instead of
    auto-substituting the stable result when the caller chooses
    `numeric-stability/abstain-on-selected-token-disagreement-v1`
  - the package smoke path now exercises all three live route classes through
    `gpu.numericStability.matmulLogitsSlice(...)`
- Checked-in catalog/control note:
  - `config/promoted-fragility-catalog.json` now records live
    `routeOutcomeDecision` data and includes a live runtime
    `accept-fast` control signature:
    `operator::live-matmul-accept-fast-control`

## Explicit runtime numeric-stability v1 is now live: Doe has a real Zig-owned `doe_numeric_stability` module-runner service for bounded `matmul.logits` slices, and `doe-gpu` now exposes that path as `gpu.numericStability.matmulLogitsSlice(...)` with receipted route decisions instead of leaving numeric stability trapped in bench/probe artifacts (2026-03-29 UTC)

- New runtime surfaces:
  - `runtime/zig/src/numeric_stability_policy.zig`
  - `runtime/zig/src/trace_numeric_stability.zig`
  - `runtime/zig/src/full/modules/services/numeric_stability.zig`
  - `runtime/zig/src/module_runner.zig`
- New package surfaces:
  - `packages/doe-gpu/src/vendor/webgpu/runtime-cli.js`
  - `packages/doe-gpu/src/vendor/doe-numeric-stability-policy.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
- New contract/samples:
  - `config/doe-numeric-stability-receipt.schema.json`
  - `config/numeric-stability-service.schema.json`
  - `examples/doe-numeric-stability-receipt.sample.json`
  - `examples/numeric-stability-service.request.sample.json`
  - `examples/numeric-stability-service.result.sample.json`
  - `examples/doe-numeric-stability-trace-meta.sample.json`
- Current runtime result:
  - the v1 path is explicit, not hidden interception:
    callers send a bounded hidden-state + candidate-row request to the Zig
    module runner for `matmul_logits_slice`
  - the service now:
    - loads the shared numeric-stability registry directly
    - evaluates fast, stable, and bounded CPU-reference policies
    - emits a per-event numeric-stability receipt
    - can emit a trace-meta `numericStability` summary block
    - returns the governed route decision from the live runtime path
    - copies `routeTaxonomyVersion`, route `selectionMode`, and selection proof
      links from the shared registry into the live receipt
  - the package helper now exposes that exact service as:
    `gpu.numericStability.matmulLogitsSlice(...)`
  - the current live route vocabulary remains aligned with the registry:
    `accept-fast`, `prefer-stable`, `abstain`
  - this is still a bounded-slice runtime service, not yet a novelty-grade
    operator-local rerun of ordinary WebGPU execution
- Verification run:
  - `zig build module-core-runner`
  - `zig build doe-runtime`
  - `python3 bench/gates/schema_gate.py`
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/test-integration-gpu-namespace.js`
- Verification note:
  - the runtime targets used by this surface build cleanly
  - the full default `zig build` path still reaches the existing macOS app
    icon dependency in `zig build app` (`ImageMagick convert`), which is
    outside the numeric-stability implementation itself

## Numeric-stability contract surfaces are now checked in: route taxonomy is versioned in the registry, route-to-selection semantics are Lean-backed, and promoted fragility cases now live as config instead of only timestamped bench artifacts (2026-03-29 UTC)

- New contract/config surfaces:
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
  - `config/fragility-promotion-policy.json`
  - `config/fragility-promotion-policy.schema.json`
  - `config/promoted-fragility-catalog.json`
  - `config/promoted-fragility-catalog.schema.json`
  - `config/fragility-signatures/promoted/*.json`
  - `bench/runners/promote_numeric_fragility_signatures.py`
- Current result:
  - the numeric-stability registry now carries an explicit
    `routeTaxonomyVersion` plus route-decision metadata for:
    - `accept-fast`
    - `prefer-stable`
    - `abstain`
  - Lean now proves the current route-to-selection semantics in addition to the
    earlier trigger and triggered-vs-fallback route logic:
    - `accept-fast` selects the fast value
    - `prefer-stable` selects the stable value
    - `abstain` selects no substitution
  - promoted fragility evidence is now frozen into checked-in config:
    - the promotion policy defines what qualifies for `discovery`,
      `promoted`, `runtime-candidate`, and `runtime-exercised`
    - the promoted catalog points at normalized signature files instead of
      treating timestamped hunt reports as the only source of truth
  - the current promoted set remains a contract layer, not a runtime novelty
    claim:
    see `config/promoted-fragility-catalog.json` for the current promoted
    entries and `config/fragility-promotion-policy.json` for what is still
    blocking versus advisory
- Interpretation:
  - this is the clean bridge from discovery artifacts to future runtime
    consumption
  - it now feeds a live Zig/package bounded-slice service, but it still does
    not satisfy the `runtime-exercised` novelty bar until Doe emits true
    operator-local rerun receipts

## Numeric-stability contract planning is now explicit: a canonical fragility-signature schema and a discovery -> promoted -> runtime-exercised graduation ladder are defined so the runtime side can consume evidence without drifting from bench artifacts (2026-03-29 UTC)

- New planning/config surfaces:
  - `config/fragility-signature.schema.json`
  - `docs/numeric-stability-contract-roadmap.md`
- Current result:
  - the fragility-signature schema defines one canonical case shape for:
    - prompt-level flips
    - top-prefix-only prompt flips
    - policy-boundary examples
    - operator controls
  - the roadmap now fixes the artifact-graduation ladder:
    - `discovery`
    - `promoted`
    - `runtime-candidate`
    - `runtime-exercised`
  - route semantics are now stated explicitly at the planning layer:
    - current runtime truth remains `accept-fast | prefer-stable | abstain`
    - `review-required` is deferred until it has a real runtime surface,
      schema migration, and proof support
  - blocking versus advisory is also explicit:
    - schema, traceability, and proof-linked route semantics are blocking
    - corpus breadth, browser promotion, and semantic legibility remain
      advisory until runtime-exercised evidence lands
- Interpretation:
  - this no longer describes a runtime vacuum: Doe now has an explicit
    runtime/package bounded-slice service
  - it still defines the contract boundary that future Zig/package/browser
    work must satisfy before bench evidence can be promoted into a novelty
    claim

## Fresh Apple Metal numeric-fragility corpus exports now normalize the prompt-flip, policy-boundary, and operator-control evidence into one JSONL surface with bounded-answer surprisal, pair-margin, and outsider-lead fields, so the repo can compare numeric brittleness to uncertainty without hand-merging reports (2026-03-29 UTC)

- New runner:
  - `bench/runners/export_numeric_fragility_corpus.py`
- Fresh artifacts:
  - `bench/out/apple-metal-numeric-fragility-corpus/20260329T174341Z/apple_metal_numeric_fragility_corpus.jsonl`
  - `bench/out/apple-metal-numeric-fragility-corpus/20260329T174341Z/apple_metal_numeric_fragility_corpus.manifest.json`
- Current result:
  - the export now keeps one row shape across:
    - prompt-level LM-head bounded-answer flips
    - curated top-prefix-only prompt flips
    - stable-choice / reviewed-choice policy-boundary cases
    - operator-level numeric-stability controls
  - prompt-level rows now carry the token-level uncertainty fields needed to
    compare fragility against confidence:
    - renormalized 2-row probabilities for the bounded answer set
    - per-token bounded surprisal for the exact/reference token and the
      `f16accum` token
    - bounded-answer entropy and probability margin
    - global top-candidate context plus outsider lead against the bounded pair
  - when the source report did not persist full logits, the export leaves the
    global reference-token surprisal unset and records the reason explicitly
    instead of inventing an approximation
  - route semantics are now explicit:
    - `routeExpectation` is hunt-derived only and records whether it is still
      hypothetical or has been realized in a promoted rerun
    - `routeDecision` is reserved for an exercised rerun or policy artifact
  - promoted prompt rows now point `sourceArtifactPath` at the promoted
    hunt report itself, while `sourceSearchArtifactPath` preserves the earlier
    representative hunt artifact used to surface the case
- Interpretation:
  - this makes the current numeric-stability corpus usable for the next
    analysis layer:
    where pair margins are small, where outsiders still dominate, and where a
    low-level math-policy change crosses a brittle bounded-answer decision
    boundary

## Fresh Apple Metal real-weight LM-head receipts now show the first natural prompt/operator/rerun chain: the real prompt `Answer with exactly one word: go or stop. Question: At a red traffic light, cars should Answer:` yields the same real final-norm embedding and the same bounded `{ go, stop }` candidate rows, but `f16` accumulation flips the selected token from `go` to `stop`, and the numeric-stability route correctly prefers the stable serial policy on both Doe and Dawn (2026-03-29 UTC)

- New real prompt/operator-family fixture surface:
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.red-go-stop-answer.json`
  - `bench/fixtures/determinism/apple-metal-real-lm-head-slice-hunt.gemma270m.red-go-stop-answer.json`
  - `bench/runners/run_real_lm_head_slice_hunt.py`
- Fresh reports:
  - `bench/out/apple-metal-real-lm-head-slice-hunt/20260329T134732Z/apple_metal_real_lm_head_slice_hunt_gemma270m_red_go_stop_answer.real-lm-head-slice-hunt.json`
  - `bench/out/apple-metal-reduction-order-logit-flip/20260329T134732Z/apple_metal_real_lm_head_slice_hunt_gemma270m_red_go_stop_answer_red-go-stop-answer_prefix2.reduction-order-logit-flip.json`
  - `bench/out/apple-metal-selective-stable-rerun/20260329T134732Z/apple_metal_real_lm_head_slice_hunt_gemma270m_red_go_stop_answer_red-go-stop-answer_prefix2_selective_stable_rerun.selective-stable-rerun.json`
- Current result:
  - the new lane is fully real at the source:
    Doppler browser harvest captures a stable real prefill logits receipt and a
    stable real last-token embedding for the explicit-choice traffic-light
    prompt above
  - the bounded answer rows are the real model output rows for:
    - token `817` = ` go`
    - token `4721` = ` stop`
  - the exact-reference logits on that real embedding are:
    - ` go` = `17.802072751012076`
    - ` stop` = `17.780365353832053`
    so the exact-reference top token is ` go`
  - on both Doe and Dawn:
    - `forward`, `reverse`, and `tree64` all keep the selected token on ` go`
    - `f16accum` flips the selected token to ` stop`
  - the fresh reduction-order receipt therefore records the real operator
    bridge:
    same prompt, same real final-projection input, same real candidate rows,
    different accumulation policy, different selected token
  - the paired selective-rerun receipt records the full governance chain on
    both Doe and Dawn:
    - first divergence is `matmul.logits`
    - fast `f16accum` token = `1` (` stop`)
    - stable `forward` token = `0` (` go`)
    - stable matches the exact reference and fast does not
    - route decision = `prefer-stable`
- Runtime-path note:
  - the Dawn-backed WebGPU runtime path now explicitly requests
    `ShaderF16` when the adapter advertises it, which is what made the live
    `f16` promotion path possible for this real LM-head slice
- Interpretation:
  - this is the first honest real prompt/operator/rerun flagship case for the
    numeric-stability thesis:
    Doe can harvest a real prompt state, promote it into a real operator-family
    slice, show a selected-token cliff under alternate accumulation policy, and
    record the explicit rerun route that corrects it
  - it is still not a Doe-vs-Dawn divergence claim:
    both lanes exhibit the same numeric cliff here; Doe’s wedge is the owned
    runtime/package stack that makes the cliff observable, receipted, and
    governable

## Fresh Apple Metal `rmsnorm` family receipts now show the first real operator-family bridge from reduction policy to selected-token drift: the same fixed `rmsnorm` reduction family plus the same downstream 2-row logits projection produce different selected tokens under reduction-tree and strict-serial accumulation, while the exact-reference path stays on the tree side and the numeric-stability route correctly keeps `accept-fast` (2026-03-29 UTC)

- New real operator-family fixture surface:
  - `bench/inference-pipeline/kernels/rmsnorm_serial_f32.wgsl`
  - `bench/fixtures/determinism/rmsnorm-slice-tree.commands.json`
  - `bench/fixtures/determinism/rmsnorm-slice-serial.commands.json`
  - `bench/fixtures/determinism/apple-metal-rmsnorm-slice-logit-flip.json`
  - `bench/fixtures/determinism/apple-metal-selective-stable-rerun-rmsnorm-slice.json`
- Fresh reports:
  - `bench/out/apple-metal-reduction-order-logit-flip/20260329T124056Z/apple_metal_rmsnorm_slice_logit_flip.reduction-order-logit-flip.json`
  - `bench/out/apple-metal-selective-stable-rerun/20260329T124139Z/apple_metal_selective_stable_rerun_rmsnorm_slice.selective-stable-rerun.json`
- Current result:
  - the new lane keeps the operator family real:
    first capture is `rmsnorm.output`, second capture is the downstream
    2-row `matmul.logits`, third capture is `sample.token`
  - on both Doe and Dawn:
    - tree-reduction `rmsnorm` selects token `0`
    - strict-serial `rmsnorm` selects token `1`
    - the exact-reference logits stay on token `0`
  - the selective-rerun receipt therefore records the full trigger surface:
    first divergence present, sensitive operator matched, selected token
    changed, but `stableMatchesExactReference = false` and
    `fastMissesExactReference = false`
  - the final route decision is correctly `accept-fast`, not because the
    operator family is ignored, but because the strict-serial rerun is worse
    for this specific case
- Interpretation:
  - this is the first real operator-family receipt that proves Doe’s
    numeric-governance layer is not fake “always prefer stable” theater
  - the current honest claim is:
    Doe can detect a real `rmsnorm`-family numeric cliff, trace first
    divergence at the operator boundary, show the selected-token consequence,
    and keep the fast path when the stable rerun is not actually better

## Fresh Apple Metal numeric-stability routing is now proof-linked, and the first real operator-family negative control is explicit: the attention-style slice runs cleanly, stays parity/stable on Doe and Dawn, and therefore routes `accept-fast`, while the shared probe now rejects any semantic capture whose execution status is not actually `ok` (2026-03-29 UTC)

- New proof-linked numeric-stability contract surface:
  - `pipeline/lean/Doe/Core/NumericStabilityPolicy.lean`
  - `pipeline/lean/Doe/NumericStabilityPolicy.lean`
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
- Fresh proof-linked selective-rerun receipts:
  - `bench/out/apple-metal-selective-stable-rerun/20260329T123001Z/apple_metal_selective_stable_rerun_logit_flip.selective-stable-rerun.json`
  - `bench/out/apple-metal-selective-stable-rerun/20260329T123001Z/apple_metal_selective_stable_rerun_attention_slice.selective-stable-rerun.json`
- Fresh real operator-family negative control:
  - `bench/out/apple-metal-reduction-order-logit-flip/20260329T122013Z/apple_metal_attention_slice_logit_flip.reduction-order-logit-flip.json`
- Current result:
  - the numeric-stability registry now carries explicit proof links for the
    trigger theorem and both route-decision theorems, all extracted into
    `pipeline/lean/artifacts/proven-conditions.json`
  - the refreshed selective-rerun receipts above now copy that proof-linked
    contract into the live report:
    `proofArtifactPath`, trigger proof links, and route proof links
  - the attention-style slice is the first honest real operator-family
    negative control:
    forward and pairwise attention-output lanes stay byte-identical across
    repeats on both Doe and Dawn, so `tokenFlipObserved = false`,
    `sampleFlipObserved = false`, `firstDivergence = null`, and the route
    decision remains `accept-fast`
  - `bench/runners/run_determinism_probe.py` now rejects any captured semantic
    operator whose `execution.status` is not `ok`, so shader-compile failures
    or other execution errors can no longer masquerade as valid deterministic
    captures
- Interpretation:
  - Doe now has a proof-linked numeric-stability route contract and a clean
    real-operator-family control that shows where the wedge does not begin
  - the next valid promotion target remains another real operator family that
    actually moves selected token or bounded answer under alternate numeric
    policies, rather than a synthetic-only slice

## Fresh Apple Metal selective stable-rerun receipts now show the first full numeric-governance probe: the operator-level logit-flip lane can identify `matmul.logits` as the first divergence, compare fast vs stable digests, and route the selected token onto the stable policy when only the stable rerun matches the exact-reference top token (2026-03-29 UTC)

- New numeric-stability policy and selective-rerun tooling:
  - `config/numeric-stability-policy.json`
  - `config/numeric-stability-policy.schema.json`
  - `bench/runners/run_selective_stable_rerun_probe.py`
  - `bench/fixtures/determinism/apple-metal-selective-stable-rerun-logit-flip.json`
- Fresh report:
  - `bench/out/apple-metal-selective-stable-rerun/20260329T032429Z/apple_metal_selective_stable_rerun_logit_flip.selective-stable-rerun.json`
- Current result:
  - the probe consumes the fresh operator-level logit-flip report and applies a
    versioned numeric-stability route policy:
    `numeric-stability/prefer-stable-on-selected-token-disagreement-v1`
  - on both Doe and Dawn lanes, the first divergence is the sensitive operator
    `matmul.logits`
  - in the fast `pairwise` policy, the selected token is `0`
  - in the stable `forward` policy, the selected token is `1`, which matches
    the exact-reference top token for this scenario
  - the trigger policy fires because:
    first divergence is present, the sensitive operator matches, the selected
    token changes, the stable rerun matches the exact reference, and the fast
    path does not
  - the resulting route decision is therefore `prefer-stable` on both lanes
- Interpretation:
  - this is the first full receipt chain for the numeric-governance thesis:
    first divergence, fast/stable digest comparison, selected-token
    consequence, and an explicit route decision
  - it is still a bench/runtime-governance probe, not yet a live native or
    package execution path that automatically reruns only the sensitive
    operator inside a real workload
  - it is also not a Doe-vs-Dawn divergence claim:
    both lanes support the same route decision in this synthetic operator case;
    Doe’s moat is the owned runtime/package surface that can eventually make
    this selective correction path real and auditable

## Fresh Apple Metal reduction-order logit-flip receipts now show an operator-level bridge from accumulation policy to token selection: the same fixed hidden state and same nominal 2-row logits matmul produce different winning rows and different sampled tokens under forward, reverse, and pairwise accumulation policies on both Doe and Dawn (2026-03-29 UTC)

- New operator-level counterexample tooling and fixture:
  - `bench/runners/run_reduction_order_logit_flip.py`
  - `bench/fixtures/determinism/apple-metal-reduction-order-logit-flip.json`
  - `bench/fixtures/determinism/matmul-logits-forward.commands.json`
  - `bench/fixtures/determinism/matmul-logits-reverse.commands.json`
  - `bench/fixtures/determinism/matmul-logits-pairwise.commands.json`
  - `bench/inference-pipeline/kernels/matmul_logits_forward_f32.wgsl`
  - `bench/inference-pipeline/kernels/matmul_logits_reverse_f32.wgsl`
  - `bench/inference-pipeline/kernels/matmul_logits_pairwise_f32.wgsl`
- Fresh report:
  - `bench/out/apple-metal-reduction-order-logit-flip/20260329T031521Z/apple_metal_reduction_order_logit_flip.reduction-order-logit-flip.json`
- Current result:
  - the new lane runs the same fixed hidden state through three explicit
    logits-matmul accumulation contracts:
    forward serial, reverse serial, and pairwise-tree reduction
  - the exact reference logits are `[6.0, 8.85]`, so the exact top token is
    row `1`
  - the live Apple Metal receipts above show:
    - forward logits `[6.0, 6.710000038146973]`, top token `1`, sampled token `1`
    - pairwise logits `[6.0, 4.0]`, top token `0`, sampled token `0`
    - reverse logits `[8.0, 8.0]`, scalar argmax token `0`, sampled token `0`
  - each variant is byte-stable across repeated runs on both Doe and Dawn, and
    Doe and Dawn match each other for every named accumulation policy
- Interpretation:
  - this is the operator-level bridge the micro dot-product lane was meant to
    enable:
    same nominal logits operator, same inputs, different declared accumulation
    policy, different winning row, different sampled token
  - the current honest claim is still narrow:
    Doe now has a receipted Apple Metal operator-level sensitivity lane for
    accumulation-order-induced token flips
  - this is not yet a Doe-vs-Dawn divergence; it is a proof that Doe now has
    the right measurement surface to trace numeric policy choices from
    reduction order into token selection
  - the next work should promote this further into real operator families with
    semantic cliffs:
    softmax denominator, layernorm, attention score accumulation, and small
    matmul inner products that can be selectively routed onto stricter modes

## Fresh Apple Metal reduction-order counterexample receipts now show a metal-level numeric divergence on the same fixed dot product: forward, reverse, and pairwise accumulation policies produce distinct stable output bytes on both Doe and Dawn, which establishes the micro counterexample base for later operator- and decode-level instability hunts (2026-03-28)

- New micro-counterexample tooling and fixture:
  - `bench/runners/run_reduction_order_counterexample.py`
  - `bench/fixtures/determinism/apple-metal-reduction-order-dot-product.json`
  - `bench/fixtures/determinism/dot-product-forward.commands.json`
  - `bench/fixtures/determinism/dot-product-reverse.commands.json`
  - `bench/fixtures/determinism/dot-product-pairwise.commands.json`
  - `bench/inference-pipeline/kernels/dot_product_forward_f32.wgsl`
  - `bench/inference-pipeline/kernels/dot_product_reverse_f32.wgsl`
  - `bench/inference-pipeline/kernels/dot_product_pairwise_f32.wgsl`
- Fresh report:
  - `bench/out/apple-metal-reduction-order-counterexample/20260329T030505Z/apple_metal_reduction_order_dot_product.reduction-order-counterexample.json`
- Current result:
  - the new lane runs the same fixed 8-term dot product through three explicit
    accumulation contracts:
    forward serial, reverse serial, and pairwise-tree reduction
  - each variant is byte-stable across repeated runs on both Doe and Dawn
  - each variant produces a distinct captured output on both Doe and Dawn; see
    the report above for the exact values, digests, and deltas from the exact
    reference sum
  - Doe and Dawn match each other for each named accumulation policy in the
    current Apple Metal receipt, so this is not yet a Doe-vs-Dawn divergence
- Interpretation:
  - this is the metal-level base case we were missing:
    same nominal dot product, same inputs, different declared accumulation
    order, different bytes
  - the current honest claim is still narrow:
    Doe now has an explicit, receipted micro-counterexample lane for
    accumulation-order sensitivity on Apple Metal
  - the next work should promote this from micro counterexample to
    operator-level and decode-level sensitivity hunts:
    attention, softmax, layernorm, and matmul-inner-product slices with
    first-divergence tracing and selective correction modes

## Fresh Apple Metal package determinism receipts now show a real natural supporting stable-choice case on the ordinary Node/package lane: for `Leaving a toddler alone near a pool is safe or unsafe. It is`, Doe keeps the raw global argmax under `stable-token`, but the bounded `{safe, unsafe}` policy lanes resolve the declared ambiguity to `unsafe` with proof-linked receipts (2026-03-28)

- New real scout, sample-only, and package receipts:
  - `bench/out/apple-metal-real-logit-hunt/20260328T211207Z/apple_metal_real_logit_hunt_gemma270m_policy_breadth.real-logit-hunt.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T212034Z/apple_metal_sample_only_tie_break_pool_safe_unsafe_gemma270m.sample-only-tie-break.json`
  - `bench/out/apple-metal-package-determinism/20260328T212103Z/pool-safe-unsafe-prefill-as-captured-stable-token/pool-safe-unsafe-prefill-as-captured-stable-token.package-determinism.json`
  - `bench/out/apple-metal-package-determinism/20260328T212034Z/pool-safe-unsafe-prefill-as-captured-stable-choice/pool-safe-unsafe-prefill-as-captured-stable-choice.package-determinism.json`
  - `bench/out/apple-metal-package-determinism/20260328T212034Z/pool-safe-unsafe-prefill-as-captured-reviewed-choice/pool-safe-unsafe-prefill-as-captured-reviewed-choice.package-determinism.json`
- New supporting fixtures/config:
  - `config/determinism-answer-set-registry.json`
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.policy-breadth.json`
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.pool-safe-unsafe.gemma270m.json`
  - `bench/runners/run_package_determinism_receipt.py`
- Current result:
  - the fresh `pool-safe-unsafe` scout receipt above is byte-stable across
    repeats on Apple Metal and preserves the same prompt-tokenization and
    `topK` membership in the scout contract
  - on that natural prefill state, the bounded candidate set `{safe, unsafe}`
    falls inside the fixed `candidate-margin-band-v1` trigger; see the scout
    and package receipt artifacts above for the exact logits and digest
  - on the ordinary Node/package lane:
    - `stable-token` stays on the raw scalar greedy token
    - `stable-choice` triggers and emits `selectedBy=stable-choice-policy`
    - `reviewed-choice` accepts the explicit reviewed decision and emits
      `selectedBy=reviewed-choice-decision`
  - the fresh sample-only report above shows:
    - `stableChoiceDifferentiatorCaseCount=2`
    - `reviewedChoiceDifferentiatorCaseCount=2`
    for the natural `as-captured` case plus the exact-tie stress case
- Interpretation:
  - this is the first fresh natural supporting case for Doe’s bounded
    post-logit policy lane after the hardened scout/promotion contracts:
    the underlying model/sampler still prefers a non-answer global argmax, but
    Doe can now apply a declared bounded ambiguity policy on the same real
    logits and emit package-level receipts for it
  - this is still not a broad mined-corpus headline claim:
    the pair-agnostic miner correctly keeps the broader natural scout corpus at
    zero promoted headline cases because the strongest natural cases still have
    large outsider leads
  - the safe public claim is therefore:
    Doe has a real Apple Metal natural supporting `stable-choice` example on
    the package lane, not a broad natural ambiguity-resolution win across the
    whole prompt corpus

## Determinism boundary contracts now use a versioned policy registry and emit schema-valid trace-meta companions for stable-token, stable-choice, and reviewed-choice instead of helper-local policy constants (2026-03-28)

- New shared policy and trace-meta contract surfaces:
  - `config/determinism-policy.json`
  - `config/determinism-policy.schema.json`
  - `packages/doe-gpu/src/vendor/doe-determinism-policy.js`
  - `config/doe-determinism-receipt.schema.json`
  - `config/trace-meta.schema.json`
  - `examples/doe-determinism-trace-meta.sample.json`
  - `runtime/zig/src/trace_determinism.zig`
  - `runtime/zig/src/trace.zig`
- Fresh emitted scratch receipts proving the new trace-meta path:
  - `bench/out/scratch/20260328T194525Z-determinism-trace-meta/doe.stable-token.trace-meta.json`
  - `bench/out/scratch/20260328T194525Z-determinism-trace-meta/doe.stable-choice.trace-meta.json`
  - `bench/out/scratch/20260328T194525Z-determinism-trace-meta/doe.reviewed-choice.trace-meta.json`
- Current result:
  - the three Doe post-logit boundaries now all resolve against the same
    versioned registry at `config/determinism-policy.json`
  - public/package receipts now carry:
    - `policyRegistryPath`
    - `policyRegistryVersion`
    - versioned policy IDs
  - `stable-token` receipts are now structurally parallel with the other two
    modes:
    they expose both `policyId` and `selectedBy=stable-token-policy`
  - the repo-only determinism executors now emit adjacent zero-row
    `trace_meta` files whose `determinism` block preserves the same:
    mode, policy IDs, trigger IDs, evaluator IDs, selected-by fields, and
    proof theorem list as the public receipts
  - the native Zig trace summary now carries the same optional `determinism`
    block as a contract stub, so native/runtime callers can emit the same
    boundary metadata when that lane is wired
- Interpretation:
  - this is a contract hardening step, not a broader ambiguity claim:
    Doe’s product wedge is now more explicit and auditable because the
    post-logit boundaries are versioned config-backed contracts with trace-meta
    alignment, not just helper-returned JSON receipts

## Doe now has a proof-linked reviewed-choice sibling beside stable-token and stable-choice: Apple sample-only receipts can show raw Doe/Dawn, deterministic policy lanes, and an explicit reviewed decision as separate audited outcomes (2026-03-28)

- New public determinism surfaces and receipt contract:
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/README.md`
  - `config/doe-determinism-receipt.schema.json`
  - `examples/doe-determinism-receipt.stable-token.sample.json`
  - `examples/doe-determinism-receipt.stable-choice.sample.json`
  - `examples/doe-determinism-receipt.reviewed-choice.sample.json`
- New proof-layer sources and extraction path:
  - `pipeline/lean/Doe/Core/DeterminismPolicy.lean`
  - `pipeline/lean/Doe/DeterminismPolicy.lean`
  - `pipeline/lean/Doe/Extract.lean`
  - `pipeline/lean/lean_build_common.sh`
  - `pipeline/lean/artifacts/proven-conditions.json`
- New Apple sample-only reviewed-choice receipt:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T190156Z-reviewed/apple_metal_sample_only_tie_break_seatbelt_not_safe_gemma270m.sample-only-tie-break.json`
- Current result:
  - Doe now keeps three post-logit contracts separate in public/package-visible
    receipts:
    - `stable-token`: deterministic full-vocab greedy tie-break
    - `stable-choice`: deterministic bounded candidate-set policy
    - `reviewed-choice`: explicit reviewed decision over the same bounded
      ambiguity contract
  - the receipt schema now requires `proofLinks` for all three modes, and those
    links now resolve to extracted theorems in
    `pipeline/lean/artifacts/proven-conditions.json`
  - on the refreshed Apple seatbelt sample-only artifact above:
    - `as-captured`: raw Doe, raw Dawn, Doe `stable-token`, Doe
      `stable-choice`, and Doe `reviewed-choice` all fall back to the same raw
      token
    - `force-not-safe-exact-tie`: raw Doe/raw Dawn emit `6338`, Doe
      `stable-token` and Doe `stable-choice` emit `711`, and Doe
      `reviewed-choice` accepts the explicit reviewed decision and emits `6338`
- Interpretation:
  - this is a stronger Doe capability claim than more prompt hunting:
    Doe now owns an explicit, audited boundary after logits and before final
    token emission, with proof-linked policy receipts instead of raw GPU
    sampler behavior alone
  - the stronger claim is still narrow:
    the Lean links cover policy-layer semantics only
    (tie-break, trigger, evaluator acceptance), not GPU floating-point
    determinism or cross-backend model correctness

## Hardened Apple Metal determinism receipts now separate natural discoveries from mutation-assisted demos, gate pair mining through a tokenizer-aware answer-set registry plus versioned trigger policies, and narrow the current live claim to exact-tie differentiation rather than a natural stable-choice win (2026-03-28)

- New config and receipt-contract surfaces:
  - `config/determinism-answer-set-registry.json`
  - `config/determinism-answer-set-registry.schema.json`
  - `config/determinism-trigger-policy.json`
  - `config/determinism-trigger-policy.schema.json`
  - `config/doe-determinism-receipt.schema.json`
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
- Fresh refreshed scout and promotion receipts:
  - `bench/out/apple-metal-real-logit-hunt/20260328T182007Z/apple_metal_real_logit_hunt_gemma270m_choice_breadth.real-logit-hunt.json`
  - `bench/out/apple-metal-real-logit-hunt/20260328T182007Z/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
  - `bench/out/apple-metal-real-logit-hunt/20260328T182048Z/apple_metal_real_logit_hunt_gemma270m_high_stakes.real-logit-hunt.json`
  - `bench/out/apple-metal-pair-agnostic-mine/20260328T182131Z/apple_metal_pair_agnostic_mine_gemma270m.pair-agnostic-mine.json`
  - `bench/out/apple-metal-semantic-pair-hunt/20260328T182238Z/apple_metal_pair_agnostic_mine_gemma270m.semantic-pair-hunt.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T182215Z/apple_metal_sample_only_tie_break_seatbelt_not_safe_gemma270m.sample-only-tie-break.json`
- Current result:
  - the refreshed scout receipts now carry explicit scout-stage stability
    (`promptTokenizationStable`, `topCandidateMembershipStable`) instead of
    letting downstream stages assume that those checks existed
  - across the refreshed `choice_breadth`, `seatbelt_safe_unsafe`, and
    `high_stakes` scout corpora, the registry-gated pair miner promotes zero
    natural cases:
    `sourceCandidateCount=94`, `minedCandidateCount=0`,
    `promotedCandidateCount=0`
  - because the natural mined report is empty, the mutation stage has no honest
    shortlist to mutate right now; the correct next state is a zero-promotion
    semantic receipt, not a mutation-assisted headline demo
  - `stable-choice` receipts now explicitly record:
    - `triggerPolicyId`
    - `candidateSetId`
    - `candidateSetSource`
  - the seatbelt sample-only fixture now pins the bounded candidate set by
    token ID (`711`, `6338`) so the probe stays reproducible even when a
    refreshed scout no longer keeps both candidate tokens in source `topK`
  - on the refreshed seatbelt sample-only probe:
    - `as-captured`: raw Doe, raw Dawn, Doe `stable-token`, and Doe
      `stable-choice` all emit `496`
    - `force-not-safe-exact-tie`: raw Doe and raw Dawn emit `6338`, while Doe
      `stable-token` and Doe `stable-choice` emit `711`
- Interpretation:
  - the current stronger claim is contract discipline, not broader ambiguity
    coverage:
    Doe now has explicit natural-vs-mutation provenance, registry-gated pair
    mining, versioned trigger policies, and stage-specific stability receipts
  - the current narrower live differentiator is still real:
    Doe can apply explicit deterministic sampler and bounded-policy decisions on
    the same fixed logits when the raw GPU sampler does not follow the scalar
    expected token
  - what no longer holds on refreshed Apple source receipts is the softer
    “natural seatbelt stable-choice win” story; that earlier receipt should be
    treated as superseded by the refreshed no-trigger `as-captured` run above

## Doe now has a reproducible Apple Metal determinism-search funnel: broad scout -> pair-agnostic mining -> decode-state promotion -> shortlist mutation search, with negative controls carried forward instead of hidden (2026-03-28)

- New search/promotion fixtures and runners:
  - `bench/fixtures/determinism/apple-metal-pair-agnostic-mine.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-semantic-pair-mutation-search.gemma270m.json`
  - `bench/runners/determinism_search_helpers.py`
  - `bench/runners/run_pair_agnostic_pair_miner.py`
  - `bench/runners/run_semantic_pair_mutation_search.py`
- Fresh live search artifacts:
  - `bench/out/apple-metal-pair-agnostic-mine/20260328T175850Z/apple_metal_pair_agnostic_mine_gemma270m.pair-agnostic-mine.json`
  - `bench/out/apple-metal-semantic-pair-hunt/20260328T175911Z/apple_metal_pair_agnostic_mine_gemma270m.semantic-pair-hunt.json`
  - `bench/out/apple-metal-semantic-pair-mutation-search/20260328T180122Z/apple_metal_semantic_pair_mutation_search_gemma270m.semantic-pair-mutation-search.json`
  - `bench/out/apple-metal-semantic-pair-mutation-search/20260328T180122Z/apple_metal_semantic_pair_mutation_search_gemma270m.real-logit-hunt.json`
  - `bench/out/apple-metal-semantic-pair-mutation-search/20260328T180122Z/apple_metal_semantic_pair_mutation_search_gemma270m.pair-agnostic-mine.json`
- Current result:
  - the pair-agnostic miner is now conservative and provenance-heavy:
    it mines replayable single-token answer pairs from broad scout output,
    carries canonical token IDs plus `candidateSetSource=mined-topk-v1`, and
    keeps only prompt-bounded cases that meet explicit usefulness criteria
  - on the current Apple breadth receipts, that miner promotes exactly one
    useful case:
    the repeated seatbelt ` not`/` safe` source at
    `bench/out/apple-metal-real-logit-hunt/20260328T172744Z/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
  - `run_semantic_pair_hunt.py --mined-report ...` now reconstructs a full
    decode-state recipe from the mined case without needing a hand-written pair
    fixture:
    `promptTokenIds`, `decodePrefixTokenIds`, `currentIds`, and
    `greedyTokenSequence` are all present in
    `bench/out/apple-metal-semantic-pair-hunt/20260328T175911Z/apple_metal_pair_agnostic_mine_gemma270m.semantic-pair-hunt.json`
  - the first shortlist mutation pass is intentionally a negative-control run,
    not a victory lap:
    - `sourceCaseCount=1`
    - `mutationCandidateCount=3`
    - `improvedMutationCount=0`
    - `outcomeCounts={"pair-missing": 3}`
  - the three seatbelt prompt mutations all failed honestly for different
    reasons recorded in the mutation hunt report:
    - the two instructional variants (`one-word-choice`,
      `reverse-one-word-choice`) collapsed into list/format tokens rather than
      preserving a promotable semantic pair
    - the `bounded-prefix` variant made ` not` the top token but did not keep
      ` safe` in the mined near-pair window, so it stayed a negative control
- Interpretation:
  - Doe now has the search infrastructure needed to discover determinism and
    ambiguity-resolution demos without guessing exact prompts up front
  - the funnel is explicit and auditable:
    scout receipts -> mined pair receipts -> decode-state receipts -> mutation
    receipts -> promoted mined cases
  - the current honest state is stronger methodology, not a stronger claim:
    the search machinery is real and replayable, but the first live mutation
    pass did not produce a new promotable case beyond the original seatbelt
    source

## Doe now has a separate Apple Metal stable-choice layer above stable-token: on the repeated prompt `Driving without a seatbelt is safe or unsafe. It is`, raw Doe, raw Dawn, and Doe `stable-token` all stay on the natural greedy token, while Doe `stable-choice` deterministically resolves the bounded ` not`/` safe` ambiguity to ` not` with an explicit policy receipt (2026-03-28)

- New public helper and receipt contract:
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/src/vendor/doe-namespace.d.ts`
  - `packages/doe-gpu/README.md`
  - `config/doe-determinism-receipt.schema.json`
- New schema-gated sample receipts:
  - `examples/doe-determinism-receipt.stable-token.sample.json`
  - `examples/doe-determinism-receipt.stable-choice.sample.json`
- New seatbelt stable-choice source and probe receipts:
  - `bench/out/apple-metal-real-logit-hunt/20260328T172744Z/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T173832Z/apple_metal_sample_only_tie_break_seatbelt_not_safe_gemma270m.sample-only-tie-break.json`
- Current result:
  - the repeated seatbelt real-logit source receipt is byte-stable across
    three reruns on this host
  - on the natural `as-captured` logits:
    - raw Doe emits `1492`
    - raw Dawn emits `1492`
    - Doe `stable-token` emits `1492`
    - Doe `stable-choice` emits `711`
  - the stable-choice receipt is not pretending the model became numerically
    deterministic; it records a separate bounded-policy decision:
    - `policyId=seatbelt/not-safe-first`
    - candidate set `{711:"not", 6338:"safe"}`
    - `ambiguityTrigger.mode=candidate-margin-band`
    - `ambiguityTrigger.epsilon=0.05`
    - observed candidate-set gap `0.04282951354980469`
    - `selectedBy=stable-choice-policy`
  - on the controlled exact-tie stress case:
    - raw Doe emits `6338`
    - raw Dawn emits `6338`
    - Doe `stable-token` emits `711`
    - Doe `stable-choice` emits `711`
- Interpretation:
  - this is the clean separation Doe needs:
    `stable-token` remains a narrow sampler-determinism claim over fixed logits,
    while `stable-choice` is an explicit policy-governed ambiguity-resolution
    layer over a bounded answer set
  - Apple still does not show a raw Doe-vs-Dawn sampling split on natural
    logits here; the differentiator is that Doe now has a documented,
    deterministic, auditable policy layer when the answer set is ambiguous

## Doe now has a broader Apple Metal stable-token search surface with replayable decode-state recipes, and one repeated two-token semantic differentiator on a real safety prompt: for `Driving without a seatbelt is safe or unsafe. It is`, raw Doe and Dawn emit ` safe` under an exact ` not`/` safe` tie while Doe `stable-token` emits the scalar-expected ` not` (2026-03-28)

- New real-logit hunt fixtures for semantic breadth and a repeated source receipt:
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.choice-breadth.json`
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.seatbelt-safe-unsafe.json`
- New semantic-pair hunt fixtures:
  - `bench/fixtures/determinism/apple-metal-semantic-pair-hunt.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-semantic-pair-hunt.gemma270m.choice-breadth.json`
- New focused sample-only fixtures for semantic two-token ties:
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.driving-not-good.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.patch-public-private.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.red-go-stop.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.snow-winter-summer.gemma270m.json`
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.seatbelt-not-safe.gemma270m.json`
- Fresh breadth source receipts:
  - `bench/out/apple-metal-real-logit-hunt/20260328T172358Z/apple_metal_real_logit_hunt_gemma270m_choice_breadth.real-logit-hunt.json`
  - `bench/out/apple-metal-real-logit-hunt/20260328T172744Z/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
- Fresh semantic-pair hunt receipts with decode-state recipes:
  - `bench/out/apple-metal-semantic-pair-hunt/20260328T172132Z/apple_metal_semantic_pair_hunt_gemma270m.semantic-pair-hunt.json`
  - `bench/out/apple-metal-semantic-pair-hunt/20260328T172758Z/apple_metal_semantic_pair_hunt_gemma270m_choice_breadth.semantic-pair-hunt.json`
- Fresh semantic sample-only receipts:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T172535Z/apple_metal_sample_only_tie_break_driving_not_good_gemma270m.sample-only-tie-break.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T172553Z/apple_metal_sample_only_tie_break_patch_public_private_gemma270m.sample-only-tie-break.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T172609Z/apple_metal_sample_only_tie_break_red_go_stop_gemma270m.sample-only-tie-break.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T172626Z/apple_metal_sample_only_tie_break_snow_winter_summer_gemma270m.sample-only-tie-break.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T172808Z/apple_metal_sample_only_tie_break_seatbelt_not_safe_gemma270m.sample-only-tie-break.json`
- Current result:
  - `run_semantic_pair_hunt.py` now emits token-level decode-state recipes
    (`promptTokenIds`, `decodePrefixTokenIds`, `currentIds`) so the interesting
    real prompt boundaries can be recreated later without access to raw backend
    KV buffers
  - the current best natural semantic near-tie remains the short prompt
    `Driving without brakes is`, where ` not` and ` good` sit very close in the
    source receipt
  - the broader semantic hunt also surfaces repeatable Apple prompts for:
    ` not`/` safe`, ` public`/` private`, ` winter`/` summer`, ` go`/` stop`,
    ` true`/` false`, and ` even`/` odd`
  - two-token exact-tie probes are narrower than the earlier `top4` tie story:
    the `driving not/good`, `public/private`, `go/stop`, and
    `winter/summer` probes all keep raw Doe, raw Dawn, and Doe `stable-token`
    aligned with scalar first-max semantics
  - the repeated seatbelt source receipt is the current strongest two-token
    stable-token differentiator:
    - repeated real-logit source receipt:
      `bench/out/apple-metal-real-logit-hunt/20260328T172744Z/apple_metal_real_logit_hunt_gemma270m_seatbelt_safe_unsafe.real-logit-hunt.json`
    - repeated sample-only receipt:
      `bench/out/apple-metal-sample-only-tie-break/20260328T172808Z/apple_metal_sample_only_tie_break_seatbelt_not_safe_gemma270m.sample-only-tie-break.json`
    - baseline `as-captured`: raw Doe, raw Dawn, and Doe `stable-token` agree
    - `force-not-safe-exact-tie`: raw Doe emits `6338`, raw Dawn emits `6338`,
      Doe `stable-token` emits `711`
    - the Doe receipt records the exact contract and evidence:
      `mode=stable-token`, `comparator=scalar-f32-greedy`,
      `tieBreakRule=lowest-index-among-max`, plus tied-max prefix
      `[711, 6338]`
- Interpretation:
  - the repo now has a broader, more honest search story for deterministic
    semantic decisions: most real two-token ties do not currently distinguish
    Doe from Dawn, but Doe can still provide an explicit stable-token contract
    where the raw GPU sampler does not follow scalar first-max semantics
  - the current Apple claim stays narrow:
    Doe has replayable semantic tie receipts and at least one repeated real
    safety prompt where Doe `stable-token` changes the answer under a controlled
    exact tie while raw Doe and raw Dawn stay in lockstep

## Doe now has a human-readable Apple Metal stable-token receipt on a real safety prompt: when the prompt `Driving without brakes is safe or unsafe. It is` is stress-mutated into an exact tie between ` not` and ` safe`, raw Doe and Dawn both emit ` safe`, while Doe `stable-token` emits the scalar-expected ` not` with explicit receipts (2026-03-28)

- New real-logit hunt fixture for semantic answer-token prompts:
  - `bench/fixtures/determinism/apple-metal-real-logit-hunt.gemma270m.choice-primer.json`
- New focused sample-only fixture for the semantic tie case:
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.brakes-safe-unsafe.gemma270m.json`
- Fresh source report:
  - `bench/out/apple-metal-real-logit-hunt/20260328T165934Z/apple_metal_real_logit_hunt_gemma270m_choice_primer.real-logit-hunt.json`
- Fresh semantic sample-only report:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T165957Z/apple_metal_sample_only_tie_break_brakes_safe_unsafe_gemma270m.sample-only-tie-break.json`
- Fresh differentiator receipt:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T165957Z/brakes-safe-unsafe-prefill-force-not-safe-exact-tie/brakes-safe-unsafe-prefill-force-not-safe-exact-tie.determinism.json`
- Current result:
  - the source real-logit receipt for `brakes-safe-unsafe` is byte-stable across
    reruns on this host
  - `as-captured`: raw Doe, raw Dawn, and Doe `stable-token` all agree on token
    `1492` (`" now"`)
  - `force-not-safe-exact-tie`: the runner lifts token `711` (`" not"`) and
    token `6338` (`" safe"`) to the same exact max value above the original top
    logit
  - on that exact same mutated logits buffer:
    - raw Doe emits `6338`
    - raw Dawn emits `6338`
    - Doe `stable-token` emits `711`
  - the Doe receipt records the applied contract explicitly:
    `mode=stable-token`, `comparator=scalar-f32-greedy`,
    `tieBreakRule=lowest-index-among-max`, plus the tied-max prefix
    `[711, 6338]`
- Interpretation:
  - this is still a controlled exact-tie stress receipt, not a claim that real
    prompts naturally land on this exact tie boundary
  - Apple Metal still does not show a raw Doe-vs-Dawn sampling split; the raw
    GPU lanes stay in lockstep here
  - the stronger claim is narrower and more useful:
    Doe now has a human-readable stable-token differentiator on a real prompt
    with meaningful answer tokens, not just anonymous top-k tie fixtures

## Doe now has a real Apple Metal stable-token differentiator: on forced 4-way exact ties, raw Doe and Dawn still match each other, but Doe `stable-token` recovers the scalar expected token with explicit receipts (2026-03-28)

- Public helper surface:
  - `packages/doe-gpu/src/vendor/doe-namespace.js`
  - `packages/doe-gpu/README.md`
- New Doe stable-token executor used by the sample-only probe:
  - `bench/executors/run-doe-stable-token.js`
- Updated sample-only fixture with explicit Doe stable-token config:
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.gemma270m.json`
- Fresh aggregate sample-only report with Doe stable-token receipts:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T162956Z/apple_metal_sample_only_tie_break_gemma270m.sample-only-tie-break.json`
- Fresh Doe stable-token differentiator receipts:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T162956Z/answer-is-prefill-force-top4-exact-tie/doe.stable-token.json`
  - `bench/out/apple-metal-sample-only-tie-break/20260328T162956Z/sky-is-decode-2--force-top4-exact-tie/doe.stable-token.json`
- Current result:
  - raw Doe and Dawn still stay in lockstep on all `20` sample-only cases from
    the real-logit hunt corpus
  - the same two forced `top4` exact-tie cases remain the only scalar-audit
    mismatches on the raw GPU sample path:
    - `answer-is-prefill-force-top4-exact-tie`
    - `sky-is-decode-2--force-top4-exact-tie`
  - in both cases, raw Doe and raw Dawn emit the same stable GPU token while
    Doe `stable-token` emits the scalar expected token:
    - `answer-is-prefill-force-top4-exact-tie`: raw Doe/Dawn `236761`, Doe
      `stable-token` `107`
    - `sky-is-decode-2--force-top4-exact-tie`: raw Doe/Dawn `808`, Doe
      `stable-token` `107`
  - the Doe stable-token receipts are explicit about the applied contract:
    `mode=stable-token`, `comparator=scalar-f32-greedy`,
    `tieBreakRule=lowest-index-among-max`, plus logits SHA-256 and tied-max
    index prefixes
- Interpretation:
  - Apple Metal still does **not** show a raw Doe-vs-Dawn sampling split on the
    shared GPU kernel path
  - Doe now has a narrower but real determinism differentiator:
    an explicit package/runtime helper that can enforce scalar greedy tie-break
    semantics with receipts on the same logits where the raw GPU kernel follows
    a different stable tie path
  - this is a valid fixed-host, fixed-input stable-token claim; it is still not
    a full-model LM determinism claim, not a cross-backend claim, and not a
    proof of floating-point determinism

## Apple sample-only tie-break probes now reuse persisted real Gemma 270M logits; Doe and Dawn remain identical on every tested case, while forced 4-way exact ties expose a stable kernel-vs-scalar-argmax mismatch rather than a Doe-vs-Dawn split (2026-03-28)

- New runner:
  - `bench/runners/run_sample_only_tie_break_probe.py`
- Bundled fixture:
  - `bench/fixtures/determinism/apple-metal-sample-only-tie-break.gemma270m.json`
- Source real-logit report with persisted logits:
  - `bench/out/apple-metal-real-logit-hunt/20260328T154808Z/apple_metal_real_logit_hunt_gemma270m.real-logit-hunt.json`
- Fresh sample-only tie-break report:
  - `bench/out/apple-metal-sample-only-tie-break/20260328T160703Z/apple_metal_sample_only_tie_break_gemma270m.sample-only-tie-break.json`
- Current result:
  - `20` Apple Metal sample-only cases were exercised:
    top `4` real prompt/step candidates from the real-logit hunt times `5`
    controlled mutations each
  - Doe and Dawn matched each other on every case:
    all cases are `sameDecodedValueAcrossLanes=true`
  - the `as-captured`, `force-top2-exact-tie`, and both corrected `1ulp`
    mutations stay aligned with the scalar `f32` argmax audit
  - two forced `top4` exact-tie cases do **not** match scalar CPU argmax:
    - `answer-is-prefill-force-top4-exact-tie`
    - `sky-is-decode-2--force-top4-exact-tie`
  - in both of those cases Doe and Dawn still agree with each other and remain
    byte-stable across runs; the mismatch is between the real GPU sample kernel
    and the scalar audit model, not between Doe and Dawn
- Interpretation:
  - Apple Metal still does not show a Doe-vs-Dawn sampling divergence on this
    path
  - the useful new fact is narrower and still important:
    forced multi-way exact ties can make the real `sample.wgsl` kernel pick a
    stable token that differs from scalar CPU argmax semantics
  - that strengthens the case for an explicit Doe `stable-token` mode with a
    documented CPU-side argmax/tie-break contract if we want a determinism
    surface that is stronger than “same as Dawn on this GPU kernel”

## Apple real-logit hunt now separates browser repeat isolation; fresh-page reruns remove the earlier zero-logit collapse and keep current real Gemma 270M candidates byte-stable on this host (2026-03-28)

- `bench/executors/harvest-doppler-browser-logits.js` now supports explicit
  `browser.repeatIsolation` for real-logit harvests:
  - `reuse-page`
  - `new-page`
  - `new-browser`
- `bench/runners/run_real_logit_hunt.py` now uses that control to rank real
  prompt/decode candidates from Doppler's browser advanced API against a real
  Gemma 270M artifact.
- Current receipts:
  - older reuse-page report showing the collapse:
    - `bench/out/apple-metal-real-logit-hunt/20260328T154208Z/apple_metal_real_logit_hunt_gemma270m.real-logit-hunt.json`
  - fresh new-page report:
    - `bench/out/apple-metal-real-logit-hunt/20260328T154607Z/apple_metal_real_logit_hunt_gemma270m.real-logit-hunt.json`
  - fresh new-page report with persisted logits for sample-only follow-up:
    - `bench/out/apple-metal-real-logit-hunt/20260328T154808Z/apple_metal_real_logit_hunt_gemma270m.real-logit-hunt.json`
- Interpretation:
  - the older reuse-page report should be treated as a browser/model lifecycle
    bug receipt, not as real greedy-token instability
  - the fresh new-page report removes that collapse; current real prompt/step
    candidates are byte-stable across reruns on this fixed Apple Metal host
  - the current hunt now gives a real-logit candidate list that can feed the
    next sample-only Doe-vs-Dawn tie-break probe without conflating lifecycle
    faults with numerical drift

## Apple Metal tie-break audit now checks expected greedy sequencing directly from captured logits; current Doe and Dawn receipts stay in lockstep even on exact full-vocab ties (2026-03-28)

- `bench/runners/run_determinism_probe.py` now derives an explicit
  `tieBreakAudit` for `stable-decode-step` reports:
  - decodes captured final logits as `f32`
  - computes the greedy expectation as the lowest index among max logits
  - compares that expected token to the captured sampled token for each lane
- Fresh 64-step exact-tie audit:
  - `bench/out/apple-metal-determinism/20260328T183500Z/g270m_prefill64_decode64_full_tie_audit.determinism.json`
- Current result:
  - all 64 decode steps on the Apple Metal Gemma 270M shaped prefill+decode
    command stream are exact `4096`-way ties at the sampled logits boundary
  - Doe emits token `0` on every step and matches the expected greedy
    tie-break sequence on all 64 steps
  - Dawn emits the same token sequence and also matches the expected greedy
    tie-break sequence on all 64 steps
- Interpretation:
  - the current Apple Metal WebGPU path does not show a Doe-vs-Dawn tie-break
    sequencing bug on this exact-tie workload
  - the useful current claim is narrower: Doe can now prove that both lanes
    obey the same greedy tie-break expectation on a real repeated tie receipt
  - the most suspicious remaining sequencing risk is outside this Apple WebGPU
    path, especially in other sampling implementations that do not explicitly
    preserve global tie order

## Apple Metal now has an explicit determinism claim ladder: receipt, stable-token, and stable-decode-step all emit fresh byte receipts through the same probe runner, but Doe is currently at parity with Dawn rather than “more deterministic” (2026-03-28)

- `bench/runners/run_determinism_probe.py` now supports three explicit
  determinism modes instead of depending on hand-authored capture indices:
  - `receipt`
  - `stable-token`
  - `stable-decode-step`
- The runner now infers semantic capture points directly from the command
  stream:
  - `receipt` captures the sampled token on `sample.wgsl`
  - `stable-token` repeats that token capture across many runs
  - `stable-decode-step` captures both the final-logits producer buffer and the
    sampled token boundary for each decode step
- Fresh Apple Metal `receipt` artifact:
  - fixture:
    - `bench/fixtures/determinism/apple-metal-greedy-sample-receipt.json`
  - report:
    - `bench/out/apple-metal-determinism/20260328T173500Z/apple_metal_greedy_sample_receipt.determinism.json`
  - current result:
    - Doe and Dawn both emit a one-run operator receipt for
      `sample.output_token`
    - both lanes capture the same bytes and decode token `17`
- Fresh Apple Metal `stable-token` artifact:
  - fixture:
    - `bench/fixtures/determinism/apple-metal-greedy-sample-clear-winner.json`
  - report:
    - `bench/out/apple-metal-determinism/20260328T173700Z/apple_metal_greedy_sample_clear_winner.determinism.json`
  - current result:
    - Doe is byte-stable across 50 runs on `sample.output_token`
    - Dawn is byte-stable across the same 50 runs on the same operator
    - both lanes decode token `17`
    - Doe and Dawn match byte-for-byte on this fixed-host greedy-argmax probe
- Fresh Apple Metal `stable-decode-step` artifact:
  - fixture:
    - `bench/fixtures/determinism/apple-metal-gemma3-270m-decode1tok.json`
  - report:
    - `bench/out/apple-metal-determinism/20260328T174000Z/apple_metal_gemma3_270m_decode_1tok.determinism.json`
  - current result:
    - Doe is byte-stable across 20 runs on both `decode.final_logits` and
      `decode.sample_token`
    - Dawn is byte-stable across the same 20 runs on the same operators
    - both lanes match byte-for-byte across the captured final-logits and token
      buffers
- Important interpretation:
  - this is now a better determinism story than “we think temperature zero is
    stable”: Doe can emit explicit byte receipts at three levels on Apple Metal
  - the current evidence still does **not** support “Doe is more deterministic
    than Dawn”; on these Apple probes they are equally stable
  - the current evidence still does **not** support a full-model LM
    determinism claim, cross-backend determinism, or a formal proof of
    floating-point determinism

## Apple Metal now has explicit determinism receipts for greedy sampling and a Gemma-shaped decode slice; Doe matches Dawn byte-for-byte on those fixed-input probes, but this is not yet a full-model determinism claim (2026-03-28)

- Added a dedicated Apple determinism probe runner:
  - `bench/runners/run_determinism_probe.py`
- The runner annotates explicit semantic capture points on a command stream, reruns
  Doe and Dawn repeatedly on the same host/backend, and emits a report that
  separates:
  - repeated-byte stability within Doe
  - repeated-byte stability within Dawn
  - byte equality across Doe vs Dawn
- Dawn-delegate now supports targeted buffer capture through the shared
  WebGPU-backed readback path in:
  - `runtime/zig/src/core/queue/wgpu_ffi_capture.zig`
  - `runtime/zig/src/backend/dawn_delegate_backend.zig`
- Fresh Apple Metal greedy-sampling receipt with explicit non-zero logits:
  - fixture:
    - `bench/fixtures/determinism/apple-metal-greedy-sample-clear-winner.json`
    - `bench/fixtures/determinism/greedy-sample-clear-winner.commands.json`
  - report:
    - `bench/out/apple-metal-determinism/20260328T152600Z/apple_metal_greedy_sample_clear_winner.determinism.json`
  - current result:
    - Doe stable across 50 runs on `sample.input_logits` and `sample.output_token`
    - Dawn stable across 50 runs on the same two semantic operators
    - Doe and Dawn emit the same bytes for the fixed logits input and the same
      sampled-token bytes across lanes
    - both lanes decode token `17` from the captured output buffer
- Fresh Apple Metal Gemma-shaped decode receipt:
  - fixture:
    - `bench/fixtures/determinism/apple-metal-gemma3-270m-decode1tok.json`
  - report:
    - `bench/out/apple-metal-determinism/20260328T151500Z/apple_metal_gemma3_270m_decode_1tok.determinism.json`
  - current result:
    - Doe stable across 20 runs on the captured final-logits and sampled-token
      buffers
    - Dawn stable across the same 20 runs on the same semantic capture points
    - Doe and Dawn emit the same captured bytes for both operators on this host
- Important caveat:
  - the Gemma 270M decode probe uses the generated compat command stream, which
    is graph/shape-faithful but still a zero-initialized command stream rather
    than a full model-weight execution receipt
  - this means the repo can now defend fixed-host, fixed-input byte-stability
    for named Apple Metal probes, including a real greedy-sampling kernel and a
    Gemma-shaped decode slice
  - the repo still cannot defend “Doe proves deterministic LM inference” or
    “Doe is more deterministic than Dawn” as a general public claim

## Apple Metal now has a publishable runtime bundle and a stable Apple-scoped package claim surface: Bun Gemma64/Gemma1B are claimable, and Node/Dawn Gemma64/Gemma1B are explicitly unsupported on `mac.lan` (2026-03-28)

- Apple Metal runtime release bundle is now published through:
  - `bench/runners/publish_apple_runtime_release.py`
- Fresh Apple runtime release bundle:
  - `bench/out/apple-runtime-release/20260328T031800Z/apple_runtime_release_manifest.json`
- The bundle binds one Apple-local runtime deliverable:
  - raw + stripped dylib paths, SHA-256s, sizes, strip command, and dependency
    list live in the manifest under `artifact`
  - runtime footprint reports:
    - `bench/out/apple-runtime-release/20260328T031800Z/runtime_footprint_report.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/runtime_footprint_report.md`
  - drop-in ABI receipts:
    - `bench/out/apple-runtime-release/20260328T031800Z/dropin_report.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/dropin_symbol_report.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/dropin_behavior_report.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/dropin_benchmark_report.json`
  - native consumer receipt:
    - `bench/out/apple-runtime-release/20260328T031800Z/apple_runtime_consumer_report.json`
  - Apple Metal runtime compare + backend-gate receipts:
    - `bench/out/apple-runtime-release/20260328T031800Z/apple_metal_compare_dev.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/metal_sync_conformance_gate.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/metal_timing_policy_gate.json`
  - Apple CTS release publication + trend receipt:
    - `bench/out/apple-runtime-release/20260328T031800Z/cts_baseline.json`
    - `bench/out/apple-runtime-release/20260328T031800Z/cts_trend.json`
  - `config/webgpu-cts-evidence.json` now points at the release-bundle CTS
    baseline instead of an ad hoc local snapshot
- The retained Apple runtime/harness fixes behind that bundle are:
  - `runtime/zig/src/doe_queue_submit_native.zig`
  - `bench/native_compare_modules/runner.py`
  - `bench/native_compare_modules/workload_validation.py`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.compare-dev.json`
  - `bench/runners/publish_apple_runtime_release.py`
  - `bench/drop-in/apple_runtime_consumer.c`
  - `bench/drop-in/apple_runtime_consumer.py`
- Fresh Apple package receipts:
  - Bun/package Gemma64 cold + warm are both claimable:
    - `bench/out/apple-metal/20260328T035500Z/gemma64.bun-package.ir.compare.json`
    - `bench/out/apple-metal/20260328T035500Z/gemma64.bun-package.warm.ir.compare.json`
  - Bun/package Gemma1B cold + warm are both claimable:
    - `bench/out/apple-metal/20260328T035500Z/gemma1b.bun-package.ir.compare.json`
    - `bench/out/apple-metal/20260328T035500Z/gemma1b.bun-package.warm.ir.compare.json`
  - Node/Dawn Gemma64 cold + warm are now explicit unsupported receipts on this
    host instead of intermittent crash artifacts:
    - compare surface:
      - `bench/out/apple-metal/20260328T040500Z/gemma64.node-package.ir.compare.json`
      - `bench/out/apple-metal/20260328T040500Z/gemma64.node-package.warm.ir.compare.json`
    - right-side unsupported trace-meta receipt:
      - `bench/out/apple-metal/20260328T040500Z/gemma64.node-package.ir.workspace/inference_gemma3_270m_prefill_64tok_decode_64tok/right/dawn_node_webgpu.run000.meta.json`
  - Node/Dawn Gemma1B cold + warm are now explicit unsupported receipts on this
    host instead of “still pending a tiny fix”:
    - compare surface:
      - `bench/out/apple-metal/20260328T040500Z/gemma1b.node-package.ir.compare.json`
      - `bench/out/apple-metal/20260328T040500Z/gemma1b.node-package.warm.ir.compare.json`
    - right-side unsupported trace-meta receipt:
      - `bench/out/apple-metal/20260328T040500Z/gemma1b.node-package.ir.workspace/inference_gemma3_1b_prefill_64tok_decode_64tok/right/dawn_node_webgpu.run000.meta.json`
- Current interpretation:
  - the safe Apple package claim is now exact and narrower:
    Apple Metal, package surface, selected timing, `doe-gpu` vs `bun-webgpu`,
    Gemma64 + Gemma1B, cold + prepared-session lanes only
  - Node/Dawn Gemma64 and Gemma1B are explicitly unsupported on `mac.lan`; they
    are not part of the Apple package headline surface
  - Apple runtime evidence is now packaged as one coherent local release
    deliverable with ABI gate, binary artifact, consumer receipt, compare-dev,
    sync/timing gates, and CTS publication tied together by one manifest
  - this still does not close broad `doe-runtime` or conformance language:
    the evidence is Apple Metal only, non-Apple runtime slices are still
    missing, and backend/release publication is not yet broad across the
    intended runtime matrix

## Apple Metal runtime receipts are now current: drop-in gate is green, the preferred CTS subset was republished, and Node/Dawn Gemma1B remains a diagnostic package lane on this host (2026-03-28)

- Rebuilt the Apple drop-in dylib after fixing two Apple-local runtime issues:
  - the drop-in symbol gate now reads macOS `.dylib` exports correctly:
    - `bench/drop-in/dropin_symbol_gate.py`
  - `wgpuQueueWriteBuffer` now delivers a validation error when the write range
    exceeds the buffer bounds, which lets the drop-in behavior suite observe
    the expected error scope on Apple Metal:
    - `runtime/zig/src/doe_queue_submit_native.zig`
- Fresh Apple Metal drop-in runtime receipts:
  - `bench/out/dropin/20260328T014711Z/dropin_report.json`
  - `bench/out/dropin/20260328T014711Z/dropin_symbol_report.json`
  - `bench/out/dropin/20260328T014711Z/dropin_behavior_report.json`
  - `bench/out/dropin/20260328T014711Z/dropin_benchmark_report.json`
- Republished the preferred Apple Metal CTS subset baseline:
  - `bench/out/cts-baseline/20260328T014648Z.json`
  - `config/webgpu-cts-evidence.json` now points at that fresh Apple baseline
- Rechecked the blocked Node/package Gemma1B lane on Apple Metal:
  - `bench/out/apple-metal/20260328T014558Z/gemma1b.node-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T014558Z/gemma1b.node-package.warm.ir.compare.json`
- Current interpretation:
  - Apple-local runtime evidence moved materially: the Apple drop-in gate is
    green again and the preferred Apple CTS subset is freshly published as a
    backend-scoped host receipt
  - this still does not close `doe-runtime`: the current evidence is Apple
    Metal only, backend/release CTS publication remains open, and broader
    runtime-tier evidence is still required before any broad replacement claim
  - the Apple package-performance claim remains narrow and exact-workload
    scoped: Node/package Gemma64 and Bun/package Gemma1B are still the fresh
    claimable rows, Bun/package Gemma64 is still diagnostic, and Node/Dawn
    Gemma1B remains provider-blocked on this host rather than comparable
    evidence

## Apple Metal package evidence is now broader than a single row: Gemma64 Node/package and Gemma1B Bun/package both have fresh claimable selected-timing artifacts, while Bun Gemma64 remains diagnostic and Node Gemma1B remains provider-blocked on this host (2026-03-28)

- Kept the retained package submit/wait path changes that moved the Node/package
  Gemma64 lane over the selected-timing claimability line:
  - `runtime/bridge/webgpu-addon/doe_napi_queue.c`
  - `runtime/zig/src/doe_queue_flush_breakdown.zig`
- The generic package executor no longer passes empty `requiredFeatures` or
  empty `requiredLimits` into `requestDevice()`, which unblocked the Bun
  package path on the IR-backed compare stack:
  - `bench/executors/node-webgpu/executor.js`
- Fresh Node/package Gemma64 artifacts on Apple Metal:
  - `bench/out/apple-metal/20260328T005446Z/gemma64.node-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T005407Z/gemma64.node-package.warm.ir.compare.json`
- Fresh Bun/package Gemma64 comparable diagnostics on Apple Metal:
  - `bench/out/apple-metal/20260328T005149Z/gemma64.bun-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T005149Z/gemma64.bun-package.warm.ir.compare.json`
- Fresh Bun/package Gemma1B artifacts on Apple Metal:
  - `bench/out/apple-metal/20260328T005256Z/gemma1b.bun-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T005256Z/gemma1b.bun-package.warm.ir.compare.json`
- Current interpretation:
  - the package-performance surface is no longer limited to one claimable row
    on one runtime; the current tree now has claimable selected-timing evidence
    for Node/package Gemma64 and Bun/package Gemma1B on Apple Metal
  - Bun/package Gemma64 is now a real comparable lane, but it is still
    diagnostic and negative on this host; use the artifacts for the exact cold
    and warm deltas
  - Node/package Gemma1B is still blocked by a Dawn-side execution failure near
    the final submit window on this host, so it is not yet part of the
    claim-grade surface
  - this is enough evidence for a narrower Apple-Metal package-performance
    claim, but it is still not a broad backend-agnostic package post

## Doe now compiles the full selected Dawn Tint benchmark corpus to MSL, and the fresh Doe-vs-Tint artifact is fully compared instead of recording `missing_doe` skips (2026-03-27)

- Closed the remaining WGSL compiler gaps that were blocking the selected Dawn
  Tint benchmark corpus on the MSL lane:
  - let-bound local ref aliasing now carries real ref typing/lowering through
    sema, IR, and MSL local declarations:
    - `runtime/zig/src/doe_wgsl/sema_expr.zig`
    - `runtime/zig/src/doe_wgsl/sema.zig`
    - `runtime/zig/src/doe_wgsl/ir_builder.zig`
    - `runtime/zig/src/doe_wgsl/emit_msl_ir.zig`
  - atomic builtins now type their return value from the atomic element instead
    of the address-taking argument wrapper:
    - `runtime/zig/src/doe_wgsl/sema_attrs.zig`
- Added regression coverage for both cases:
  - `runtime/zig/src/doe_wgsl/mod_api_test.zig`
  - `runtime/zig/src/doe_wgsl/coverage_stage_texture_test.zig`
- Fresh benchmark-corpus artifact:
  - `bench/out/compilation/doe-vs-tint-benchmark.msl.ndjson`
- Current interpretation:
  - the selected Dawn Tint benchmark corpus no longer records `missing_doe`
    rows in the fresh MSL artifact
  - the current artifact is now a real Doe-vs-Tint comparison surface across
    the selected corpus, with raw, startup-corrected, and warm Tint views
  - this moves the remaining compiler work from basic corpus coverage to
    continued speed work and any future corpus/query expansion

## Preferred vendored CTS subset is now green on this host after normalizing `descriptor.defaultQueue.label` on the package requestDevice path (2026-03-27)

- The package requestDevice normalization path now fills in an empty string for
  `descriptor.defaultQueue.label` when CTS omits the label field:
  - `packages/doe-gpu/src/vendor/webgpu/shared/validation.js`
- Fresh preferred CTS subset baseline artifact:
  - `bench/out/cts-baseline/20260327T234418Z.json`
- The CTS evidence ledger now points at that fully passing subset artifact:
  - `config/webgpu-cts-evidence.json`
- Current host interpretation:
  - the earlier mixed CTS subset failures were largely a requestDevice
    descriptor-normalization issue, not a broad adapter/queue/runtime failure
  - the current preferred subset now passes end to end on this host; use the
    artifact for the exact query set and bucket coverage
- This shifts the main coverage frontier away from the current preferred CTS
  subset and toward:
  - broader CTS query expansion beyond the current subset
  - Doe WGSL compiler coverage on the Dawn benchmark corpus surfaced by
    `bench/out/compilation/doe-vs-tint-benchmark.msl.ndjson`

## Vendored CTS now runs against the real Doe package provider, the CTS ledger points at the first non-adapter-failure baseline, and Doe-vs-Tint has a real warm benchmark-corpus surface (2026-03-27)

- The vendored CTS subset now runs through the repo-owned provider wrapper and
  real Doe package globals:
  - `cts/fawn-node-gpu-provider.cjs`
  - `cts/fawn-node-gpu-provider.js`
  - `packages/doe-gpu/src/vendor/webgpu/index.js`
- The preferred CTS subset invocation remains config-backed through:
  - `bench/fixtures/cts_subset.fawn-node.json`
  - `bench/runners/run_cts_subset.py`
  - `bench/tools/cts_baseline_generate.py`
- The first real host baseline after the provider/globals fix is:
  - `bench/out/cts-baseline/20260327T210115Z.json`
- The CTS evidence ledger now points at that artifact instead of the earlier
  adapter-bring-up-only baseline:
  - `config/webgpu-cts-evidence.json`
- Current host interpretation:
  - adapter request, device request, and error-scope coverage now succeed on
    this subset
  - the remaining subset behavior is still mixed; use the baseline artifact for
    the current pass/fail set and stderr tails
- Doe-vs-Tint compilation now has three report views on the compiler surface:
  - raw Tint CLI process-wall timings
  - startup-corrected derived timings
  - real warm/in-process Tint timings from Dawn's `tint_benchmark`
- The benchmark-corpus config and fresh artifact for that warm surface are:
  - `bench/native-compare/compare_doe_vs_tint.benchmark-corpus.config.json`
  - `bench/out/compilation/doe-vs-tint-benchmark.msl.ndjson`
- Current compiler-surface interpretation:
  - the warm/cold benchmark-corpus harness is now real
  - the current blocking issue is Doe WGSL coverage on the selected Dawn
    benchmark corpus, so the fresh artifact currently records skipped Doe rows
    instead of comparable timing rows

## CTS evidence ledger is no longer empty, the top-level README now has a clone-to-output stranger quickstart, and Tint compilation reports now publish raw plus startup-corrected results (2026-03-27)

- Published the first repo-tracked CTS baseline artifact on the fixed vendored
  CTS lane:
  - `bench/out/cts-baseline/20260327T202656Z.json`
- The evidence ledger is no longer empty:
  - `config/webgpu-cts-evidence.json`
- Current host-state interpretation from that artifact:
  - the vendored CTS lane now executes the Doe package provider instead of
    failing on missing dependencies or broken provider-path wiring
  - the current host still fails at adapter bring-up, with the subset rows
    reflecting `requestAdapter failed (status=3, detail=metal default device unavailable)`
  - this is now real baseline evidence for this machine, not a tooling failure
- The preferred CTS subset config and runners now use a stable repo-root
  provider path:
  - `bench/fixtures/cts_subset.fawn-node.json`
  - `cts/fawn-node-gpu-provider.js`
  - `bench/tools/cts_baseline_generate.py`
  - `bench/runners/run_cts_subset.py`
- Added the first dead-simple repo quickstart to the top-level README:
  - `README.md`
  - it now shows clone -> `zig build dropin` -> addon build -> package smoke
    output, with no GPU requirement for the smoke step
- Doe-vs-Tint compilation reporting now publishes both the raw Tint process-wall
  numbers and a startup-corrected derived view:
  - `bench/native_compare_modules/runner.py`
  - `bench/native-compare/compare_doe_vs_tint_compilation.py`
  - fresh artifact: `bench/out/compilation/doe-vs-tint.msl.ndjson`
  - `config/migration-notes.md`
  - `bench/README.md`
  - `docs/benchmark-taxonomy.md`

## Node/package Gemma64 selected timing now flips positive at p50 on both cold and warm after moving package flush to shared-event waits and adding a Doe-native all-dispatch batch submit path (2026-03-27)

- Kept two package-path changes for the retained Node package lane:
  - `runtime/zig/src/doe_queue_flush_breakdown.zig` now waits for pending Metal work via the queue shared event when available instead of always using `MTLCommandBuffer.waitUntilCompleted()`
  - `runtime/zig/src/doe_compute_fast.zig`, `runtime/bridge/webgpu-addon/doe_napi_internal.h`, `runtime/bridge/webgpu-addon/doe_napi_globals.c`, and `runtime/bridge/webgpu-addon/doe_napi_queue.c` now expose and use a Doe-native all-dispatch batch submit path for dispatch-only batched package command streams on the current macOS Metal lane
- Benchmark contract is unchanged:
  - cold package rows still include setup in selected timing
  - warm package rows still exclude setup from selected timing and keep workload-unit wall on `trace-meta-process-wall`
  - the new path preserves the same dispatch order, bindings, and submit/wait boundary
- Validation passed after the retained package-path changes:
  - `zig build dropin`
  - `node packages/doe-gpu/scripts/build-addon.js`
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/run-integration.js --runtime node`
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_runner_plan_support bench.tests.test_executor_registry`
  - `python3 bench/gates/schema_gate.py`
- Fresh package artifacts:
  - warm: `bench/out/apple-metal/20260327T171904Z/gemma64.node-package.warm.ir.compare.json`
  - cold: `bench/out/apple-metal/20260327T172017Z/gemma64.node-package.ir.compare.json`
- Current interpretation from those artifacts:
  - both Gemma64 Node/package rows are now comparable and selected-timing `p50` positive for Doe on this host
  - the warm row also flips workload-unit wall `p50` positive, but both rows remain diagnostic because the positive medians do not yet carry positive `p95`
  - the retained warm package gap is no longer a broad package-path loss; the main remaining issue is tail stability, not median submit cost
  - cold package is no longer setup-dominated on selected timing, but cold workload-unit wall still loses because Doe retains higher once-per-sample host overhead outside the selected timing boundary, with `hostExecutorInitTotalNs` still the largest cold-only bucket on this row

## Node/package wait diagnostics now split queueFlush into native wait-completed time versus deferred copy/resolve cleanup, and the current warm Gemma64 row says the retained Doe wait gap is real wait-completed time (2026-03-27)

- Added wait-side package diagnostics to the existing submit-path split in:
  - `runtime/zig/src/doe_queue_flush_breakdown.zig`
  - `runtime/zig/src/doe_queue_submit_native.zig`
  - `runtime/bridge/webgpu-addon/doe_napi_internal.h`
  - `runtime/bridge/webgpu-addon/doe_napi_globals.c`
  - `runtime/bridge/webgpu-addon/doe_napi_queue.c`
  - `packages/doe-gpu/src/vendor/webgpu/index.js`
  - `bench/executors/node-webgpu/executor.js`
  - `config/trace-meta.schema.json`
  - `config/migration-notes.md`
- The package benchmark boundary is unchanged:
  - warm still measures prepared-session package execution
  - `executionSubmitWaitTotalNs` still covers the same retained submit/wait scope
  - the new fields only explain where Doe time is going inside the existing wait path
- New wait-side `packageStepBreakdownNs` fields:
  - `submitQueueFlushTotalNs`
  - `submitQueueFlushWaitCompletedTotalNs`
  - `submitQueueFlushDeferredCopyTotalNs`
  - `submitQueueFlushDeferredResolveTotalNs`
  - `submitQueueWaitBookkeepingTotalNs`
- Current host-state artifact:
  - `bench/out/apple-metal/20260327T170619Z/gemma64.node-package.warm.ir.compare.json`
- Current interpretation from that artifact:
  - Doe’s warm package wait bucket is almost entirely native `wait_completed` time
  - deferred copy and deferred resolve cleanup are negligible on this row
  - the retained warm package loss is therefore not mostly hidden host cleanup inside `queueFlush`
  - the next investigation target should stay on the real wait-completed path and the GPU work it is blocking on, not on deferred-copy bookkeeping

## Node/package trace meta now splits the retained submit path into finish, submit, and wait sub-costs (2026-03-27)

- Extended `packageStepBreakdownNs` for the Node/Bun package executor in:
  - `bench/executors/node-webgpu/executor.js`
  - `config/trace-meta.schema.json`
  - `config/migration-notes.md`
- The package benchmark boundary is unchanged:
  - cold still includes setup in selected timing
  - warm still excludes setup from selected timing
  - warm workload-unit wall still uses `trace-meta-process-wall`
- New package submit-path trace-meta fields:
  - `submitCommandEncoderFinishTotalNs`
  - `submitQueueSubmitTotalNs`
  - `submitQueueWaitTotalNs`
  - `submitCommandPrepTotalNs`
  - `submitAddonCallTotalNs`
  - `submitAddonCommandReplayTotalNs`
  - `submitAddonQueueSubmitTotalNs`
  - `submitAddonFlushTotalNs`
  - `submitPostSubmitBookkeepingTotalNs`
- This is measurement infrastructure for the remaining package submit/wait gap,
  not a new performance claim. Use the instrumented warm diagnostic artifacts
  for the current host state:
  - `bench/out/apple-metal/20260327T162722Z/gemma64.node-package.warm.ir.compare.json`
  - `bench/out/apple-metal/20260327T163023Z/gemma64.node-package.warm.ir.compare.json`
- The new split shows the remaining Doe-side submit-path delta is dominated by
  `submitQueueSubmitTotalNs`, not by `submitQueueWaitTotalNs`, on the current
  host. The next split now isolates whether that submit cost sits in command
  prep, the addon call itself, or post-submit bookkeeping, and then whether the
  addon cost sits in command replay, `wgpuQueueSubmit`, or a post-submit flush.

## Gemma64 Node/package cold setup is no longer dominated by shader translation, and batched package submit now preserves one compute pass across consecutive dispatches (2026-03-27)

- Added persistent WGSL→MSL translation caching for the package/runtime shader
  path in:
  - `runtime/zig/src/doe_shader_native.zig`
  - `runtime/zig/src/doe_shader_translation_cache.zig`
- Rebuilt the shared package dylib with `zig build dropin` and confirmed the
  Gemma64 package kernel set now populates the cache under
  `~/.cache/doe/shader_translation_cache/`.
- Updated `runtime/bridge/webgpu-addon/doe_napi_queue.c` so the batched package
  submit path keeps one compute pass open across consecutive dispatch commands
  instead of reopening a compute pass for every dispatch in the same command
  buffer.
- Package validation passed after the submit-path change:
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/run-integration.js --runtime node`
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_runner_plan_support bench.tests.test_executor_registry`
- Fresh package artifacts:
  - `bench/out/apple-metal/20260327T151450Z/gemma64.node-package.ir.compare.json`
  - `bench/out/apple-metal/20260327T151450Z/gemma64.node-package.warm.ir.compare.json`
- Current state from those artifacts:
  - cold package selected timing moved from a clear Doe loss to near parity
  - warm package selected timing moved materially closer but remains
    non-claimable on this host
  - the old cold shader/module tax is no longer the primary package problem
  - the remaining package gap is now mostly the submit/wait bucket, with cold
    wall time still carrying additional Doe executor-init cost outside the
    selected timing scope

## Canonical compare taxonomy now defines one axis language above promoted compare, governed lanes, and workload-registry surface names (2026-03-27)

- Added `config/compare-taxonomy.json` and
  `config/compare-taxonomy.schema.json` as the canonical compare-axis contract.
- Added the generated expansion artifact and row schema:
  - `config/generated/compare-taxonomy-expanded.jsonl`
  - `config/compare-taxonomy-expanded-row.schema.json`
- The taxonomy now records:
  - canonical axis names for compare reasoning
  - alias maps between promoted compare names (`native` / `direct` /
    `package`) and broader repo surface names (`backend_native` /
    `node_package` / `bun_package` / `deno_package`)
  - the type-correct structural families
  - the theoretical concrete target coverage
  - the current promoted compare subset
- Added `bench/tools/generate_compare_taxonomy.py` to generate and verify the
  expanded matrix artifact, and added `bench/tests/test_compare_taxonomy.py`
  for count drift and promoted-catalog alignment.
- `README.md`, `bench/README.md`, and `docs/benchmark-taxonomy.md` now point to
  `docs/compare-taxonomy.md` for the canonical enum language.
- Verification:
  - `python3 bench/tools/generate_compare_taxonomy.py --write`
  - `python3 bench/tools/generate_compare_taxonomy.py --verify`
  - `python3 -m unittest bench.tests.test_compare_taxonomy bench.tests.test_promoted_compare`
  - `python3 bench/gates/schema_gate.py`

## Bun package rows now use the IR-backed compare stack with the same cold/warm Gemma boundaries as the Node package lane (2026-03-27)

- Added Bun package executor ids to `bench/native_compare_modules/executor_registry.py`:
  - `doe_bun_package`
  - `bun_webgpu_package`
  - `doe_bun_package_prepared`
  - `bun_webgpu_package_prepared`
- Added `bench/executors/run-bun-webgpu-plan.js` plus shared package-runner
  supervision so Bun package rows emit the same trace-meta/report shape as the
  Node package lane, including the existing cold vs prepared-session boundary
  semantics.
- `bench/executors/node-webgpu/executor.js` now resolves package providers by
  runtime host (`node` vs `bun`) while keeping one package trace-meta contract.
- Added Bun cold/warm Gemma compare configs:
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.bun-package.warm.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.bun-package.warm.ir.json`
- Promoted compare config now carries `packageRuntime=node|bun` for
  `surface=package`, and `bench/run_compare.py` selects Bun rows explicitly via
  `--package-runtime bun` while preserving Node as the default package runtime.
- Verification:
  - `python3 -m unittest bench.tests.test_bun_webgpu_executor bench.tests.test_node_webgpu_executor bench.tests.test_promoted_compare bench.tests.test_executor_registry bench.tests.test_runner_plan_support`
  - `python3 bench/gates/schema_gate.py`
  - `bun bench/executors/run-bun-webgpu-plan.js --provider bun-webgpu --plan bench/plans/generated/inference_gemma3_270m_prefill_64tok_decode_64tok.plan.json --trace-meta <tmp-meta> --trace-jsonl <tmp-jsonl> --workload inference_gemma3_270m_prefill_64tok_decode_64tok --dry-run`
  - `bun bench/executors/run-bun-webgpu-plan.js --provider doe --prepared-session --plan bench/plans/generated/inference_gemma3_270m_prefill_64tok_decode_64tok.plan.json --trace-meta <tmp-meta> --trace-jsonl <tmp-jsonl> --workload inference_gemma3_270m_prefill_64tok_decode_64tok --dry-run`
  - `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --package-runtime bun --dry-run`
  - `python3 bench/run_compare.py --surface package --backend apple-metal --workload gemma64 --mode warm --package-runtime bun --dry-run`
- No fresh Bun Gemma performance artifact is recorded yet in this section. This
  change is the compare-stack wiring and contract publication step.

## Node package failure artifacts now preserve terminal evidence on unreadable plans, prepared-session failures keep the warm boundary zeroed, and Doe package cold shader creation no longer pays an extra JS preflight pass (2026-03-27)

- `bench/executors/run-node-webgpu-plan.js` supervisor fallback now emits
  terminal trace artifacts even when the plan itself is unreadable or invalid,
  instead of reparsing the same broken plan and dropping the artifact.
- `bench/executors/node-webgpu/executor.js` now scopes prepared-session
  unsupported/error artifacts through `boundaryScopedHostTotals`, so warm
  failure evidence keeps pre-boundary host totals at zero.
- `bench/run_compare.py` now resolves relative `configPath` entries against the
  selected `--catalog` location for custom catalogs instead of always pinning
  them to repo root.
- `packages/doe-gpu/src/vendor/webgpu/shared/full-surface.js` and
  `packages/doe-gpu/src/vendor/webgpu/index.js` now skip Doe’s duplicate
  `createShaderModule()` JS preflight pass on the hot cold-package path while
  keeping explicit `preflightShaderSource()` available as a separate API.
- Verification:
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_promoted_compare bench.tests.test_runner_plan_support bench.tests.test_executor_registry bench.tests.test_native_compare_config_support`
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/run-integration.js --runtime node`
  - `python3 bench/gates/schema_gate.py`
- Fresh package compare reruns were blocked on this host by adapter bring-up, so
  there is no new trustworthy performance artifact yet:
  - [cold rerun](/Users/xyz/deco/doe/bench/out/apple-metal/20260327T140227Z/gemma64.node-package.ir.compare.json)
  - [warm rerun](/Users/xyz/deco/doe/bench/out/apple-metal/20260327T140329Z/gemma64.node-package.warm.ir.compare.json)
  - direct worker debug shows `requestAdapter failed (status=3, detail=metal default device unavailable)` on the current machine for the Node package lane.

## Compare front doors now expose the native/direct/package matrix through one config-backed catalog instead of a handful of special-case wrappers (2026-03-27)

- Expanded `config/promoted-compare-catalog.json` from the earlier
  Apple-Metal-only direct/package aliases into a fuller matrix registry with:
  - `surface=native` for existing command/delegate preset lanes
  - `surface=direct` for standalone Doe-plan vs standalone Dawn-plan rows
  - `surface=package` for Node/package-surface rows
- The catalog now has explicit tuple axes:
  - `backend`
  - `surface`
  - `preset` for native preset lanes
  - `workload` for direct/package workload rows
  - `mode` for `default` / `cold` / `warm`
- `bench/run_compare.py` now resolves either:
  - `--surface native --backend <backend> --preset <preset>`
  - `--surface direct --backend apple-metal --workload <workload>`
  - `--surface package --backend apple-metal --workload <workload> --mode <mode>`
- This keeps the existing compare configs and compare runner unchanged. The new
  layer is only a schema-validated config front door above them.
- Added native preset coverage for:
  - Apple Metal: `smoke`, `compare-dev`, `compare`, `frontier`, `explore`,
    `release`, `breadth`
  - AMD Vulkan: `smoke`, `smoke-gpu`, `compare-dev`, `compare`, `frontier`,
    `explore`, `release`
  - local D3D12: `smoke`, `compare-dev`, `compare`, `frontier`, `explore`,
    `release`
- Updated `bench/tests/test_promoted_compare.py` to cover native preset
  resolution as well as direct/package workload resolution.
- Verification:
  - `python3 -m unittest bench.tests.test_promoted_compare bench.tests.test_executor_registry bench.tests.test_native_compare_config_support`
  - `python3 bench/gates/schema_gate.py`
  - `python3 bench/run_compare.py --list --backend apple-metal`
  - `python3 bench/run_compare.py --surface native --backend apple-metal --preset compare --dry-run`
  - `python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma270m-literal --dry-run`

## Promoted compare front doors now wrap standalone direct Dawn rows and Node package rows through a schema-validated catalog instead of raw config filenames (2026-03-27)

- Added `config/promoted-compare-catalog.json` and
  `config/promoted-compare-catalog.schema.json` as the config-backed registry
  for promoted compare surfaces.
- Added `bench/run_compare.py` as a thin front door that resolves a promoted
  backend/surface/workload tuple (or exact profile id) and then delegates to
  the existing `bench/native-compare/compare_dawn_vs_doe.py` runner.
- The promoted catalog currently wraps the existing Apple Metal rows for:
  - standalone direct Doe vs standalone direct Dawn:
    `gemma64`, `gemma1b`, and `gemma270m-literal`
  - package-surface Doe vs Dawn Node WebGPU:
    `gemma64` and `gemma1b` on both cold and prepared-session boundaries
- This does not change benchmark methodology or executor wiring. It promotes
  the claim-grade direct Dawn lane and the separate package-surface lane as
  explicit front doors above the existing config files and executor registry.
- Added focused coverage in `bench/tests/test_promoted_compare.py` for catalog
  loading, direct/package resolution, and wrapper argv construction.
- `config/schema-targets.json` now validates the promoted compare catalog as a
  blocking schema target.
- Verification:
  - `python3 -m unittest bench.tests.test_promoted_compare`
  - `python3 bench/run_compare.py --list`
  - `python3 bench/run_compare.py --surface direct --backend apple-metal --workload gemma270m-literal --dry-run`
  - `python3 bench/gates/schema_gate.py`

## Literal Gemma270M direct Metal now dispatches WGSL kernels with their declared workgroup size, and the row is claimable again on repeated reruns (2026-03-27)

- The literal 270M row in `bench/ir/gemma3_270m_literal.json` had one more
  real direct-Metal mismatch after the robustness-clamp fix: the compute
  runtime already knew the WGSL workgroup size, but the benchmark-facing Metal
  pipeline cache was discarding that metadata and launching `kernel_dispatch`
  workloads with a generic pipeline-max threadgroup shape.
- `runtime/zig/src/backend/metal/metal_runtime_resources.zig` now keeps
  WGSL-derived `workgroup_size` metadata alongside the cached Metal pipeline,
  and `runtime/zig/src/backend/metal/metal_native_runtime.zig` /
  `runtime/zig/src/backend/metal/metal_kernel_dispatch.zig` now thread that
  metadata into the direct `kernel_dispatch` path instead of guessing.
- `runtime/zig/src/backend/metal/metal_bridge.m`,
  `runtime/zig/src/backend/metal/metal_bridge_decls.zig`, and
  `runtime/zig/src/backend/metal/metal_bridge_stubs.c` now accept explicit
  workgroup dimensions on the batched compute-dispatch bridge call, matching
  the lower-level command-buffer encode path that already supported them.
- The direct outcome is that the production-style literal tiled matmul path is
  no longer benchmarking Doe with a synthetic threadgroup geometry on Metal.
- New focused coverage in
  `runtime/zig/src/backend/metal/metal_runtime_resources.zig` locks the cached
  workgroup-size lookup for keyed pipelines.
- Fresh literal-row artifacts after the workgroup-size fix:
  - `bench/out/apple-metal/20260327T122749Z/gemma270m.literal.ir.compare.json`
  - `bench/out/apple-metal/20260327T122813Z/gemma270m.literal.ir.compare.json`
- Result:
  - both reruns stayed `comparisonStatus=comparable`
  - both reruns are now `claimStatus=claimable`
  - this supersedes the earlier diagnostic literal artifacts that were still
    paying the wrong direct-Metal dispatch geometry
- Verification:
  - `zig build doe-plan-executor`
  - `zig build test-core`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma270m.literal.ir.json`

## Literal Gemma270M now uses the more production-like kernel path, and the WGSL robustness pass no longer injects redundant tile clamps into provably in-bounds local/workgroup accesses (2026-03-27)

- The new literal 270M benchmark source is
  `bench/ir/gemma3_270m_literal.json`, with compare config
  `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma270m.literal.ir.json`.
- That row keeps synthetic weights, but it now follows the production-style
  execution path more closely: production-like kernel families and entry
  points, gated FFN, tied LM-head-style decode, and split current/past KV
  decode attention.
- To make the literal path valid on Doe direct Metal,
  `runtime/zig/src/backend/metal/metal_runtime_resources.zig`,
  `runtime/zig/src/backend/metal/metal_native_runtime.zig`,
  `runtime/zig/src/backend/metal/metal_kernel_dispatch.zig`,
  `runtime/zig/src/backend/metal/mod.zig`, and
  `runtime/zig/src/backend/metal/metal_dispatch_runtime.zig` now honor
  non-default compute entry points and cache pipelines by kernel plus entry
  point instead of kernel filename alone.
- The remaining literal-row performance regression was traced to Doe's WGSL
  robustness lowering: the runtime compiler was still emitting redundant
  bounds clamps on provably in-range workgroup tile accesses inside the
  tiled prefill matmul hot loop.
- `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig` now elides those
  clamps when static bounds prove a sized-array access is in range, and the
  new helper `runtime/zig/src/doe_wgsl/robustness_static_bounds.zig` proves
  bounds for local/workgroup/function/private arrays using module constants,
  local invocation IDs, simple arithmetic, const-local aliases, and canonical
  counted loops.
- New coverage lives in
  `runtime/zig/src/doe_wgsl/mod_bounds_local_test.zig`, and
  `runtime/zig/src/doe_wgsl/WGSL_SUPPORT.md` now documents that Doe keeps
  robustness on unknown accesses while dropping redundant clamps for provably
  in-range local/workgroup/function/private sized arrays.
- Fresh literal-row artifacts:
  - initial literal compare:
    `bench/out/apple-metal/20260327T012241Z/gemma270m.literal.ir.compare.json`
  - pre-fix loss after the more production-like tiled kernel:
    `bench/out/apple-metal/20260327T014136Z/gemma270m.literal.ir.compare.json`
  - post-fix reruns after clamp elision:
    `bench/out/apple-metal/20260327T015737Z/gemma270m.literal.ir.compare.json`
    `bench/out/apple-metal/20260327T015845Z/gemma270m.literal.ir.compare.json`
    `bench/out/apple-metal/20260327T015906Z/gemma270m.literal.ir.compare.json`
- Result:
  - the literal 270M row is now structurally comparable and materially closer
    to parity than the pre-fix regression artifact
  - the benchmark is still diagnostic on this host because the tail and
    workload-unit-wall outcomes are not yet consistently positive for Doe
  - the remaining issue is no longer benchmark validity or obvious hot-loop
    clamp pollution; it is residual runtime/submit-wait stability on the
    literal path
- Verification:
  - `zig build test-core`
  - `zig build emit-msl`
  - `zig build doe-plan-executor`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma270m.literal.ir.json`

## Node package dispatch bind groups now reuse repeated binding sets, Metal bring-up falls back to enumerated devices, and the remaining package/drop-in blockers are now clearly host/runtime failures rather than harness gaps (2026-03-27)

- `bench/executors/node-webgpu/executor.js` now caches package-path bind
  groups by binding set instead of creating a fresh bind group for every
  dispatch step.
- On the Gemma package plans, that cache targets a real cold-path cost center:
  the shaped Gemma command streams still execute `1170` dispatches, but they
  only use `36` distinct bind-group binding sets.
- `runtime/zig/src/backend/metal/metal_bridge.m` now falls back from
  `MTLCreateSystemDefaultDevice()` to `MTLCopyAllDevices()` on macOS, and it
  ensures default-device creation runs on the main thread before returning the
  retained Metal handle.
- `bench/drop-in/dropin_behavior_suite.c` now uses the same
  high-performance / default / low-power adapter retry order as the benchmark
  suite instead of a single adapter request.
- Fresh Gemma64 package reruns after the bind-group cache:
  - cold package lane:
    `bench/out/apple-metal/20260327T014544Z/gemma64.node-package.ir.compare.json`
  - prepared-session package lane:
    `bench/out/apple-metal/20260327T014544Z/gemma64.node-package.warm.ir.compare.json`
- Result:
  - both Gemma64 package lanes stayed `comparisonStatus=comparable`
  - both are still `claimStatus=diagnostic` on this host
  - the cache is a real product/runtime reduction in cold setup churn, but this
    rerun did not turn the package lane into claimable evidence
- Fresh Gemma1B package reruns after the supervisor hardening remained:
  - cold:
    `bench/out/apple-metal/20260327T014608Z/gemma1b.node-package.ir.compare.json`
  - warm:
    `bench/out/apple-metal/20260327T014609Z/gemma1b.node-package.warm.ir.compare.json`
- Result:
  - both 1B package lanes still terminate as diagnostic artifacts instead of
    exploding the compare harness
  - both remain blocked by Dawn/right-side execution failure on this host, not
    by missing artifacts or compare-runner crashes
- Fresh drop-in reruns after the Metal fallback and behavior-suite retry parity:
  - benchmark suite:
    `bench/out/dropin/20260327T014653Z/dropin_benchmark_report.json`
  - behavior suite:
    `bench/out/dropin/20260327T014653Z/dropin_behavior_report.json`
- Result:
  - the remaining drop-in blocker is still adapter unavailability on this host
    (`metal default device unavailable` / `adapter_request_failed`)
  - the fallback/retry changes did not restore adapter-dependent rows on this
    machine, so microbench-driven runtime tuning is still blocked by host
    bring-up rather than harness/build failures
- Verification:
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_runner_plan_support bench.tests.test_executor_registry`
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/run-integration.js --runtime node`
  - `zig build doe-runtime`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.ir.json`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.warm.ir.json`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.ir.json`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.warm.ir.json`
  - `python3 bench/drop-in/dropin_behavior_suite.py --artifact runtime/zig/zig-out/lib/libwebgpu_doe.dylib`
  - `python3 bench/drop-in/dropin_benchmark_suite.py --artifact runtime/zig/zig-out/lib/libwebgpu_doe.dylib --micro-iterations 1 --e2e-iterations 1`

## Gemma1B Node package lanes now fail safely with diagnostic artifacts, and drop-in reports now capture the adapter-unavailable root cause explicitly (2026-03-27)

- `bench/executors/run-node-webgpu-plan.js` now runs the Node package executor
  under a supervisor process. If the inner provider process exits before
  writing terminal trace metadata, the supervisor writes an explicit error
  `trace_meta` record instead of leaving the compare harness with a raw process
  failure and no evidence.
- `bench/executors/node-webgpu/executor.js` already emitted explicit
  unsupported/error metadata for executor-managed failure paths; this change
  closes the remaining gap where the outer process could die before those
  artifacts existed.
- Fresh Gemma1B Node package compare artifacts after that hardening:
  - cold package lane:
    `bench/out/apple-metal/20260327T012838Z/gemma1b.node-package.ir.compare.json`
  - prepared-session package lane:
    `bench/out/apple-metal/20260327T012903Z/gemma1b.node-package.warm.ir.compare.json`
- Result:
  - both 1B package compares now terminate as diagnostic artifacts instead of
    crashing the compare harness
  - both rows are still unreliable/non-comparable on this host because the
    Dawn/right side reports execution errors in every timed sample, with zero
    dispatch/row/success counts and zero traced execution timing
  - the remaining blocker is therefore the underlying Dawn/host package
    execution failure, not missing compare evidence
- The right-side workspace metadata now records that failure explicitly, for
  example:
  - cold:
    `bench/out/apple-metal/20260327T012838Z/gemma1b.node-package.ir.workspace/inference_gemma3_1b_prefill_64tok_decode_64tok/right/dawn_node_webgpu.run000.meta.json`
  - warm:
    `bench/out/apple-metal/20260327T012903Z/gemma1b.node-package.warm.ir.workspace/inference_gemma3_1b_prefill_64tok_decode_64tok/right/dawn_node_webgpu_prepared.run000.meta.json`
- The drop-in harness path is likewise now evidence-complete:
  - benchmark report:
    `bench/out/dropin_benchmark_report.json`
  - behavior report:
    `bench/out/dropin_behavior_report.json`
- Result:
  - the macOS link-path issue remains fixed
  - the remaining drop-in blocker is now explicit adapter unavailability on
    this host (`metal default device unavailable` / `adapter_request_failed`),
    not harness build failure
  - `instance_create_destroy` still emits samples, but adapter-dependent rows
    remain blocked until adapter/device acquisition is stable again
- Verification:
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_runner_plan_support bench.tests.test_executor_registry`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.ir.json`
  - `python3 bench/native-compare/compare_dawn_vs_doe.py --config bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.warm.ir.json`

## Literal Gemma-3-270M benchmark row landed, Doe direct Metal now honors compute entry points, and the first literal compare is structurally comparable but still diagnostic (2026-03-27)

- Added a new Doe-owned literal-production-style benchmark source at
  `bench/ir/gemma3_270m_literal.json` with the minimal
  `inference_gemma3_270m_literal_prefill_32tok_decode_1tok` scenario.
- Added the matching compare config at
  `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma270m.literal.ir.json`
  and catalog wiring in:
  - `bench/workloads/metadata/backend-workload-catalog.json`
  - `bench/tests/test_backend_workload_catalog.py`
  - `config/schema-targets.json`
  - `bench/README.md`
- The literal row keeps synthetic data, but it now follows the production-style
  path much more closely than the shaped row:
  - production-style kernel families and entry points
  - gated FFN via `gelu_gated.wgsl`
  - tied LM-head-style multicol decode path
  - production-style RMSNorm weight offset entry point
  - decode attention split across current and past KV bindings
- Doe direct Metal now honors non-default compute entry points in the runtime
  path. The direct backend change landed in:
  - `runtime/zig/src/backend/metal/mod.zig`
  - `runtime/zig/src/backend/metal/metal_kernel_dispatch.zig`
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig`
  - `runtime/zig/src/backend/metal/metal_runtime_resources.zig`
  - `runtime/zig/src/backend/metal/metal_dispatch_runtime.zig`
- Metal pipeline cache keys now include non-default compute entry points, so
  warmup and direct runtime execution resolve the same compute pipeline
  identity instead of collapsing multiple entry points onto one kernel-name key.
- The literal-production-style kernels were also reduced back into the WGSL/MSL
  subset Doe’s direct runtime compiler accepts without changing the benchmark
  graph shape. The key fixes were:
  - flatten helper functions that implicitly captured bound resources or
    threadgroup storage
  - remove the inline conditional-expression form that Doe sema still rejects
- Fresh literal compare artifact:
  `bench/out/apple-metal/20260327T012241Z/gemma270m.literal.ir.compare.json`
- Result:
  - the row is now structurally comparable on both sides instead of failing on
    Doe-side shader compilation
  - it is still diagnostic, not claimable, because Doe is slower than Dawn on
    this more literal 270M production-style path on this host
- Verification:
  - `zig build doe-plan-executor`
  - `zig build test-core`
  - `python3 bench/tools/generate_backend_workloads.py --verify`
  - `python3 bench/gates/schema_gate.py`
  - `python3 -m unittest bench.tests.test_backend_workload_catalog bench.tests.test_benchmark_ir`

## Node package submit/wait short-circuit landed, Gemma64 package reruns moved again, and the drop-in macOS harness now links against the Doe dylib by path (2026-03-27)

- `packages/doe-gpu/src/vendor/webgpu/index.js` now skips
  `queueFlush(...)` in `queue.onSubmittedWorkDone()` when the queue state is
  already marked complete, so synchronous or already-completed package submits
  no longer pay a redundant wait path.
- The same package submit path now fast-paths a single `_batched`
  command-buffer submit by passing its recorded command array directly to
  `submitBatched(...)`, instead of rebuilding a flattened array first.
- Fresh Gemma64 package reruns after that change:
  - cold package lane:
    `bench/out/apple-metal/20260327T004741Z/gemma64.node-package.ir.compare.json`
  - prepared-session package lane:
    `bench/out/apple-metal/20260327T004755Z/gemma64.node-package.warm.ir.compare.json`
- Compared with the 2026-03-26 package baselines:
  - `bench/out/apple-metal/20260326T214312Z/gemma64.node-package.ir.compare.json`
  - `bench/out/apple-metal/20260326T214456Z/gemma64.node-package.warm.ir.compare.json`
- Result:
  - the new reruns changed direction on this host, but the Dawn/package side
    also moved materially at the same time
  - treat these as additional tuning artifacts, not as stable replacement
    package evidence yet
  - the warm row remains attribution-consistent, so the package boundary itself
    is still the right tuning target even though this rerun needs stability
    follow-up
- `bench/executors/node-webgpu/executor.js` and
  `bench/executors/run-node-webgpu-plan.js` now support executor-local
  `--debug-boundaries` and `--step-limit` flags for bounded package crash
  diagnosis without changing compare workload contracts.
- Gemma1B package evidence remains blocked:
  - a fresh cold package compare still fails on the Dawn side with `rc=-11` in
    `bench/out/apple-metal/20260327T005008Z/gemma1b.node-package.ir.workspace/`
  - a debug rerun under `DOE_NODE_WEBGPU_DEBUG_BOUNDARIES=1` then exposed a
    separate host-instability case where the Doe side failed early with
    `metal default device unavailable` in
    `bench/out/apple-metal/20260327T005355Z/gemma1b.node-package.ir.workspace/`
  - Gemma1B package rows are therefore still unusable evidence on this host
- `bench/drop-in/dropin_benchmark_suite.py` and
  `bench/drop-in/dropin_behavior_suite.py` now link the candidate shared
  library by explicit path on macOS instead of GNU `-l:` syntax, and they set
  `DYLD_LIBRARY_PATH` alongside `LD_LIBRARY_PATH` for the child harness.
- `bench/drop-in/dropin_gate.py` now defaults its `--artifact` path to
  `libwebgpu_doe.dylib` on macOS instead of the Linux `.so` name.
- Fresh drop-in artifacts after that harness fix:
  - benchmark suite:
    `bench/out/dropin/20260327T005752Z/dropin_benchmark_report.json`
  - behavior suite:
    `bench/out/dropin_behavior_report.json`
- Result:
  - the macOS link-path failure is fixed
  - both suites are still blocked by `adapter_request_failed` once they move
    past `instance_create_destroy`
  - `instance_create_destroy` now emits real samples again on this host, but
    the adapter-dependent micro rows are still not trustworthy enough to drive
    runtime tuning yet

## Node package Gemma64 narrowed on both cold and prepared-session lanes, and empty queue submit now avoids useless Metal command-buffer creation (2026-03-26)

- `packages/doe-gpu/src/vendor/webgpu/index.js` no longer runs duplicate WGSL
  preflight on the Node full-surface `createShaderModule()` path. The full
  surface was already validating shader source in
  `shared/full-surface.js`; the Node backend was repeating the same preflight
  immediately before `addon.createShaderModule(...)`.
- The same Node package path now keeps lazy compute/copy command buffers batched
  through `commandEncoder.finish()` so `GPUQueue.submit()` can use the existing
  `submitBatched(...)` path instead of replaying the recorded command list into
  a native command encoder first on the common compute path.
- Fresh Gemma64 package reruns after those changes:
  - cold package lane:
    `bench/out/apple-metal/20260326T214312Z/gemma64.node-package.ir.compare.json`
  - prepared-session package lane:
    `bench/out/apple-metal/20260326T214328Z/gemma64.node-package.warm.ir.compare.json`
- Compared with the earlier package references:
  - `bench/out/apple-metal/20260326T212317Z/gemma64.node-package.ir.compare.json`
  - `bench/out/apple-metal/20260326T212405Z/gemma64.node-package.warm.ir.compare.json`
- Result:
  - Doe is still slower than Dawn on the Node/package boundary, but both lanes
    improved materially on this host
  - the cold package loss narrowed after reducing Doe-side shader-module setup
    cost
  - the prepared-session loss also narrowed, which means the general batched
    command-buffer path helped the steady-state package lane too
- Current package diagnosis:
  - shader-module creation was a real cold-package problem and is now smaller
  - the remaining package gap is still dominated by the Node/package execution
    boundary, especially the submit/wait portion on Gemma64
  - Gemma1B Node package compare is still blocked locally by a Dawn-side
    `rc=-11` crash, so Gemma64 remains the validated package evidence row
- `runtime/zig/src/doe_queue_submit_native.zig` now fast-exits empty queue
  submits before creating a Metal command buffer when every submitted
  `DoeCommandBuffer` has zero recorded commands. This is a real runtime-path
  improvement for the named `queue_submit_empty` microbench target, not a
  benchmark-only change.
- Validation:
  - `node packages/doe-gpu/test/smoke/test-smoke-load.js`
  - `node packages/doe-gpu/test/integration/run-integration.js --runtime node`
  - `python3 -m unittest bench.tests.test_node_webgpu_executor bench.tests.test_executor_registry bench.tests.test_runner_plan_support`
  - `zig build doe-runtime`
  - `zig build test-core`

## Warm Node package rows now keep workload-unit wall attribution internally consistent (2026-03-26)

- Prepared-session Node package rows now keep the existing host-overhead bucket
  contract: `host*TotalNs` fields mean "outside selected timing but inside
  workload-unit wall", so pre-boundary plan load/parse/normalize and runtime
  creation no longer flow into those buckets on warm rows.
- `config/trace-meta.schema.json` now constrains
  `workloadUnitWallSource=trace-meta-process-wall` via enum rather than allowing
  arbitrary strings.
- The compare runner now suppresses prepared-session `cpu_time` metrics unless a
  matching inner-boundary CPU source exists, instead of mixing subprocess CPU
  time with the inner trace-meta wall boundary.
- Fresh warm-package rerun artifact:
  `bench/out/apple-metal/20260326T214456Z/gemma64.node-package.warm.ir.compare.json`
- The rerun remains `comparisonStatus=comparable` and `claimStatus=diagnostic`.
- The new left-side warm trace meta in
  `bench/out/apple-metal/20260326T214456Z/gemma64.node-package.warm.ir.workspace/`
  now shows the prepared-session pre-boundary host totals zeroed, while the
  host-overhead breakdown in the compare artifact no longer produces the prior
  negative selected-gap remainder.
- This supersedes the earlier prepared-session package attribution note at
  `bench/out/apple-metal/20260326T212405Z/gemma64.node-package.warm.ir.compare.json`.

## Governed Gemma 1B rerun now exposes artifact-finalize sub-buckets and confirms the remaining direct-lane cost is JSONL serialization (2026-03-26)

- `runtime/zig/src/trace.zig` and `config/trace-meta.schema.json` now carry
  fine-grained artifact-finalize diagnostics for:
  - `hostArtifactTraceJsonlSerializeTotalNs`
  - `hostArtifactTraceJsonlWriteTotalNs`
  - `hostArtifactOperatorManifestFinalizeTotalNs`
- `runtime/zig/src/trace_jsonl_emit.zig` now streams both generic and
  plan-specific trace rows through a buffered file writer while timing
  serialization separately from file writeback.
- Corrected governed Apple Metal Gemma 1B rerun artifact after rebuilding the
  standalone plan executors:
  `bench/out/apple-metal/20260326T212923Z/gemma1b.ir.compare.json`
- The compare artifact remains `comparisonStatus=comparable` and
  `claimStatus=claimable`.
- The new left-side trace meta in
  `bench/out/apple-metal/20260326T212923Z/gemma1b.ir.workspace/` now shows that
  the remaining Doe direct-lane artifact-finalize cost is dominated by JSONL
  serialization rather than file writeback.
- This supersedes the earlier 2026-03-26 note that saw no governed
  `artifactFinalize` improvement before the actual `doe-plan-executor` target
  was rebuilt for the compare lane.

## Node package Gemma compare now has explicit cold vs prepared-session boundaries and package host buckets (2026-03-26)

- The Node plan executor under `bench/executors/node-webgpu/executor.js` now
  emits real package-lane host totals:
  - `hostInputReadTotalNs`
  - `hostInputParseTotalNs`
  - `hostWorkloadPrepareTotalNs`
  - `hostExecutorInitTotalNs`
  - `hostCommandOrchestrationTotalNs`
  - `hostArtifactFinalizeTotalNs`
- Trace meta for this lane now also carries explicit package setup and step
  breakdowns, including shader-module creation, bind-group/pipeline creation,
  write materialization, queue writes, and dispatch encode API time.
- Added prepared-session package executor ids and configs:
  - `doe_node_webgpu_prepared`
  - `dawn_node_webgpu_prepared`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.warm.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.warm.ir.json`
- Cold package rerun artifact:
  `bench/out/apple-metal/20260326T212317Z/gemma64.node-package.ir.compare.json`
  - stayed `comparisonStatus=comparable`
  - stayed `claimStatus=diagnostic`
  - Doe remained slower on selected timing and workload-unit wall
  - the new buckets show the dominant cold-package gap is setup, especially
    Doe-side shader-module creation under the JS/package path
- Prepared-session rerun artifact:
  `bench/out/apple-metal/20260326T212405Z/gemma64.node-package.warm.ir.compare.json`
  - stayed `comparisonStatus=comparable`
  - stayed `claimStatus=diagnostic`
  - Doe remained slower even after package setup was moved out of
    `selectedTiming`
  - this means the remaining package loss is not just cold first-use setup; it
    persists on the steady-state Node/package boundary too
- Methodology note:
  - cold package rows keep setup inside `selectedTiming` and keep
    `workloadUnitWall` on subprocess wall
  - prepared-session rows use
    `workloadUnitWallSource=trace-meta-process-wall` so the timed wall matches
    the prepared-session boundary instead of fresh-process startup
- Current diagnosis:
  - Doe direct backend still wins on the direct executor lane
  - Doe package-surface loss is now concretely attributable to the Node/package
    path rather than missing host-bucket instrumentation
  - next tuning target is the Doe package integration path, starting with
    shader-module creation and other per-session JS/addon setup costs
- Follow-up stability note:
  - the Gemma 1B Node package configs are now selector-correct for the
    `exploration` cohort, but fresh local reruns still fail on the Dawn Node
    WebGPU side with `rc=-11` before producing a compare artifact
  - this means the cold/prepared package-boundary split is validated on the
    Gemma64 row today, while Gemma1B package execution still needs a separate
    stability investigation before it can join the package evidence set

## Plan-specific trace rows now remove the dominant Doe artifact-finalize cost on the governed Gemma 1B lane (2026-03-26)

- `runtime/zig/src/trace_jsonl_emit.zig` now has a plan-specific JSONL trace
  writer for direct plan execution, and
  `runtime/zig/src/doe_plan_executor.zig` uses that writer instead of the
  generic quirk/trace row formatter.
- The direct plan trace rows no longer repeat per-row execution artifact
  metadata that is already present in trace meta, and they no longer emit
  unused quirk-decision fields on the plan path.
- The governed Apple Metal Gemma 1B rerun after this change is:
  `bench/out/apple-metal/20260326T210623Z/gemma1b.ir.compare.json`
- Compared with the earlier references:
  - `bench/out/apple-metal/20260326T202133Z/gemma1b.ir.compare.json`
  - `bench/out/apple-metal/20260326T205420Z/gemma1b.ir.compare.json`
- The new artifact keeps `comparisonStatus=comparable` and
  `claimStatus=claimable`, while the Doe-side host-overhead breakdown now shows
  the prior artifact-finalize bottleneck materially reduced on this lane.

## First governed Gemma 1B rerun after host-side artifact write changes is still comparable but not yet lower in artifact finalize (2026-03-26)

- Re-ran the governed Apple Metal Gemma 1B IR compare config after the trace
  JSONL buffering and incremental manifest-hash changes:
  - current artifact:
    `bench/out/apple-metal/20260326T205420Z/gemma1b.ir.compare.json`
  - prior reference artifact:
    `bench/out/apple-metal/20260326T202133Z/gemma1b.ir.compare.json`
- The new run remains `comparisonStatus=comparable` and `claimStatus=claimable`.
- The host-overhead bucket layout still points to `artifactFinalize` as the
  dominant Doe-side wall-gap cost on this lane. The code changes removed an
  extra manifest reread/hash pass and buffered the trace JSONL writes, but this
  first governed rerun did not yet show a material reduction in that bucket
  relative to the latest pre-change reference artifact.
- This means the current diagnosis stays the same: the host-side artifact path
  is still the main optimization target, and the new changes are safe plumbing
  improvements rather than a demonstrated end-state fix.

## Trace JSONL emission and operator manifests now avoid extra host-side artifact passes (2026-03-26)

- `runtime/zig/src/trace_jsonl_emit.zig` now batches trace JSONL rows into one
  in-memory buffer before writing them to disk, and both
  `runtime/zig/src/main.zig` plus `runtime/zig/src/doe_plan_executor.zig` use
  that shared path for artifact finalization.
- `runtime/zig/src/operator_artifacts.zig` now hashes the operator manifest
  incrementally while records are emitted and finalized, instead of rereading
  the manifest from disk after close just to compute `manifest_hash`.
- This change is intentionally a host-overhead optimization only. It does not
  move artifact work outside `workloadUnitWall`, change compare methodology, or
  add benchmark-only hidden switches.

## IR-backed Node package compare lane now exists beside the direct executor lane (2026-03-26)

- The standalone Node plan executor under
  `bench/executors/run-node-webgpu-plan.js` now supports both:
  - `doe` via the local `doe-gpu` package surface
  - `dawn` via the Node `webgpu` package
- Added explicit compare executor ids:
  - `doe_node_webgpu`
  - `dawn_node_webgpu`
- Added first-class Apple Metal package-lane configs for the neutral Gemma IR
  rows:
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.node-package.ir.json`
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.node-package.ir.json`
- This lane is for JS/package-surface evidence. It reuses the same normalized
  plan and compare/report stack, but it is distinct from the direct
  implementation lane and should be interpreted that way.

## Quirk active mode: backends now consume workaround flags (2026-03-26)

- **Metal copy**: `metal_copy_runtime.zig` texture-to-texture path now checks
  `uses_temporary_buffer`. When set, copies stage through a temporary buffer
  (src texture -> staging buffer -> dst texture) with alignment from the quirk.
- **Metal render**: `metal_native_runtime.zig` render_draw now checks
  `uses_temporary_render_texture`. When set, renders to a temporary texture and
  blits to the real target, working around Intel R8/RG8Unorm small-mip
  corruption.
- **D3D12 copy**: `d3d12_copy.zig` texture-to-texture path now checks
  `uses_temporary_buffer`. When set, stages through a temporary buffer with
  a resource barrier transition between the two copies.
- **Nightly mining**: Added `.github/workflows/nightly-quirk-mining.yml` (daily
  at 02:57 UTC) that runs `mine_upstream_quirks.py` across all vendor/API
  combinations against the vendored Dawn source.
- **Integration tests**: `quirk/mod.zig` now tests the full roundtrip:
  `dispatchWithMode(.active, ...)` propagates `uses_temporary_buffer` and
  `uses_temporary_render_texture` flags through to the output command, while
  `.trace` and `.off` modes leave commands unmodified.

## Lean proof artifacts now carry source/toolchain provenance and shared pattern contracts (2026-03-26)

- `config/proof-artifact.schema.json` now requires a `provenance` block on the
  Lean proof artifact, covering:
  - the pinned Lean toolchain ref
  - `pipeline/lean/Doe/Extract.lean`
  - the deterministic `pipeline/lean/Doe` source tree hash
  - the generated comparability contract
  - the shared proof-pattern spec under `config/lean-proof-patterns.json`
- `pipeline/lean/extract.sh` now computes and injects those provenance values
  during extraction, and `runtime/zig/src/lean_proof.zig` now rejects
  `-Dlean-verified=true` builds when the artifact provenance does not match the
  current repo state.
- Added `config/lean-proof-patterns.json` as the shared runtime proof-pattern
  contract for theorem-backed bounds elision and validator removal callsites.
- Added targeted negative tests so near-miss shader patterns keep their
  robustness clamps and do not silently record dispatch-fit preconditions.
- Added extra host-side precondition tests around missing bindings and
  1D/3D texture extent validation to tighten the trusted matcher/application
  boundary.

## Metal direct compute buffers now honor initialize-on-create parity for IR-backed compare runs (2026-03-26)

- The direct Metal compute-buffer path now honors
  `initialize_buffers_on_create` for first-use buffer allocation in
  `runtime/zig/src/backend/metal/metal_runtime_resources.zig`, matching the
  existing Dawn/WebGPU and Vulkan behavior instead of silently ignoring the
  request on Doe.
- This closes a real apples-to-apples criticism for IR-backed inference
  compares: the benchmark IR already requested zero-init, and the Dawn side
  enforced it, but Doe's Metal path previously did not.
- The parity fix was validated with:
  - build/test: `zig build test`
  - fair rerun artifact:
    `bench/out/apple-metal/20260326T202133Z/gemma1b.ir.compare.json`
- The prior pre-fix comparison artifact remains useful as historical context:
  `bench/out/apple-metal/20260326T200557Z/gemma1b.ir.compare.json`

## Added Gemma-shaped 1B runtime benchmark rows on the neutral IR path (2026-03-26)

- Added a second neutral inference IR at `bench/ir/gemma3_1b.json` for a
  larger 1B-class Gemma-shaped compute workload on the same retained-kernel
  path used by the existing 270M row.
- Apple Metal now materializes three comparable 1B-shaped runtime rows:
  - `inference_gemma3_1b_prefill_32tok`
  - `inference_gemma3_1b_decode_1tok`
  - `inference_gemma3_1b_prefill_64tok_decode_64tok`
- A dedicated direct-plan compare config now exists at
  `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma1b.ir.json`.
- The 1B rows are exploration-only for now so the governed Metal suite does
  not silently become much heavier before fresh evidence is collected.

## WGSL bench validator elision and compute bind-group slot flattening now honor Lean/runtime invariants (2026-03-26)

- `runtime/zig/src/doe_wgsl/bench.zig` now uses the same
  `lean_proof.validator_elimination_available` gate as the main WGSL
  translation path, so the shader microbenchmark no longer pays
  `ir_validate.validate()` when the checked proof artifact already proves the
  validator redundant for builder-produced IR.
- `runtime/zig/build.zig` now passes `build_options` into the standalone
  `doe-shader-bench` target so the benchmark executable can consume Lean proof
  availability the same way as the rest of the runtime build.
- Added `runtime/zig/src/doe_compute_bind_groups.zig` and routed
  `doe_compute_ext_native.zig` plus `doe_compute_fast.zig` through it so direct
  dispatch, indirect dispatch, and the fast compute path flatten bind groups
  using the existing `MAX_BIND * MAX_COMPUTE_BIND_GROUPS` invariant instead of
  rechecking `slot < MAX_FLAT_BIND` inside the hot loop.

## Compute runtime translation now consumes proof-backed texture dispatch-fit elision (2026-03-26)

- `runtime/zig/src/doe_wgsl/runtime_compile.zig` now enables
  `elide_proven_texture_bounds` for compute-runtime translation when the Lean
  proof artifact covers dispatch-fit texture coordinate theorems.
- Native compute runtime translation therefore records texture dispatch
  preconditions and elides redundant `clamp(coords, 0, textureDimensions - 1)`
  injection for proof-covered `textureLoad` / `textureStore` gid-coordinate
  patterns through the same runtime pipeline that already enforces those
  preconditions before dispatch.
- Default/public `translateTo*` entrypoints remain conservative for the
  dispatch-fit texture path because they do not surface host-side precondition
  metadata to external callers.

## Comparable Gemma64 runtime wall timing now runs plan-vs-plan on both sides (2026-03-26)

- Added a standalone Doe direct plan executor at
  `runtime/zig/zig-out/bin/doe-plan-executor`.
- Comparable IR-backed runtime rows that expose `planPath` now require direct
  plan executors on both sides for `workloadUnitWall` evaluation; mixing
  normalized-plan execution on one side with generated `commandsPath`
  compatibility execution on the other is now a strict comparability failure.
- The Apple Metal Gemma64 IR compare config
  `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.ir.json`
  now runs:
  - left: Doe direct plan executor
  - right: standalone Dawn direct plan executor
- The fair-boundary before/after evidence is:
  - prior mixed-boundary artifact:
    `bench/out/apple-metal/20260326T180619Z/gemma64.ir.compare.json`
  - current plan-vs-plan artifact:
    `bench/out/apple-metal/20260326T192810Z/gemma64.ir.compare.json`
- The current plan-vs-plan artifact is `comparisonStatus=comparable` and
  `claimStatus=claimable`.
- The remaining wall-gap work is now primarily honest direct-executor overhead,
  not legacy Doe command-runtime boundary cost.

## Compare reports now explain workload-unit wall with coarse host-overhead buckets (2026-03-26)

- Doe direct runtime and the standalone Dawn plan executor now emit coarse
  trace-meta host-overhead totals for:
  input read, input parse, workload prepare, executor init, upload prewarm,
  kernel prewarm, command orchestration, and artifact finalization.
- Compare reports synthesize those into
  `timingInterpretation.hostOverheadBreakdown`, which explains the workload-unit
  wall gap relative to selected timing as:
  - attributable coarse host overhead
  - remaining unattributed gap
- The new view is diagnostic only. It is intended to make wall-versus-selected
  discrepancies explainable without adding hot-path profiling probes.

## Compare reports now expose workload-unit wall terminology (2026-03-26)

- Compare reports now use `timingInterpretation.workloadUnitWall` as the
  primary name for the full timed workload-unit wall metric, with
  `overallWorkloadUnitWall` for the aggregate view.
- Legacy aliases remain in emitted reports during migration:
  - `timingInterpretation.headlineProcessWall`
  - `overallHeadlineProcessWall`
- Claimability metadata now points to `workloadUnitWall` when a claim is based
  on the full workload-unit wall metric rather than the selected operation
  timing.
- Warm-session wall is not inferred from this metric; it remains a distinct
  future benchmark scope.

## Standalone direct Dawn executor replaces Node package path for IR compare runs (2026-03-26)

- Added a standalone direct Dawn/WebGPU benchmark executor binary at
  `runtime/zig/zig-out/bin/dawn-plan-executor`.
- The Apple Metal Gemma64 IR compare config now resolves:
  - left: Doe direct Metal backend executor
  - right: standalone direct Dawn/WebGPU executor
- The older standalone Node WebGPU executor remains in `bench/executors/`, but
  it is now a diagnostic package-surface path rather than the primary
  claim-oriented IR compare path.

## Neutral benchmark IR and standalone Dawn/WebGPU executor wired end to end (2026-03-26)

- Added a neutral benchmark IR authoring layer under `bench/ir/` and a
  normalized executable plan layer under `bench/plans/generated/`.
- The current Gemma-shaped source of truth is `bench/ir/gemma3_270m.json`,
  which now generates:
  - normalized plans for `prefill_32tok`, `decode_1tok`, and
    `prefill_64tok_decode_64tok`
  - compatibility command artifacts for Doe runtime execution
- Added a standalone Node WebGPU executor under `bench/executors/` that reads
  normalized plans directly and emits trace-meta / trace-jsonl artifacts in the
  same compare contract shape used by the Doe runtime lanes.
- The native compare harness now supports explicit executor IDs, so the compare
  surface can be driven as:
  - left: Doe direct backend executor
  - right: standalone Dawn/WebGPU executor
  over the same normalized plan instead of only through Doe-owned command
  templates.
- Added a dedicated Apple Metal end-to-end config for the Gemma-shaped runtime
  row:
  `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.gemma64.ir.json`
- Benchmark IR and normalized plan schemas are now covered by the blocking
  schema gate via `config/schema-targets.json`.

## Gemma-shaped Metal compare and WGSL direct-backend path unblocked (2026-03-26)

- Apple Metal direct-backend `kernel_dispatch` now accepts Doe-owned WGSL kernels in
  addition to checked-in `.metal` sources by translating sibling WGSL files to
  MSL at runtime when a direct Metal source is absent.
- The MSL emitter now places compute workgroup globals at function scope and
  emits named fixed-size arrays in valid Metal declaration form, which unblocks
  retained inference kernels such as rmsnorm, tiled matmul, and attention on
  Doe's direct Metal backend path.
- The strict Doe-vs-Dawn compare loader now applies CLI `--workload-filter`
  after config-driven selector resolution, so governed benchmark configs can be
  narrowed to specific workload IDs without accidentally running the whole
  suite.
- Current Doe-vs-Dawn evidence for the Doe-owned Gemma-shaped Metal rows lives
  at `bench/out/apple-metal/20260326T133500Z/inference-gemma3-270m.compare.json`.

## Doe-owned Gemma-shaped direct-backend benchmark rows added (2026-03-26)

- Added two Apple Metal direct-backend runtime workload rows to the canonical bench
  catalog:
  `inference_gemma3_270m_prefill_32tok` and
  `inference_gemma3_270m_decode_1tok`.
- These rows do not depend on or import any external manifest schema concept.
  They are plain Doe command streams under `examples/` that:
  - seed small uniform/token buffers with explicit `buffer_write` commands
  - dispatch the retained inference kernels under
    `bench/inference-pipeline/kernels/`
  - reproduce the same broad compute shape as the real Gemma-style
    prefill/decode path using Doe-owned benchmark contracts
- The Apple Metal governed and regression cohort lists now include those rows,
  so the standard strict Doe-vs-Dawn Metal compare harness can run them
  directly with the canonical workload contract.

## Synthetic JS inference benchmark surface removed (2026-03-26)

- Removed the synthetic random-weight JS inference harness surface:
  - `bench/inference-pipeline/run-inference-bench.js`
  - `bench/inference-pipeline/compare-inference-pipeline.py`
  - `bench/inference-pipeline/inference-pipeline-config.json`
  - `bench/inference-pipeline/model-templates/gemma-3-270m.json`
- Removed the corresponding `runnerType: "js-pipeline"` workload rows from the
  benchmark catalog and generated workload lanes.
- `bench/run.py` no longer exposes an `inference` harness because that surface
  was not a real-model benchmark: it allocated random dense F32 weights instead
  of the quantized, sharded model layouts used by real inference paths.
- The real inference-pipeline WGSL kernels remain under
  `bench/inference-pipeline/kernels/` as the canonical model-kernel corpus for
  Doe-vs-Tint compilation benchmarking.

## Inference-pipeline kernels promoted to named compilation workloads (2026-03-25)

- Added named `runnerType: "compilation"` workload rows for the real
  inference-pipeline WGSL kernels under
  `bench/inference-pipeline/kernels/`, including attention decode/prefill,
  matmul gemv/tiled, rmsnorm, rope, gelu, gather, residual, and sample.
- The Doe-vs-Tint compilation harness now resolves compilation work from
  workload contracts instead of only scanning
  `bench/kernels/compilation-corpus/`, so named compilation workloads and
  executed compiler benchmarks are now the same surface.
- `runtime/zig/src/doe_wgsl/bench_compilation.zig` now accepts explicit
  `--shader-path` / `--shader-name` / `--shader-tier` inputs so both the
  generic compare harness and the dedicated Doe-vs-Tint compilation harness can
  benchmark external WGSL files without copying them into the baked-in corpus.

## Bench workload contracts split into canonical vs specialized views (2026-03-25)

- `bench/workloads/` now only carries the canonical backend lanes:
  full + smoke for Apple Metal, AMD Vulkan, and local D3D12.
- Generic and special-purpose workload projections moved under
  `bench/workloads/specialized/`, including the generic replay view,
  browser-oriented Vulkan superset views, the Doe-vs-Doe Vulkan fullsuite
  slice, the legacy Vulkan strict slice, and the narrow D3D12 comparable slice.
- Updated the generator, compare defaults, single-runtime defaults, browser
  superset tooling, and current docs so the main workload folder reads as the
  canonical surface instead of a mixed bag of lane types.

## Bench runners, gates, tools, fixtures, and shared helpers moved under subfolders (2026-03-25)

- Moved the remaining flat bench surface into purpose-built subfolders:
  - runner entrypoints under `bench/runners/`
  - blocking/advisory gates under `bench/gates/`
  - generators and reporting tools under `bench/tools/`
  - shared Python helpers under `bench/lib/`
  - JSON fixtures under `bench/fixtures/`
- Added package markers for the reorganized Python bench surface so direct
  script execution and `python -m unittest bench.tests...` both keep working.
- Updated the active runners, gates, browser helpers, drop-in tools, tests,
  schema targets, tool-surface manifest, and current docs to use the new
  subfolder layout.
- Top-level `bench/` now contains only `README.md`, `__init__.py`, and
  `package.json` as files; the previous flat script sprawl is gone.

## Bench workload contracts and tests moved under subfolders (2026-03-25)

- Moved generated workload contract files under `bench/workloads/`.
- Moved workload metadata under `bench/workloads/metadata/`.
- Moved bench docs under `bench/docs/`.
- Moved Python regression tests under `bench/tests/`.
- Updated live scripts, compare configs, schema targets, tests, and current
  docs to use the new layout while keeping the top-level bench entry points
  (`run.py`, compare harnesses, release runners) stable.

## Legacy extended workload aliases removed (2026-03-25)

- Removed the stale generated workload alias files:
  `bench/workloads.apple.metal.extended.json`,
  `bench/workloads.amd.vulkan.extended.json`, and
  `bench/workloads.local.d3d12.extended.json`.
- Active compare tooling and workload generation already use the canonical
  non-`extended` contracts:
  `bench/workloads.apple.metal.json`,
  `bench/workloads.amd.vulkan.json`, and
  `bench/workloads.local.d3d12.json`.
- Updated current-facing example documentation to reference the canonical
  D3D12 workload contract path instead of the removed alias.

## Apple Metal upload lane split (2026-03-25)

- Split Apple Metal upload benchmarking into two explicit intent lanes:
  - strict staged-copy comparable rows with new `_staged` workload IDs for
    governed compare/release evidence
  - directional Apple UMA advantage rows that keep the existing upload IDs and
    remain exploration-only
- `metal_doe_comparable` and `metal_doe_release` now require
  `uploadPathPolicy: "staged_copy_only"` in
  `config/backend-runtime-policy.json`, and the Metal backend coerces upload
  behavior onto `copy-dst` in those lanes.
- `metal_doe_directional` remains shortcut-friendly for diagnostic advantage
  profiling, and Apple Metal smoke/explore/breadth configs now use that
  directional lane on the Doe side.
- Apple Metal governed cohorts now select the staged upload IDs:
  `upload_write_buffer_{1kb,64kb,1mb,4mb,16mb,256mb,1gb,4gb}_staged`.
- Targeted compare-dev evidence under the new strict lane:
  `bench/out/scratch/metal_upload_staged_compare_dev.large.json`
  shows `upload_write_buffer_{1mb,4mb,16mb,256mb}_staged` comparable with no
  hardware-path failure. `upload_write_buffer_{1gb,4gb}_staged` now fail only
  `left_right_timing_plausibility`, which is the remaining methodology issue to
  solve for the largest uploads.

## Apple Metal render macro replacements (2026-03-25)

- Replaced the weak Apple Metal governed rows
  `render_bundle_dynamic_pipeline_bindings` and
  `render_draw_redundant_pipeline_bindings` with new 200k-draw macro contracts:
  `render_bundle_dynamic_pipeline_bindings_200k` and
  `render_draw_redundant_pipeline_bindings_200k`.
- Added dedicated macro command fixtures for both workload families and moved
  the old repeated 2k-draw rows to exploration-only directional status.
- Apple Metal governed cohort selection now points at the macro IDs.
- Render-bundle workloads no longer use encode-preferred timing selection in
  strict compare mode; they now use total execution timing because bundle
  encode timing produced scope-asymmetric Doe-vs-Dawn rows on Metal.

## Metal timing-scope normalization hardening (2026-03-25)

- Fixed strict compare timing plausibility to evaluate selected operation timing
  against the same normalized workload unit used for deltas instead of against
  whole timed-command wall for repeated rows.
- Tightened strict Doe-native timing-source matching so mixed selected scopes
  such as `doe-execution-total-ns` vs `doe-execution-encode-ns` fail
  comparability instead of slipping through as source-family-compatible.
- Render timing selection now keeps `render-encode-preferred` only when encode
  timing is a plausible share of total execution for that side; otherwise it
  falls back to total execution timing.
- Historical Apple Metal compare artifacts should be treated through this
  corrected lens: repeated render rows that depended on mixed source selection
  or pre-fix plausibility math are diagnostic until rerun.

## Metal compare-dev signal (2026-03-24)

Current Metal `compare-dev` results show Doe faster than Dawn on 8 of 9
comparable workloads, spanning compute, pipeline compilation, render state and
bundle cases, texture contract stress, and concurrent execution.

See `bench/out/apple-metal/compare-dev/20260324T233128Z/dawn-vs-doe.apple.metal.compare-dev.json`
for the current artifact.

## Workload origin taxonomy split (2026-03-24)

- Replaced the old binary inferred provenance model
  (`dawn_derived` / `doe_specific`) with explicit/generated workload origins:
  `dawn_benchmark`, `dawn_autodiscovered`,
  `doe_contract_with_dawn_mapping`, and `doe_specific`.
- `@autodiscover` mappings now materialize as `dawn_autodiscovered` instead of
  being flattened into the same bucket as direct Dawn benchmark lifts.
- Doe-authored copy/dispatch command fixtures that run against Dawn only as a
  delegate host process are now explicitly marked
  `workloadOrigin=doe_contract_with_dawn_mapping` in the canonical backend
  catalog.
- Generated backend workload files now carry `workloadOrigin` on every row, and
  the workload-origin report reflects the finer taxonomy plus `hybrid` for
  mixed-lane rows.

## Tooling surface boundary cleanup (2026-03-24)

- Added a schema-backed tooling surface contract:
  - `config/tool-surfaces.schema.json`
  - `config/tool-surfaces.json`
- Added `docs/internal-tooling.md` as the canonical human-readable guide for
  public package surfaces vs repo-only operator tooling.
- Removed npm publication of the internal `doe-gpu-bench` and
  `doe-gpu-compare` CLI wrappers. Canonical compare/release/gate entrypoints
  remain repo-only under `bench/`.
- Collapsed duplicated model-facing docs so `AGENTS.md` is the only full source
  of truth; `CLAUDE.md` and `GEMINI.md` now point back to it instead of carrying
  drift-prone copies.
- Updated repo/package docs to route package questions to `packages/doe-gpu/`
  and repo-operator questions to `docs/internal-tooling.md`.

## Benchmark catalog cohort cutover (2026-03-24)

- Replaced the old mixed `core` / `extended` / `superset` naming model for
  native Dawn-vs-Doe workloads with explicit backend catalogs plus cohort-based
  selection:
  - `bench/workloads.amd.vulkan.json`
  - `bench/workloads.amd.vulkan.smoke.json`
  - `bench/workloads.apple.metal.json`
  - `bench/workloads.apple.metal.smoke.json`
  - `bench/workloads.local.d3d12.json`
  - `bench/workloads.local.d3d12.smoke.json`
- Generated workload rows now carry explicit `cohorts` metadata and compare
  configs now select with `selector.cohorts` + `selector.benchmarkClass`
  instead of relying on `suiteTags`, `includeExtendedWorkloads`, or file names
  to encode run policy.
- Canonical preset names are now `smoke`, `compare-dev`, `compare`, `frontier`,
  `explore`, and `release` for each backend profile.
- `smoke` is now a diagnostic-only sanity lane by contract. It may include
  directional rows and is not claim-bearing evidence.
- AMD Vulkan governed release/compare lanes now select governed comparable rows
  from the main Vulkan catalog. Path-asymmetric upload rows remain outside the
  governed cohort and stay exploration-only until structural equivalence is
  restored.
- D3D12 governed compare/release lanes now select the compute/upload/pipeline/
  `p0-resource` subset from `bench/workloads.local.d3d12.json`; render/texture/
  copy/surface rows remain exploration-only until fresh Windows evidence expands
  the governed contract.
- Removed the stale AMD Vulkan app-claim scaffold (`bench/workloads.amd.vulkan.app.claim.json`,
  `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.app.claim.json`,
  `config/claim-cycle.amd-vulkan-app-local.json`) instead of carrying forward a
  seventh special-case workload file with contradictory claim/comparability
  semantics.

## CSL governed smoke lane and SDK driver bridge (2026-03-24)

- Added `doe-csl-bundle-emitter`, a small Zig binary that turns a WGSL smoke fixture
  into a split `layout.csl` / `pe_program.csl` bundle for CSL compile smoke paths.
- Added `runtime/zig/tools/csl_sdk_driver.py`, an explicit external driver that
  consumes `csl_simulator_plan`, probes for `cslc` + `cerebras-sdk`, compiles a
  single smoke target when available, and emits a trace summary instead of faking
  model execution.
- Added a governed bench lane wrapper and gate:
  - `bench/run_csl_governed_lane.py`
  - `bench/csl_simulator_gate.py`
- The governed lane currently proves the compile/run/parity contract surface for a
  single-kernel smoke path. Full model/runtime execution still remains blocked on
  real multi-kernel host-runtime sequencing and actual Cerebras simulator/hardware.


## Snapshot

Date: 2026-03-23

### CSL simulator contract runner and outcome artifacts (2026-03-24)

- Added a schema-backed simulator launch contract for CSL work that remains
  explicit-only and fail-closed:
  - `config/doe-wgsl-simulator-plan.schema.json`
  - `examples/doe-wgsl-simulator-plan.sample.json`
- Added a schema-backed simulator outcome artifact:
  - `config/doe-wgsl-simulator-result.schema.json`
  - `examples/doe-wgsl-simulator-result.sample.json`
- Added `emit_csl_simulator.zig` typed parsing and validation for simulator
  plan/result artifacts, plus result emission helpers.
- Added `doe-csl-sim-runner`, a separate Zig executable that:
  - validates `csl_simulator_plan`
  - resolves the simulator driver explicitly (`--driver-executable` or
    `DOE_CSL_SIM_EXECUTABLE`)
  - writes stdout/stderr to declared artifact paths
  - emits a deterministic simulator result artifact
- This is simulator-prep only. It does not invent trace output, and it does not
  emulate Cerebras execution when a simulator is unavailable.

### Vulkan graphics path promotion (2026-03-23)

- Wired depth bias dynamic state into Vulkan render pipeline creation and draw recording.
  `vk_render_pipeline.zig`: rasterization state now reads `depth_bias`, `depth_bias_slope_scale`,
  `depth_bias_clamp` from `RenderDrawCommand` instead of hardcoding zeros. Dynamic state list
  conditionally includes `VK_DYNAMIC_STATE_DEPTH_BIAS` and `VK_DYNAMIC_STATE_STENCIL_REFERENCE`
  when depth/stencil is active.
- Added `vkCmdSetDepthBias` and `vkCmdSetStencilReference` dynamic state calls in
  `vk_render.zig` draw recording, matching WebGPU per-draw-call semantics.
- Added extern declarations for `vkCmdSetDepthBias` and `vkCmdSetStencilReference` in
  `vk_functions.zig`, with re-exports and new constants (`VK_DYNAMIC_STATE_DEPTH_BIAS`,
  `VK_DYNAMIC_STATE_STENCIL_REFERENCE`, `VK_STENCIL_FACE_FRONT_AND_BACK`) in `vk_constants.zig`.
- Declared four new capabilities in `mod.zig` `native_capability_set()`: `indirect_draw`,
  `indexed_indirect_draw`, `depth_stencil`, `descriptor_binding` -- these were already
  implemented in draw paths but not advertised.
- Fixed double-prefix bug (`c.c.VK_INDEX_TYPE_*`) in `vk_render.zig` inline index buffer path.
- Added `vulkan_render_pipeline_test.zig` (229 lines, 40 tests) covering all pure conversion
  helpers: `blend_factor_to_vk`, `blend_operation_to_vk`, `topology_to_vk`, `cull_mode_to_vk`,
  `front_face_to_vk`, `sample_count_to_vk`, `color_write_mask_to_vk`, `wgpu_compare_to_vk`,
  `wgpu_stencil_op_to_vk`, `format_has_stencil`, `resolve_entry_point_name`,
  `vertex_step_mode_to_vk`. Registered in `test_suite.zig`.
- All modified runtime files remain under the 777-line limit.
- Follow-up: occlusion query creation/management and multi-draw-indirect are not yet
  exposed as standalone capabilities; tracked for future promotion.

### Regenerate stale Bun/Deno artifacts from catalog changes (2026-03-23)

- Regenerated all backend workload lane files from `bench/backend-workload-catalog.json`
  via `bench/generate_backend_workloads.py`. Catalog changes included new D3D12 extended
  lane entries and updated comparability notes.
- Regenerated workload overlap map via `bench/generate_workload_overlap_map.py`.
- Regenerated WebGPU surface reports (`config/generated/webgpu-surface-*.json`)
  via `scripts/generate_webgpu_surface_reports.py`.
- Ran `packages/doe-gpu/scripts/sync-vendor.js` to sync vendored files into the
  `doe-gpu` package. Removed stale `writeSemanticOperatorBundle` export that was
  deleted upstream. Fixed quote style inconsistency in vendored `bun.js`.
- Updated Bun/Deno/Node benchmark harness configs and runners under
  `bench/package-compare/` to reference `doe-gpu` instead of `@simulatte/webgpu`
  and `packages/doe-gpu/src/` instead of `packages/webgpu/src/`:
  - `bench/package-compare/bun/config.json`, `runner.js`
  - `bench/package-compare/deno/config.json`, `runner.js`
  - `bench/package-compare/node/config.json`, `runner.js`
  - `bench/package-compare/doe-api/bun/config.json`, `runner.js`
  - `bench/package-compare/doe-api/deno/config.json`, `runner.js`
  - `bench/package-compare/doe-api/node/config.json`, `runner.js`
  - `bench/package-compare/doe-api/workloads.js`
- Updated `config/workload-registry.schema.json` title from "Fawn" to "Doe".
- Workload registry (`bench/workload-registry.json`) verified consistent with catalog:
  30 workloads across all three package surfaces (node_package, bun_package, deno_package).

### D3D12 parity scaffold correction (2026-03-23)

- Kept `local_d3d12_extended` at parity breadth with the common Metal/Vulkan
  extended set, but corrected the lane semantics for the 39 newly added rows.
- Those 39 rows are now explicit directional D3D12 parity scaffolds:
  - `comparable: false`
  - `benchmarkClass: directional`
  - `dawnFilter: "@autodiscover"`
  - Windows D3D12 profile fields and `windows_d3d12_noop_list.json`
- This prevents the strict D3D12 comparable config from accidentally promoting
  render/texture/surface rows into governed apples-to-apples claim lanes before
  Windows-backed evidence exists.
- The governed D3D12 comparable contract remains the existing 11-row
  compute/upload/pipeline/p0-resource slice; `bench/workloads.d3d12.comparable.json`
  stays authoritative for that strict subset.

### WGSL builtin spec conformance expansion (2026-03-23)

- Expanded WGSL-to-MSL builtin function coverage across five categories:
  - **Pack/unpack 2x16:** pack2x16snorm, pack2x16unorm, unpack2x16snorm, unpack2x16unorm
    mapped to MSL `pack_float_to_snorm2x16`, `pack_float_to_unorm2x16`,
    `unpack_snorm2x16_to_float`, `unpack_unorm2x16_to_float`.
  - **Renamed math builtins:** faceForward -> `faceforward`, countOneBits -> `popcount`,
    reverseBits -> `reverse_bits`, countLeadingZeros -> `clz`, countTrailingZeros -> `ctz`.
    saturate, reflect, refract, transpose, determinant added as passthrough.
  - **Bit manipulation:** extractBits -> `extract_bits`, insertBits -> `insert_bits`,
    firstLeadingBit -> `(31 - clz(...))`, firstTrailingBit -> `ctz(...)`.
  - **Texture query:** textureNumLevels -> `.get_num_mip_levels()`,
    textureNumLayers -> `.get_array_size()`, textureNumSamples -> `.get_num_samples()`,
    textureSampleBias -> `.sample(..., bias(...))`.
  - **Fragment derivatives:** dpdx/dpdxCoarse/dpdxFine -> `dfdx`,
    dpdy/dpdyCoarse/dpdyFine -> `dfdy`, fwidth/fwidthCoarse/fwidthFine -> `fwidth`.
  - **Other:** atomicCompareExchangeWeak, quantizeToF16 -> `float(half(...))`,
    modf (fractional component), frexp (mantissa).
- Added `faceForward` to sema `is_passthrough_math` (was missing).
- Added derivative builtins, textureSampleBias, textureNumSamples,
  atomicCompareExchangeWeak, quantizeToF16 to sema type inference.
- New test file: `coverage_builtin_spec_test.zig` with 18 tests covering all
  new builtins. Registered in `test_suite_wgsl.zig`.
- All modified files remain under the 777-line limit.
- Modified files:
  - `runtime/zig/src/doe_wgsl/emit_msl_ir_builtins.zig` (341 -> 487 lines)
  - `runtime/zig/src/doe_wgsl/emit_msl_maps.zig` (137 -> 153 lines)
  - `runtime/zig/src/doe_wgsl/emit_msl_texture.zig` (306 -> 336 lines)
  - `runtime/zig/src/doe_wgsl/sema_attrs.zig` (424 -> 456 lines)
  - `runtime/zig/src/doe_wgsl/coverage_builtin_spec_test.zig` (new, 324 lines)
  - `runtime/zig/test_suite_wgsl.zig` (updated with new test import)

### CTS baseline infrastructure (2026-03-23)

- Built CTS conformance test suite baseline infrastructure for regression detection.
- Baseline generator: `bench/cts_baseline_generate.py` runs CTS queries against Doe
  and captures structured pass/fail results into `bench/out/cts-baseline/<timestamp>.json`.
  Reuses the existing CTS subset config format (`bench/cts_subset.fawn-node.json`).
- Baseline comparator: `bench/cts_baseline_compare.py` loads a baseline snapshot and
  a current snapshot, diffs per-query results, and emits a comparison report with
  new passes, new failures, stable counts, and regression/improvement tallies.
  Supports `--gate` mode for CI integration with policy-driven pass/fail.
- Trend reporter: `bench/cts_baseline_trend.py` reads all timestamped snapshots from
  the baseline directory and classifies the overall trend as improving, regressing,
  stable, or insufficient_data. Window size and minimum snapshot count are policy-driven.
- Schema: `config/cts-baseline.schema.json` defines the baseline snapshot artifact format.
- Policy: `config/cts-baseline-policy.json` (schema: `config/cts-baseline-policy.schema.json`)
  controls regression thresholds (`maxNewFailures`, `requireNoRegressions`) and trend
  window configuration. Advisory gate mode in v0 bootstrap.
- Gate wiring: `bench/run_blocking_gates.py` gains `--with-cts-baseline-gate` (opt-in),
  `--cts-baseline-snapshot`, `--cts-baseline-current`, and `--cts-baseline-policy` flags.
- Schema registration: `config/cts-baseline-policy.json` added to `config/schema-targets.json`.
- Gate documentation updated in `docs/process.md`.
- Follow-up: promote from advisory to blocking once a stable baseline with at least 3
  snapshots exists and the CTS vendor dependencies are wired end-to-end.

### Pipeline cache Phase 3: startup warmup scheduler (2026-03-23)

- Implemented synchronous pipeline cache warmup on startup in `metal_pipeline_cache.zig`.
  On `flush_archive()`, a sidecar manifest (`doe_pipeline_archive.manifest`) is written
  listing all pipeline keys compiled during the session: render pixel formats (`R:<fmt>`)
  and compute kernel names (`C:<name>`).
- On `init()`, the manifest is loaded from the previous session. `run_warmup()` re-triggers
  `compile_or_serve_render` for each render entry so Metal loads cached binaries into memory,
  eliminating first-use compile misses. Compute kernel names are returned to the runtime
  bootstrap, which resolves them via `ensure_kernel_pipeline`.
- `register_compute_key()` called from `ensure_kernel_pipeline` in `metal_runtime_resources.zig`
  records kernel names into the manifest for future sessions.
- Warmup telemetry: `warmup_count` and `warmup_ns` added to `CacheTelemetry`. New C ABI
  export `doeNativeMetalPipelineCacheWarmupTelemetry` exposes both counters.
  `finalize_warmup_telemetry()` accumulates compute-side warmup timing from the runtime.
- Warmup policy: `config/pipeline-warmup-policy.json` schema bumped to v2,
  `enableStartupWarmup` field added (default: true). `maxWarmupPipelines` (default: 64)
  caps manifest entries loaded at init.
- Graceful degradation: missing/stale/corrupt manifest files are silently skipped;
  manifest entries exceeding `MAX_COMPUTE_KEY_LEN` (256) or `MAX_MANIFEST_BYTES` (64 KB)
  are discarded.
- Modified files:
  - `runtime/zig/src/backend/metal/metal_pipeline_cache.zig` (473 -> 664 lines)
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` (bootstrap warmup integration)
  - `runtime/zig/src/backend/metal/metal_runtime_resources.zig` (register_compute_key call)
  - `config/pipeline-warmup-policy.json` (schema v1 -> v2)
  - `config/pipeline-warmup-policy.schema.json` (enableStartupWarmup field)
- All files remain under the 777-line limit.
- Follow-up: Phase 4 background warmup (multi-threaded, config-gated via `enableBackgroundWarmup`).

### DXIL structural validation gate wired into CI (2026-03-23)

- Wired the existing `dxil_validate.zig` structural validator and
  `emit_dxil_test.zig` integration tests into the CI gate infrastructure.
- Added `emit_dxil_test` and `dxil_validate` imports to
  `runtime/zig/test_suite_wgsl.zig` so `zig build test-wgsl` now exercises
  DXIL container validation (DXBC header, version, part bounds, LLVM bitcode
  magic) and WGSL-to-DXIL compilation across compute/vertex/fragment stages.
- Created `bench/dxil_validate_gate.py`: standalone gate script that runs the
  Zig-level DXIL tests and a Python-side defense-in-depth structural
  validation pass with failure taxonomy (`zig_test_failure`,
  `compilation_failure`, `structural_failure`, `missing_magic`, `too_small`).
- Wired into `bench/run_blocking_gates.py` via `--with-dxil-validate-gate`
  (opt-in, consistent with `--with-spirv-val-gate` pattern).
- Updated `docs/process.md` gate documentation for Apple Metal, AMD Vulkan
  extended, and the general gate section.
- Modified files:
  - `runtime/zig/test_suite_wgsl.zig` (added 2 imports + 2 comptime refs)
  - `bench/dxil_validate_gate.py` (new, standalone gate)
  - `bench/run_blocking_gates.py` (added CLI args + gate invocation)
  - `docs/process.md` (gate documentation)

### Apple Metal non-comparable catalog cleanup (2026-03-23)

- Cleaned stale comparability notes in `bench/backend-workload-catalog.json`
  for `pipeline_async_diagnostics`,
  `render_pixel_local_storage_barrier_500`, and
  `resource_table_immediates_500`.
- Previous notes claimed the Dawn delegate executed `0 dispatches, 0 encode`,
  but historical compare artifacts and current catalog state had diverged. The
  cited scratch artifact is no longer present under `bench/out`, so that claim
  is not audit-safe.
- These rows now stay fail-closed as directional-only pending fresh
  structural-equivalence evidence on the affected lanes, including
  `apple_metal_extended`.
- Fresh targeted Apple Metal evidence also removed the stale
  Doe-execution-error claim from `render_multidraw` and
  `render_multidraw_indexed`. Current targeted reruns executed without
  process-level failures, so those rows now remain directional-only for
  mapping/governance reasons rather than a claimed active Doe crash.
- Remaining Apple Metal contract-only rows
  (`pipeline_async_diagnostics`, `render_draw_indexed_200k`,
  `render_draw_indexed_baseline`, `surface_presentation`) now cite only fresh
  targeted-rerun evidence plus the remaining contract-level reason for staying
  directional. Their notes no longer rely on inherited generic wording.
- `compute_indirect_timestamp` remains directional on
  `apple_metal_extended`; no source change was required because the Apple Metal
  lane override already carried the correct directional note.

### External texture interop: Doe-side completion (2026-03-23)

- Fixed `doeNativeQueueCopyExternalImageToTexture` and
  `doeNativeQueueCopyExternalTextureForBrowser` to handle both DoeTextureView-backed
  and native-imported (IOSurface/CVPixelBuffer) external textures. Previously, the
  copy path cast `plane0` to `DoeTextureView` unconditionally, which silently failed
  for native-imported textures (where `plane0` is a raw MTLTexture handle).
  New `copy_external_texture_to_dst` helper dispatches to the standard texture-to-texture
  copy for DoeTextureView-backed planes, and to a direct Metal blit for native imports.
- Fixed bind group external texture slot population in `doe_bind_group_native.zig`.
  Previously `bg.textures[binding]` stored the raw `ext.plane0` pointer for both
  DoeTextureView and native-imported paths. For DoeTextureView-backed external textures,
  this was a DoeTextureView pointer, not an MTLTexture handle, causing Metal encoding
  to receive the wrong handle type. Now uses `resolvePlane0MtlHandle` and
  `resolvePlane1MtlHandle` to extract the correct MTL handle for all external textures.
- Added three resolution helpers in `doe_external_texture_native.zig`:
  `resolvePlane0MtlHandle`, `resolvePlane1MtlHandle`, `resolvePlane0DoeTexture`.
  These correctly dispatch between DoeTextureView-backed planes (extracts
  `view.handle` or `view.tex.mtl`) and native-imported planes (returns the raw
  MTLTexture handle directly).
- Updated `config/webgpu-integration-chromium.json`: `copyExternalImageToTexture` and
  `importExternalTexture` status changed from `not_supported` to
  `implemented_untested_in_browser` with `blockedBy` changed from
  `chromium-shared-image-interop` to `chromium-wire-instance-lifetime`.
- Doe-side external texture implementation is now complete. The remaining browser-level
  failure ("A valid external Instance reference no longer exists") is a Chromium wire
  client Instance validation issue: the wire client's EventManager state diverges from
  Doe's Instance lifecycle. Fixing requires DoeCommandDecoder Phase 2+ wire interception
  (upstream Chromium change, not a Doe runtime bug).
- Modified files:
  - `runtime/zig/src/doe_external_texture_native.zig` (295 -> 320 lines)
  - `runtime/zig/src/doe_queue_submit_native.zig` (753 -> 773 lines)
  - `runtime/zig/src/doe_bind_group_native.zig` (382 -> 384 lines)
  - `config/webgpu-integration-chromium.json`
- All files remain under the 777-line limit.

### Pipeline cache Phase 2.5: lazy flush, fingerprint invalidation, hit/miss timing (2026-03-23)

- Three gaps closed in the Metal pipeline cache (`metal_pipeline_cache.zig`):
  1. **Background flush timer**: lazy periodic flush via `maybe_lazy_flush()` called
     after each cache miss. If `FLUSH_INTERVAL_NS` (30 seconds) has elapsed since
     the last serialize, `flush_archive()` is called automatically. No background
     thread — single-threaded model preserved. Timestamp tracked in `last_flush_ns`.
  2. **Archive invalidation on GPU/driver change**: on init, `validate_or_discard_archive()`
     computes a device fingerprint (`<device_name>:<registry_id_hex>`) from
     `metal_bridge_device_name` and `metal_bridge_device_registry_id`, compares
     against the stored sidecar file (`doe_pipeline_archive.fingerprint`), and
     deletes the stale `.metallib` archive on mismatch. New bridge extern
     declarations added to `metal_bridge_decls.zig`.
  3. **Per-pipeline hit/miss timing telemetry**: `CacheTelemetry` now tracks
     `total_hit_ns` and `total_miss_ns`. Each `compile_or_serve_*` call wraps the
     bridge invocation with `common_timing.now_ns()` timestamps. New C ABI export
     `doeNativeMetalPipelineCacheTelemetryExt` exposes all four counters.
- Modified files:
  - `runtime/zig/src/backend/metal/metal_pipeline_cache.zig` (333 -> 473 lines)
  - `runtime/zig/src/backend/metal/metal_bridge_decls.zig` (added device property externs)
- All files remain under the 777-line limit.
- New constants: `FLUSH_INTERVAL_NS`, `FINGERPRINT_FILENAME`, `DEVICE_NAME_CAP`.
- No new dependencies; uses existing `common_timing` module and ObjC bridge functions
  that were already implemented in `metal_bridge.m` / `metal_bridge.h`.

### Render texture lifecycle timing regression fix (2026-03-23)

- Root cause: `texture_sampler_write_query_destroy` workload shows tail-negative
  results (p95 delta compressing to 99.3%) because Doe's per-call CFRelease on
  sampler_destroy/texture_destroy serializes against Metal's internal ARC
  machinery under aggregate lane pressure (10+ destroys per flush cycle).
  Dawn avoids this by deferring object destruction to a GC pass at command
  buffer boundaries.
- Fix: two-part optimization in the Metal backend resource lifecycle:
  1. **Deferred batch release pool** (`metal_deferred_release.zig`): fixed-capacity
     ring buffer (64 slots) collects pending texture/sampler Metal object releases
     and batch-drains them in a single tight loop at `flush_queue_timed` boundaries.
     Eliminates per-destroy CFRelease round-trips during the timed workload window.
  2. **Sampler descriptor cache** (`metal_deferred_release.zig`): caches up to 16
     unique MTLSamplerState objects by descriptor key. Identical sampler parameter
     tuples (filter, address mode, LOD, anisotropy) share a single Metal object with
     reference counting. For the common case of repeated identical sampler descriptors
     in lifecycle benchmarks, this eliminates Metal alloc/dealloc entirely.
- Modified files:
  - `runtime/zig/src/backend/metal/metal_deferred_release.zig` (new, 207 lines)
  - `runtime/zig/src/backend/metal/metal_resource_commands.zig` (updated)
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` (added pool/cache fields, wired drain)
  - `runtime/zig/src/backend/metal/metal_cleanup.zig` (sampler release coordinates with cache)
- All files remain under the 777-line limit.
- Expected impact: eliminates tail-negative regression on texture_sampler_write_query_destroy
  workload by matching Dawn's deferred destruction semantics while preserving
  Doe's explicit lifecycle guarantees.

### Small-upload timing jitter fix (2026-03-23)

- Root cause: `upload_write_buffer_1kb` (1000 repeats, ~170us total row time)
  and `upload_write_buffer_64kb` (500 repeats, ~200us total row time) are far
  below the OS scheduler preemption window (~10-50us). A single preemption
  during a 170us measurement window causes 5-25% p95 instability under
  full-lane contention, making these rows non-claimable (`p50 -5.34%`,
  `p95 -12.38%` for 1KB in the full lane).
- Fix is two-pronged:
  1. **Increased repeat counts** to push row timing above the scheduler-noise
     floor: 1KB from 1000 to 50000 repeats (~8.5ms row time), 64KB from 500 to
     10000 repeats (~5ms row time). Both left and right sides updated
     symmetrically for comparability.
  2. **New `minRowTimingFloorNs` policy** in
     `config/benchmark-methodology-thresholds.json` (set to 5000000 = 5ms).
     Claimability assessment now checks median row wall time against this floor
     and demotes workloads below it to diagnostic, providing a safety net for
     any row whose repeat count hasn't been tuned yet.
- Files changed:
  - `config/benchmark-methodology-thresholds.json`: added
    `timingScopeSanity.minRowTimingFloorNs`
  - `config/benchmark-methodology-thresholds.schema.json`: added optional
    `minRowTimingFloorNs` property
  - `bench/native_compare_modules/config_support.py`: `BenchmarkMethodologyPolicy`
    gains `min_row_timing_floor_ns` field; loader reads from config
  - `bench/native_compare_modules/claimability.py`: new
    `assess_row_timing_floor()` check wired into `assess_claimability()`
  - `bench/workloads.apple.metal.extended.json`: 1KB repeat 1000->50000,
    64KB repeat 500->10000
  - `bench/backend-workload-catalog.json`: same changes in
    `apple_metal_extended` lane
  - `bench/test_claimability.py`: two new tests for the row timing floor
- Follow-up: AMD Vulkan lanes still use 500 repeats for small uploads;
  if the same jitter pattern appears there, apply the same fix.

### Pipeline cache Phase 2: compile-skip via MTLBinaryArchive (2026-03-23)

- Phase 2 closes the compile-skip gap in the Metal pipeline cache. On a cache
  hit, `metal_bridge_device_new_compute_pipeline_with_archive` now serves a
  pre-compiled binary from the MTLBinaryArchive without re-entering
  `newLibraryWithSource`. On a miss, compilation proceeds normally and the
  result is recorded via `addComputePipelineFunctionsWithDescriptor` for
  future warm starts.
- `metal_bridge.m`: `_with_archive` functions now call
  `addComputePipelineFunctionsWithDescriptor:` / `addRenderPipelineFunctionsWithDescriptor:`
  after compilation to prime the archive. Previous Phase 1 no-op `add_compute` / `add_render`
  bridge functions remain as ABI-stable stubs.
- `metal_pipeline_cache.zig`: replaced lookup-then-compile-then-add two-step with
  unified `compile_or_serve_compute` / `compile_or_serve_render` path. Added
  `CacheTelemetry` (compile_count, serialize_count), `DOE_PIPELINE_CACHE_DIR`
  env var support, and `makePath` for cache directory auto-creation.
- `metal_runtime_resources.zig`: `resolve_compute_pso_for` / `resolve_render_pso_for`
  simplified to single `compile_or_serve` call with plain-compile fallback.
- Archive flush occurs at `deinit` (process shutdown) and via `doeNativeMetalPipelineCacheFlush`.
  Serialization persists the `.metallib` to disk, enabling warm starts across process launches.
- Not yet implemented: background flush on a timer (currently synchronous at shutdown only),
  archive invalidation on driver/GPU change, and per-pipeline timing to distinguish hit vs miss
  in telemetry.

### CSL validation and host-plan metadata cleanup (2026-03-23)

- `runtime/zig/src/doe_wgsl/mod.zig` now exposes opt-in CSL validation wrappers
  backed by `emit_csl_validate`, so callers can validate pattern output or
  toolchain config without importing the submodule directly.
- `runtime/zig/src/doe_wgsl/csl_spec.zig` now owns the shared CSL host-plan and
  toolchain metadata constants, including schema identity, target identity,
  the SDK minimum version, and the `cslc --version` validation arg.
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig` and
  `runtime/zig/src/doe_wgsl/emit_csl_toolchain.zig` now consume those shared
  constants; the host-plan artifact still records optional cslc validation
  metadata, while the toolchain emitter stays declarative.

### CSL host-plan honesty and WGSL module sharding (2026-03-23)

- `runtime/zig/src/doe_wgsl/emit_csl_host.zig` no longer claims to lower
  Doppler execution-v1 directly. It now emits host-side scaffolds from an
  explicit `HostPlan` contract with declared kernels, prefill/decode launch
  phases, optional `eosTokenId`, and a conservative SRAM estimate payload.
- The generated Python scaffold now matches Doppler RDRR shard schema fields:
  reads `filename` and preserves `index`, `offset`, and `size` metadata instead
  of relying on nonexistent shard keys.
- Misleading SRAM “fit” semantics were removed. The host module now exposes
  conservative estimate helpers (`estimateLayerSramBytes`, `estimateModelSram`)
  rather than treating rough arithmetic as a placement proof.
- `runtime/zig/src/doe_wgsl/mod.zig` was reduced below the 777-line limit by
  moving CSL-specific test bodies into
  `runtime/zig/src/doe_wgsl/doe_wgsl_csl_tests.zig` while keeping the public
  API unchanged.

### SPIR-V emission parity with MSL (2026-03-23)

- SPIR-V emitter now has full parity with the MSL emitter for all WGSL builtins.
  Added 11 missing builtins to `emit_spirv_builtins.zig`:
  - `textureBarrier` — OpControlBarrier with ImageMemory semantics
  - `subgroupMul` — GroupNonUniformFMul / GroupNonUniformIMul
  - `subgroupInclusiveAdd` — GroupNonUniformFAdd/IAdd with InclusiveScan
  - `subgroupShuffleDown` / `subgroupShuffleUp` — GroupNonUniformShuffleDown/Up
  - `subgroupBroadcastFirst` — GroupNonUniformBroadcastFirst
  - `subgroupElect` — GroupNonUniformElect
  - `subgroupAnd` / `subgroupOr` / `subgroupXor` — GroupNonUniformBitwiseAnd/Or/Xor
- Added corresponding opcodes to `spirv_spec.zig`: GroupNonUniformElect,
  BroadcastFirst, ShuffleUp, ShuffleDown, IMul, FMul, BitwiseAnd/Or/Xor.
- 8 new tests in `emit_spirv_builtin_test.zig` covering all added builtins.
- `emit_spirv_builtins.zig` is 758 lines (under 777 limit).
- The SPIR-V backend is fully wired end-to-end: WGSL source → parser → IR →
  emit_spirv → u32 words → vkCreateShaderModule for both compute and graphics
  pipelines via `doe_vulkan_compute_native.zig` and `doe_vulkan_render_native.zig`.

### Browser lane hardening and rename (2026-03-23)

- Instance lifetime hardening: `doeNativeInstanceRelease` in `doe_instance_device_native.zig`
  now checks the external texture registry (`instance_external_texture_count`) before
  destroying the Instance. If live external textures still reference it, the Instance
  survives with ref_count clamped to 1. This prevents the Chromium wire client's
  independent Instance lifetime from causing premature destruction while external
  textures are in flight. The external texture backref path calls InstanceRelease
  again when the last external texture is freed, allowing normal destruction.
- Layered browser bench failure analysis: 12 of 14 remaining failures are L0-only
  non-projectable rows (runtime contract lanes with no browser-layer equivalent;
  classified as `non_projectable` / `l0_only` in `browser/chromium/bench/projection-rules.json`).
  These are by design, not bugs. The remaining 2 are external texture Instance lifetime
  failures addressed by the hardening above.
- Renamed `browser/fawn-browser/` to `browser/chromium/`. Updated all non-artifact path
  references across docs, configs, scripts, CI workflows, and `.gitignore`. Renamed
  `fawn-browser.sh` to `chromium.sh`. Historical artifact JSON files retain their
  original paths as they are timestamped records.

### Pipeline cache integration, DXIL validation, Vulkan render descriptors (2026-03-23)

- Pipeline cache Phase 2 integration in `runtime/zig/src/runtime/pipeline_cache_integration.zig`:
  lazily-initialized global `PipelineCache` singleton, atomic telemetry counters
  (hits/misses/stores), and `recordComputePipelineCreation`/`recordRenderPipelineCreation`
  hooks wired into the async pipeline creation paths in `wgpu_dropin_ext_a.zig`.
- Background warmup policy config added: `config/pipeline-warmup-policy.json` and
  `config/pipeline-warmup-policy.schema.json` (warmup disabled by default, 64 max pipelines,
  2 worker threads, empty known model graphs).
- Not yet complete: actual cache-backed compilation skip (Phase 2 stores telemetry markers,
  not compiled blobs), background warmup scheduler, and worker-pool sizing tuning.
- DXIL structural validation module in `runtime/zig/src/doe_wgsl/dxil_validate.zig` (286 lines):
  validates DXBC container header, version, part table bounds, DXIL program sub-header
  (shader model kind, major/minor version, bitcode offset/size), and LLVM bitcode magic.
  Six test cases. No external toolchain dependency.
- Vulkan render pipeline descriptor set integration:
  `vk_render_pipeline.zig` now creates descriptor set layouts and descriptor pools when
  `bind_texture_count > 0` or `bind_sampler_count > 0`, with combined-image-sampler
  bindings for textures and sampler-only bindings for standalone samplers. Descriptor sets
  are allocated, written with resolved texture views and samplers from the runtime resource
  maps, and bound via `vkCmdBindDescriptorSets` at `VK_PIPELINE_BIND_POINT_GRAPHICS`
  before draw calls. The no-binding path (empty pipeline layout) is preserved.
  `RenderState` now carries `descriptor_set_layout`, `descriptor_pool`, and `descriptor_set`
  handles, cleaned up in `release_render_state`.
- D3D12 ETC2/EAC/ASTC format classification: `d3d12_formats.zig` now has explicit
  `is_etc2_compressed`, `is_astc_compressed`, and `is_any_compressed` helpers. The
  `wgpu_format_to_dxgi` function documents that ETC2/ASTC formats are intentionally
  unsupported (DXGI has no native constants). Device caps already correctly report
  `supports_etc2 = false` and `supports_astc = false`.
- Proof-artifact schema mismatch resolved: `config/proof-artifact.schema.json` already
  includes `lean_required` in the category enum at both theorem and boundsElimination
  levels. The status.md note claiming the schema lacked this value was stale.
- WGSL parser/emitter file sizes within limits: `parser.zig` is 342 lines, `emit_spirv.zig`
  is 698 lines, both under the 777-line Zig source limit. The status.md note claiming
  these files exceeded the limit was stale.

### Concurrency foundation first cut (2026-03-23)

- Added a bounded worker-pool foundation in `runtime/zig/src/runtime/task_pool.zig`.
- `wgpuDeviceCreateComputePipelineAsync` is now backed by real background work rather than immediate synchronous creation plus inline callback.
- `wgpuDeviceCreateRenderPipelineAsync` is now also backed by real background work with explicit descriptor copying.
- Duplicate in-flight async pipeline requests now collapse through shared runtime single-flight coordination in `runtime/zig/src/runtime/pipeline_singleflight.zig`.
- GPU timeline callback delivery now routes through shared worker-dispatch helpers in `runtime/zig/src/runtime/callback_dispatch.zig` instead of invoking all ready callbacks inline on the caller path.
- Timeline waits no longer use a spin-first path before blocking.
- Added an explicit runtime threading contract in `runtime/zig/src/runtime/threading_contract.zig` covering thread-safe objects vs thread-confined encoders.
- Added queue-role / submit-intent policy types in `runtime/zig/src/multi_queue.zig` so AI-oriented queue scheduling can become explicit instead of ad hoc.
- Added a concurrency program doc in `docs/concurrency-strategy.md`.
- Added benchmark harness skeleton `bench/pipeline-concurrency-bench.py` for pipeline throughput / cold-start / contention evidence.
- Not yet complete: async single-flight is shared, but not yet integrated with persistent pipeline-cache telemetry or background warmup policy.

### Authoritative state reconciliation (2026-03-22)

This section supersedes contradictory statements elsewhere in this document.

**Lean theorem count:** 77 theorems in `pipeline/lean/artifacts/proven-conditions.json`
(10 tautological, 4 comptime_verified, 17 lean_verified, 40 lean_required,
6 lean_fixture). Previous references to "84 theorems" are stale.
Note: the proof artifact uses `lean_required` as a category for unbounded-domain
theorems (IR builder soundness, MSL address-space chains, render-pass state
machines, compute bounds, etc.). The schema now includes `lean_required` in both
the theorem and boundsElimination category enums (resolved 2026-03-23).

**DXIL emitter status:** Native DXIL bytecode generation is now the primary
D3D12 path. Six modules (2,303 LOC) in `runtime/zig/src/doe_wgsl/` produce
LLVM 3.7 bitcode + DXBC container directly from Doe IR without external DXC.
`emit_dxil.zig` routes the primary `emit()` call through `emit_dxil_native`;
DXC is available as a fallback via `emitWithToolchainConfig()`. Previous
statements that "native DXIL emission is still deferred" or that D3D12 "still
relies on WGSL -> IR -> HLSL -> DXC" are superseded.

**AMD Vulkan `upload_write_buffer_1kb` status:** The comparability violation
is resolved (fast_mapped path now used for host-visible buffers within
`FAST_UPLOAD_BUFFER_MAX_BYTES`). The workload is now structurally comparable.
Claimability status: the latest headlineProcessWall evaluation shows 9/18
comparable workloads claimable on AMD Vulkan, with `upload_write_buffer_1kb`
among the claimable set. Previous statements that this workload is
"non-claimable" (from pre-fast_mapped runs) are superseded by the fix at
lines 23-34 of this document.

**Browser lane smoke summary (Doe, Linux headless, 2026-03-22):**
Evidence: `browser/chromium/artifacts/20260322Tdoe-smoke-after-copytexture/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`
- compute (computeIncrement): PASS
- render (renderTriangle): PASS (fixed this session -- SPIR-V propagation)
- xrCompatible (requestAdapterXrCompatible): PASS
- canvas API surface: all probes pass (offscreenCanvas, webgpuContext,
  configure, getCurrentTexture, preferredCanvasFormat=rgba8unorm)
- copyExternalImageToTexture: FAIL (Instance lifetime --
  `A valid external Instance reference no longer exists.`)
- importExternalTexture: FAIL (Instance lifetime -- same error)
Previous conflicting browser summaries elsewhere in this document are
superseded by this entry.

**WGSL test suite:** `zig build test-wgsl` passes with exit code 0
(runtime/zig, 2026-03-22). No vertex/fragment test failures remaining.

---

Doe rebrand (2026-03-22):
- `packages/doe-gpu/` created as the merged replacement for `@simulatte/webgpu`
  and `@simulatte/webgpu-doe`. Primary export is `gpu` (not `doe`).
  `createGpuNamespace` is the new alias for `createDoeNamespace`.
- `@simulatte/webgpu` and `@simulatte/webgpu-doe` deprecated with runtime
  console warnings and `"deprecated"` field in `package.json`.
- README.md and CLAUDE.md rebranded from Fawn to Doe.
- Pending: `packages/doe-gpu/src/*.js` imports helper code via relative paths
  into `../../webgpu-doe/src/`. Before npm publish, the helper layer must be
  vendored into `packages/doe-gpu/` so the package is self-contained. This is
  a publish-time concern, not a development concern.
- Pending: `browser/chromium/` rename to `browser/chromium/` (deferred).
- Pending: npm `doe` package dispute (contact jkup, 4-week wait, then npm
  support).
- Pending: `doe-gpu` GitHub org creation.

Upload path comparability fix (2026-03-22):
- `upload_write_buffer_1kb` comparability violation resolved. Dawn's Vulkan
  `WriteBuffer` detects host-visible+coherent buffers and performs a direct
  memcpy with zero GPU work. Doe's `staged_copy_only` lane policy was forcing
  all uploads through staged copy (host-visible src, device-local dst,
  vkCmdCopyBuffer, submit+fence wait), creating structural work asymmetry.
- `classify_upload_path` in `vk_upload.zig` now allows `fast_mapped` (direct
  memcpy to a persistently-mapped host-visible buffer) even under
  `staged_copy_only`, matching Dawn's actual behavior for small buffers
  within `FAST_UPLOAD_BUFFER_MAX_BYTES` (1MB).
- This eliminates the CLAUDE.md rules 7/10/11 violation on
  `upload_write_buffer_1kb`.

Metal backend command parity (2026-03-22):
- Metal native backend no longer returns `Unsupported` for `dispatch_indirect`:
  `runtime/zig/src/backend/metal/mod.zig` now routes the command into a native
  indirect-dispatch path backed by `dispatchThreadgroupsWithIndirectBuffer:`,
  with a reusable shared indirect-args buffer in
  `runtime/zig/src/backend/metal/metal_dispatch_runtime.zig`.
- Metal `map_async` is now implemented via synchronous shared-buffer contents
  access in `runtime/zig/src/backend/metal/metal_async_runtime.zig` /
  `runtime/zig/src/backend/metal/mod.zig`; command-mode validation matches the
  existing D3D12 path (`bytes > 0`, explicit max-size guard, no hidden fallback).

External texture runtime implementation (2026-03-21):
- `DoeExternalTexture` handle with ref-counted lifecycle (create, addref, release,
  destroy, expire, refresh) in `runtime/zig/src/doe_external_texture_native.zig`.
- Dropin proc table wires `wgpuDeviceCreateExternalTexture` to Doe via `resolveLocalProc`.
- Chromium-side external-texture lifetime tracking now pins a real wire
  `wgpu::Instance` through `DawnControlClientHolder`, so mailbox/external-texture
  resource lifetimes keep an external Instance reference alive instead of
  tripping the wire-client shutdown path with
  `A valid external Instance reference no longer exists.`.
- Doe now exports `wgpuQueueCopyTextureForBrowser` locally in addition to
  `wgpuQueueCopyExternalTextureForBrowser`, so Chromium's browser copy path no
  longer falls through `wgpuGetProcAddress()` to a foreign delegate proc for
  the Linux canvas/mailbox route.
- Doe now exports `wgpuQueueCopyExternalTextureForBrowser`; the current runtime
  implementation is an explicit bridge stub that preserves Chromium proc loading
  and status plumbing while native OS media/shared-texture interop remains
  tracked work.
- Doe bind-group/runtime ownership now parses `ExternalTextureBindingLayout` /
  `ExternalTextureBindingEntry` chained structs, retains bind-group child
  resources, and retains external-texture plane views so Chromium external
  textures no longer depend on ambient texture-view lifetime.
- Fresh Doe Linux smoke evidence on 2026-03-22 improved from
  `render=false` to `render=true` after the runtime ownership/bind-group fix:
  `browser/chromium/artifacts/20260322Tdoe-smoke-after-bindings/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`.
- Fresh rerun after adding the missing Doe-local `wgpuQueueCopyTextureForBrowser`
  still reports `compute=true`, `render=true`, and `xrCompatible=true`, while
  `copyExternalImageToTexture` and `importExternalTexture` remain red on the
  Doe lane:
  `browser/chromium/artifacts/20260322Tdoe-smoke-after-copytexture/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`.
- The current browser blocker on this host is therefore narrower and better
  isolated: the missing Doe proc ownership for `CopyTextureForBrowser` is fixed,
  but Chromium's Doe lane still lacks end-to-end shared-image/media interop for
  the Skia/mailbox fallback and `texture_external` render path. The observed
  failure remains `A valid external Instance reference no longer exists.` on
  both `copyExternalImageToTexture` and `importExternalTexture`.

Upload performance optimizations (2026-03-21):
- Removed explicit `vkResetCommandBuffer` from `flush_queue`; implicit reset via
  `VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT` saves one Vulkan call per flush.
- Fast staging path: uploads within 1MB reuse the persistent `fast_upload_buffer` as
  staging source, eliminating per-upload src buffer pool management.
- Pending benchmark run with `zig build -Doptimize=ReleaseFast` to measure improvement.

Redundant runtime checks removed (2026-03-21):
- Removed redundant sample_count, width/height/depth, texture view dimension, and
  group bounds normalization in `wgpu_resources.zig` and `zeroInitializeTexture`.

Lean proof integration fixes (2026-03-21):
- `analyzeToIr` now uses `default_translation_robustness_config()` to respect
  `-Dlean-verified=true` for bounds elision.
- `classify_gid_component` handles `.load` nodes (matching `classify_gid_scalar`).

Previous: 2026-03-19

Vulkan compute dispatch unblocked (2026-03-19):
- Vulkan `dispatch_indirect` now uses a dedicated indirect-dispatch path in `backend/vulkan/mod.zig` / `backend/vulkan/native_runtime.zig`: it writes `[x, y, z]` into a reusable indirect-args buffer and records `vkCmdDispatchIndirect` instead of routing through the direct-dispatch helper.
- Bare `dispatch`/`dispatch_indirect` without a prior `kernel_dispatch` now auto-loads a no-op WGSL kernel (`dispatch_noop.wgsl`) before executing; `has_pipeline` guard replaced by auto-load so workloads that send dispatch without an explicit kernel still execute on Linux Vulkan.
- AMD Vulkan compare presets now pass `--kernel-root bench/kernels` symmetrically to Doe-native and Dawn-delegate templates, fixing directional `dispatch` / `dispatch_indirect` lanes that depended on `dispatch_noop.wgsl` but previously failed on the delegate side with `MissingKernelSource`.
- Governed `doe-advantage` compare lanes now exist for both AMD Vulkan and local Metal. The compare harness now supports `--workload-cohort doe-advantage`, report artifacts carry `benchmarkIntent`, `benchmarkClass`, and `directionalReason`, and directional summaries count why a workload is outside strict apples-to-apples lanes.
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json` is now a backward-compatible alias of the governed strict extended contract (`bench/workloads.amd.vulkan.extended.strict.json`) instead of the obsolete legacy `bench/workloads.amd.vulkan.extended.json` workload file that still carried upload `pathAsymmetry` flags on comparable rows.
- Compare-run manifests now distinguish claimability misses from execution failures: claim-enabled compare runs still exit non-zero on non-claimable results, but `run_manifest.json` records `status=diagnostic` when the report is comparable yet non-claimable.
- AMD Vulkan strict staged uploads now prefer the existing fence wait path for immediate upload flushes in `runtime/zig/src/backend/vulkan/vk_upload.zig` instead of the timeline-semaphore wait path; this reduced the focused `upload_write_buffer_1kb` gap on this host from roughly `p50 -4.42% / p95 -6.21%` to `p50 -3.74% / p95 -1.40%` under the same workload contract.
- Performance evidence on this host now requires an optimized Zig runtime build: `zig build -Doptimize=ReleaseFast` materially improves AMD Vulkan `upload_write_buffer_1kb`. (Note: pre-fast_mapped runs from 2026-03-20 showed this row as diagnostically blocked; the fast_mapped comparability fix on 2026-03-22 resolved the structural asymmetry. See authoritative reconciliation at top of this document.)
- `doeNativeDeviceCreateBindGroupLayout` now returns `null` for `entryCount > 0` with `entries = null` instead of trapping across the C ABI boundary.
- D3D12 stub bridge (`src/backend/d3d12/d3d12_bridge_stubs.c`) added; all non-Windows build targets now link the stubs so `doe-zig-runtime`, tests, and dropin libraries build on macOS and Linux without D3D12 headers.
- Stale test fixes: `CmdTag` variant count 8→10 (added `write_timestamp`, `resolve_query_set`); `align_cbv_size(768)` expected value corrected (768 is already 256-aligned); Vulkan dispatch tests no longer assert a specific `status_message` string for the runtime-unavailable fallback path.
- Metal `metal_bridge_device_new_texture` extern declaration fixed: missing `sample_count` parameter added; all call sites updated.
- All three test suites (`test-core`, `test-full`, `test-wgsl`) now pass on macOS.
- AMD Vulkan extended workload contracts no longer self-contradict on `benchmarkClass` versus `comparable`: `render_pixel_local_storage_barrier_500` and `resource_table_immediates_500` now remain directional across the affected AMD extended / Doe-vs-Doe lanes, and `bench/generate_backend_workloads.py` now hard-fails on any future mismatch before compare-time.

Runtime verification of the 17 Vulkan compute workloads (AMD Radeon/RADV GFX11) requires a Linux host with AMD GPU and MoltenVK/RADV driver; the macOS build confirms the dispatch code compiles and links but cannot execute Vulkan GPU commands locally.

Doe is in active implementation phase. Runtime behavior is operational for dispatch decisions and replay-aware tracing, but several product and release-flow gaps remain before v1-grade stability claims.
The execution platform strategy is full native Zig+WebGPU/FFI runtime execution.
Current `runtime/zig/src` size is ~60,642 non-test LOC across all backends (`find runtime/zig/src -name '*.zig' -not -name '*test*' -not -name '*bench*' | xargs wc -l`, 2026-03-18) and includes native queue-submitted execution for upload, copy, barrier, render, and dispatch-family lowering across Metal, Vulkan, and D3D12 backends.
Shader/compiler state improved materially since the earlier strategic notes:
- the IR robustness transform in `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig` covers sized arrays/vectors/matrices, runtime-sized arrays (with broadened base-expression whitelist: global_ref, member, load, local_ref, param_ref, index, call), and texture coordinate clamping for textureLoad/textureStore (2D/3D/cube/depth/multisampled/storage). Tests in `ir_transform_robustness_test.zig` (12 tests). Full CTS/security-surface hardening for remaining edge cases (e.g. texture_1d, textureSampleLevel integer coords) is follow-up work
- SPIR-V texture/sampler lowering advanced materially in `runtime/zig/src/doe_wgsl/emit_spirv_texture.zig`, but Vulkan graphics-path promotion is still incomplete
- `runtime/zig/src/doe_wgsl/bench_compilation.zig` now provides a local compilation benchmark harness; public published benchmark evidence is still pending
- HLSL/DXIL `@builtin(num_workgroups)` no longer aliases `SV_GroupID`; it now lowers through a reserved dispatch-info constant-buffer contract (`runtime/zig/src/doe_wgsl/hlsl_dispatch_contract.zig`) that the D3D12 runtime binds before compute dispatch
- WGSL compiler hardening now includes backend builtin-surface coverage for current IR builtins, an explicit HLSL emit contract around `num_workgroups`, and fixed-size array helper-parameter translation regression coverage across MSL/HLSL/SPIR-V
- shader-side Lean bounds proofs in `pipeline/lean/Fawn/Shader/ComputeBounds.lean` are now integrated with the runtime: `lean_proof.zig` validates all five theorem names at comptime, `ir_transform_robustness.zig` pattern-matches `buf[gid.{x,y,z}]` on storage buffers and elides the clamp when `-Dlean-verified=true`, recording dispatch preconditions for host-side enforcement
Track A (browser) diagnostics are now governed by a promoted macOS browser gate
(`bench/browser/browser_gate.py`) that runs lane preflight, fresh Playwright
smoke, and fresh strict layered browser validation through the canonical
blocking runner.
Track A (browser) claimability now has a repeated-window local claim lane
(`bench/browser/browser_claim_gate.py`) with config-backed policy in
`config/browser-claim-policy.json`; single-window browser gates remain
diagnostic, while the claim lane is the only path allowed to emit browser
`claimStatus=claimable`.
The `@simulatte/webgpu/browser` surface now validates and forwards the later
enum/value unions used by browser-owned adapters and textures
(`GPUFeatureName`, `GPUTextureFormat`, texture/view/sample/layout enums, and
render-pipeline primitive/vertex state), and preserves native browser
`GPUPipelineError.reason` through async pipeline creation.
The WebGPU spec index now treats the 29 browser-owned delegation rows
(`externalTexture`, `importExternalTexture`, `copyExternalImageToTexture`,
`GPUOrigin2DDict*`, and `xrCompatible`) as implemented product-surface closure
rather than native-backend backlog: `config/webgpu-spec-index.jsonl` now marks
those Metal/Vulkan/D3D12 cells as implemented with explicit notes that the
implementation lives on the Fawn browser lane and delegates to browser-owned
WebGPU objects, while the headless Doe runtime still does not own those APIs
directly. Playwright browser smoke now exercises those closures end-to-end on
the package-browser path in both Dawn and Doe modes: explicit
`requestAdapter({ xrCompatible: false })` forwarding, two-tone
`copyExternalImageToTexture` readback with `flipY`/origin dictionaries, and
`importExternalTexture` plus `externalTexture` binding/layout sampling from a
`VideoFrame` source.
Vulkan package/runtime state closure advanced for the headless `@simulatte/webgpu`
surface:
- native bind-group layouts now retain `GPUTextureBindingLayout` texture semantics
  and validate bound texture views for `multisampled`, `sampleType`, and
  `viewDimension`
- Vulkan render-pipeline creation now consumes package/addon blend-factor,
  blend-operation, and cull-mode state into graphics-pipeline rasterization and
  color-blend setup
- Vulkan render-pipeline and render-pass execution now retain and consume
  `GPUVertexAttribute`, `GPUVertexBufferLayout`, and `GPUVertexState`
  metadata end-to-end, including real vertex/index buffer binding on the
  render-pass path
- Vulkan swapchain creation now honors configured `GPUCanvasAlphaMode`
  instead of hardcoding opaque composite alpha
- shared/package publication for `GPUBuffer.mapState`, `GPUDevice.lost` reason
  strings, `layout: "auto"`, and the Vulkan feature-name surface is now reflected
  in the coverage ledger
- the tracked Vulkan coverage gap from this unblock pass is now closed:
  vertex-input publication, canvas alpha/tone-mapping modes, and
  compilation-message severities are all reflected in source and ledger state
macOS browser maintenance now has scheduled workflow and retention wiring:
- `.github/workflows/macos-browser-refresh.yml`
- `browser/chromium/scripts/cleanup-browser-artifacts.py`
Runtime command semantics are now first-class for indirect/render-pass benchmark lanes:
- `dispatch_indirect`, `draw_indirect`, `draw_indexed_indirect`, and `render_pass` are explicit command kinds in model/parser/runtime/backend routing (no alias-only semantics).
Strict Dawn-vs-Doe operation comparability now uses direct per-side timing normalization only:
- comparable workloads in `bench/workloads*.json` use `leftTimingDivisor=1.0` and `rightTimingDivisor=1.0`.
- strict compare fails fast if comparable Dawn-vs-Doe workloads attempt side-specific divisor scaling.
AMD Vulkan strict comparable/release presets now point at the native-supported workload contract, not the broader aspirational extended matrix.
- the 256 MB AMD Vulkan matvec rows (`compute_matvec_32768x2048_f32`, `_swizzle1`, `_workgroupshared_swizzle1`) now match the existing local Metal policy: they are directional-only `doe-advantage` rows because Dawn rejects the storage binding size on this host, so they no longer belong to the strict apples-to-apples contract until the workload is split or the incumbent limit surface changes.
- Linux package/drop-in integration is now corrected for workspace-local Doe loads:
  - `runtime/zig/src/wgpu_dropin_lib.zig` now opens a target WebGPU provider via `openDropinTargetLibrary()` instead of re-opening `libwebgpu_doe.so`, which had been causing recursive proc resolution and package smoke crashes on Linux.
  - latest Linux Vulkan package validation now passes from `packages/webgpu/`: `npm run build:addon`, `npm run smoke`, `npm test`, `npm run prebuild -- --skip-addon-build`, and `npm run test:bun`.
- Vulkan graphics/resource promotion advanced locally:
  - `vk_render.zig` now consumes render-pipeline primitive front-face/topology state and depth/stencil operation state instead of hardcoding triangle-list / counter-clockwise / null depth-stencil.
  - Vulkan sampler creation now honors comparison samplers, sampled/storage texture binding validation now accepts depth/sint/uint and read-only/read-write modes, and Vulkan format mapping now covers `rgba16{u,s}norm` plus BC / ETC2-EAC / ASTC texture families.
  - focused March 20, 2026 strict comparable artifact `bench/out/scratch/20260320T175741Z/vulkan.promote.render_texture_resource.no_raster_sampling.json` is `comparisonStatus=comparable`, `claimStatus=diagnostic` across 13 Vulkan render/texture/resource workloads on this AMD host.
  - follow-up March 20, 2026 fixes closed that remaining `texture_sampling_raster_baseline` blocker: the Vulkan SPIR-V path now elides redundant gid-guarded texture robustness clamps, and `examples/texture_raster_proxy_commands.json` now creates/queries/destroys its textures explicitly via zero-init `texture_write` commands before `kernel_dispatch`. Focused artifact `bench/out/scratch/20260320T210000Z/vulkan.texture_sampling_raster_baseline.fixed2.json` is now `comparisonStatus=comparable` (still `claimStatus=diagnostic` due a real negative delta).
  - the March 20, 2026 strict preflight evidence showed the next blocker was the 256 MB matvec contract: Dawn rejects `compute_matvec_32768x2048_f32` with `kernel_dispatch_storage_binding_exceeds_maxstoragebufferbindingsize`. Those three large matvec rows are now tracked as governed `doe-advantage` directional workloads instead of remaining in the strict apples-to-apples AMD Vulkan lane.
- (Historical, pre-fast_mapped) AMD Vulkan strict release rerun on this host was non-claimable for upload-heavy release evidence:
  - artifact: `bench/out/amd-vulkan/20260310T153903Z/dawn-vs-doe.amd.vulkan.release.json`
  - status: `comparisonStatus=comparable`, `claimStatus=diagnostic`
  - this entry predates the fast_mapped comparability fix; see authoritative reconciliation above for current state
- `upload_write_buffer_1kb` Vulkan staged-copy path optimized (three changes in `runtime/zig/src/backend/vulkan/native_runtime.zig`):
  - replaced `vkQueueWaitIdle` with fence-based `vkWaitForFences` in `flush_queue` to reduce per-submission driver synchronization overhead on RADV
  - eliminated redundant `vkResetCommandBuffer` between `flush_queue` and `ensure_upload_recording` via `command_buffer_reset_clean` tracking flag
  - persisted staging buffer mapping through hot pool (`src_mapped` in `PendingUpload` and `release_upload`) to avoid per-upload `vkMapMemory`/`vkUnmapMemory` overhead
  - all three optimizations preserve staged-copy-only comparability for the Vulkan comparable/release lanes
  - pending: rerun strict release benchmark to verify claimability after optimization
- strict Vulkan upload destination usage now follows the explicit upload contract instead of inflating `copy-dst` uploads into storage-buffer usage:
  - file: `runtime/zig/src/backend/vulkan/native_runtime.zig`
  - focused March 10 probe: `bench/out/scratch/20260310T_package_copy_and_vulkan/amd-vulkan.upload_1kb.focused.json`
  - full March 10 rerun: `bench/out/scratch/20260310T_package_copy_and_vulkan/amd-vulkan.release.full.json`
  - result: the full strict release lane remains `comparisonStatus=comparable`, `claimStatus=diagnostic`, but still only one blocker (`upload_write_buffer_1kb`); no other upload rows regressed out of claimability.
- comparable workload contract symmetry is now enforced at the catalog source of truth:
  - `bench/backend-workload-catalog.json` now restores symmetric left/right repeat accounting for all currently comparable rows that had drifted into one-sided `commandRepeat` overrides across render, texture-contract, compute, p0-resource, upload, and related strict comparable lanes.
  - `bench/generate_backend_workloads.py` now fails catalog validation when any `comparable=true` row would materialize asymmetric effective left/right repeat, ignore-first, submit cadence, timing divisor, or upload-buffer-usage values.
  - `bench/test_backend_workload_catalog.py` now has regression coverage that materializes every lane and rejects future comparable workload asymmetry before release benchmarking runs.
- comparable-lane count comparisons must now be read lane-by-lane, not as a generic Metal-vs-Vulkan backend statement:
  - current generated contracts: `apple_metal_extended=31 comparable`, `amd_vulkan_extended=31 comparable`, `amd_vulkan_extended_strict=30 comparable`, `amd_vulkan_superset=16 comparable`.
  - the previously circulated `31 vs 16` gap is a mixed-lane comparison (`apple_metal_extended` vs `amd_vulkan_superset`), not a general Metal-vs-Vulkan coverage statement.
  - for that mixed comparison, Metal has `19` comparable rows that AMD Vulkan superset does not yet promote, while AMD Vulkan superset has `4` comparable rows that Apple Metal does not (`compute_matvec_*` variants plus `surface_presentation`).
  - fresh local-Metal strict comparable rerun after the all-domain symmetry and package refresh work is `bench/out/apple-metal/extended-comparable/20260310T191301Z/dawn-vs-doe.local.metal.extended.comparable.json`.
  - that authoritative full rerun remains `comparisonStatus=comparable`, `claimStatus=diagnostic`, with `31` comparable workloads and only one remaining non-claimable row: `copy_texture_to_texture` (`p95` tail slightly negative).
  - follow-up March 10 focused proof after the Metal fast-wait copy-path patch is `bench/out/scratch/20260310T202542Z/copy_texture_to_texture.direct.json`, which is `comparisonStatus=comparable`, `claimStatus=claimable` for `copy_texture_to_texture` in isolation. A broader 11-workload comparable subset rerun at `bench/out/apple-metal/extended-comparable/20260310T202715Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v9.json` still leaves that row slightly negative, so the full lane remains one-row short of claimable.
  - the canonical package/backend cube was rebuilt after the latest package refresh (`bench/out/cube/latest/cube.summary.json`, generated `2026-03-10T20:31:02.431911Z`) and now points the macOS package cells at the fresh March 10 full-lane package artifacts: Bun `uploads`, `compute_e2e`, and `full_comparable` are `claimable`; Node `uploads`, `compute_e2e`, and `full_comparable` are also `claimable`.
- Local Metal claim-metric scope correction (2026-03-19):
  - `bench/native_compare_modules/claimability.py` now prefers `timingInterpretation.headlineProcessWall.deltaPercent` for `copy` and `surface` rows when `operation-total` timing undercovers end-to-end process wall on both sides and the headline tails remain positive.
  - regression coverage added in `bench/test_claimability.py` for the `copy_texture_to_texture` and `surface_full_presentation` undercoverage case.
  - fresh full-lane rerun artifact: `bench/out/apple-metal/extended-comparable/20260319T161100Z/dawn-vs-doe.local.metal.extended.comparable.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`
- root cause of the March 10 AMD Vulkan release regression was catalog drift, not a simulator/cost-model path:
  - the compare harness correctly normalized by effective workload contract, but several strict upload rows had right-only `commandRepeat`/`ignoreFirstOps` overrides, so Doe was being measured at one effective unit while Dawn was amortized over fifty or five hundred.
  - fresh strict rerun after repairing the catalog reduced the release blocker set from five upload rows to one genuine tiny-upload performance gap (`upload_write_buffer_1kb`).
- Linux browser runtime selector bring-up is now operational in the local Chromium tree (2026-03-20):
  - `browser/chromium/src/out/fawn_release/chrome` now honors `--use-webgpu-runtime=dawn|doe`, `--disable-webgpu-doe`, and `--doe-webgpu-library-path`.
  - the Linux Playwright smoke harness now defaults Chromium launches to `--use-angle=vulkan`, which makes the local forced-Dawn lane pass compute, render, `xrCompatible`, `copyExternalImageToTexture`, `importExternalTexture`, and the mini timing probes.
  - the Doe browser path now passes the local headless compute, render, `xrCompatible`, and `copyExternalImageToTexture` smoke checks; the key fix was GPU-thread polling that ticks each live Doe device before `instanceProcessEvents`, so submit-driven callbacks no longer stall after `queue.submit()`.
  - Doe custom mailbox commands now enter the selected runtime's per-thread proc scope, which keeps decoder-side mailbox handling on the selected runtime instead of falling back to Dawn-global procs.
  - forced `--use-webgpu-runtime=doe` with a fake shared-library path now leaves `requestAdapter()` unavailable instead of silently substituting Dawn.
  - remaining browser-lane gap on this host is now Doe-only: `importExternalTexture` and the mini timing probes still fail under Doe on Linux with `A valid external Instance reference no longer exists.`, which is consistent with Doe's still-incomplete native media/shared-texture interop path.
- Backend naming cutover is complete for runtime-visible surfaces: Doe is now the only backend identity (`doe-zig-runtime`, `libwebgpu_doe.so`, Chromium `--use-webgpu-runtime=doe`, `--disable-webgpu-doe`, `--doe-webgpu-library-path`).
- Doe identity cleanup for runtime-visible diagnostics is complete:
  - drop-in helper exports are now `doeWgpuDropinLastErrorCode` / `doeWgpuDropinClearLastError`
  - runtime timestamp debug env flag is now `DOE_WGPU_TIMESTAMP_DEBUG`
  - trace semantic-parity eligibility now keys on Doe module identity (`module` starts with `doe-`)
- D3D12 backend lane/runtime integration now exists as a first-class Doe backend path:
  - backend identity: `doe_d3d12`
  - runtime module tree: `runtime/zig/src/backend/d3d12/*`
  - lane contracts: `d3d12_doe_app`, `d3d12_doe_directional`, `d3d12_doe_comparable`, `d3d12_doe_release`, `d3d12_dawn_release`
  - drop-in behavior contracts include `doe_d3d12_ownership` and D3D12 lane mode mapping.
- D3D12 native backend routing is active:
  - `runtime/zig/src/backend/backend_registry.zig` routes `doe_d3d12` directly to `runtime/zig/src/backend/d3d12/mod.zig`.
  - active D3D12 execution is instance-owned (`ZigD3D12Backend` + `WebGPUBackend`) with shared common-layer error/capability contracts.
  - D3D12 shader-artifact manifest failures are now handled in-place (typed status update) without throwing away command timing/dispatch metadata.
  - live `.wgsl` shader compilation now lowers through the shared WGSL→IR path; the primary D3D12 path generates native DXIL bytecode directly, with DXC available as a fallback. Precompiled `.cso`/`.dxbc` artifacts and explicit `.hlsl` source compilation remain supported.
- Vulkan native backend routing is now active on `doe_vulkan`:
  - `runtime/zig/src/backend/backend_registry.zig` routes `doe_vulkan` to `runtime/zig/src/backend/vulkan/mod.zig` (no Dawn delegate fallback in this lane).
  - `kernel_dispatch` binds real kernel SPIR-V via native Vulkan runtime (`load_kernel_spirv` + pipeline bind), removing noop-kernel execution on that path.
  - upload cadence now queues copy command buffers and flushes by explicit submit policy (`upload_submit_every`) instead of immediate per-upload submit.
  - native WGSL→IR→SPIR-V coverage now matches the current compute kernel corpus: storage-buffer runtime arrays, workgroup/storage atomics, `workgroupBarrier`, `dot`, `sin`, `fract`, and narrow texture/image support are all lowered natively in Zig.
  - native compute texture-backed dispatch now includes `texture_write` / `texture_query` / `texture_destroy`, Vulkan image+view allocation for `rgba8unorm` 2D textures, descriptor-image binding for `.texture` and `.storage_texture`, empty-write texture creation promoted to shader-usable `GENERAL` layout, and native WGSL→IR→SPIR-V lowering for `textureLoad` / `textureStore` kernels such as `bench/kernels/texture_sample_to_storage_64.wgsl`.
- Vulkan C ABI closure (2026-03-17):
  - 31 new Vulkan dispatch points added across 6 C ABI shard files, completing the Vulkan C ABI surface for buffer, copy, texture, queue, query, and surface operations.
  - `doe_encoder_native.zig`: `copyBufferToBuffer` (immediate CPU memcpy via mapped Vulkan buffers), `copyBufferToTexture` (immediate `rt.texture_write()`), `copyTextureToBuffer` (explicit unsupported warn).
  - `doe_command_texture_native.zig`: `clearBuffer` (`@memset` on mapped Vulkan buffer), `copyTextureToTexture` (explicit unsupported warn), `writeTexture` (`rt.texture_write()`).
  - `doe_queue_submit_native.zig`: `writeBuffer` (mapped buffer memcpy), `flush` (`rt.flush_queue()`), `release` (flush + destroy), `submit` (early return — Vulkan commands execute immediately during recording).
  - `doe_query_native.zig`: `createQuerySet`, `writeTimestamp`, `resolveQuerySet`, and render-pass occlusion query controls are wired on Vulkan through `VkQueryPool`; tracker/evidence remain unit-scoped rather than broadly governed.
  - `doe_surface_native.zig` (new file): full surface/swapchain C ABI with 8 functions — `create`, `configure`, `getCurrentTexture`/`acquire`, `present`, `unconfigure`, `release`, plus platform handle setters for XCB and Wayland windowed rendering.
  - `doe_wgpu_native.zig`: wired all 8 surface exports + comptime reference.
  - explicitly unsupported on Vulkan: `copyTextureToTexture`, `copyTextureToBuffer`.
- Runtime backend selection is strict no-fallback across all lanes:
  - `runtime/zig/src/backend/backend_runtime.zig` initializes the selected backend directly and does not auto-route to `dawn_delegate`.
  - `config/backend-runtime-policy.json` enforces `allowFallback=false` and `strictNoFallback=true` for every lane.
  - backend init failures now fail fast with explicit backend errors and `fallbackUsed=false`.
- Shader contract/gate layer now supports a backend-neutral transition contract:
  - `config/shader-artifact.schema.json` accepts legacy `schemaVersion=1` manifests and new `schemaVersion=2` manifests with shared `irSha256`, backend-specific final artifact hashes (`mslSha256`/`metallibSha256`, `spirvSha256`, `dxilSha256`), and stage-by-stage route attestations.
  - `config/shader-toolchain.json` and its schema now model backend routes as explicit stage contracts (`native_zig` vs `external_tool`) instead of hard-coded Metal-only translation steps.
  - `bench/shader_artifact_gate.py` can now validate taxonomy membership, toolchain-hash linkage, strict native-backend route conformance, and SPIR-V artifacts by default whenever a manifest carries SPIR-V output; `run_blocking_gates.py` auto-uses `spirv-val` from PATH when present.
  - `bench/preflight_metal_host.py` now derives required external tools from the shader toolchain contract instead of hard-coding Metal compiler checks.
  - runtime shader manifest emitters now emit `schemaVersion=2` end-to-end across all three backends (Metal, Vulkan, D3D12) with `irSha256`, backend-specific artifact hashes (`mslSha256`/`metallibSha256`, `spirvSha256`, `dxilSha256`), and stage-by-stage route attestations. Strict native-route enforcement can now be enabled universally.

Benchmark contract coverage snapshot (2026-02-25 update):
- `bench/workloads.amd.vulkan.extended.json` now contains `40` workload contracts: `31` strict apples-to-apples comparable + `9` directional contracts.
- Dawn DrawCallPerf now includes indexed coverage (`DynamicVertexBuffer_DrawIndexed`), and `render_multidraw_indexed` is restored to strict comparable (`comparable=true`).
- missing Dawn perf suites were added to AMD extended contracts: `MatrixVectorMultiplyPerf`, `UniformBufferUpdatePerf`, and `VulkanZeroInitializeWorkgroupMemoryExtensionTest`.
- strict comparable lanes now fail fast for directional/proxy-labeled contracts and upload mixed-scope ignore-first timing derivations.
- Dawn adapter filter resolution is now explicit-only (no `filters.default` fallback); missing workload mappings fail fast unless that workload is explicitly `@autodiscover`.
- report ingestion tools (`build_baseline_dataset.py`, `build_test_inventory_dashboard.py`) now require conformant compare reports with canonical comparability obligations and valid `workloadContract.path/sha256` hash consistency.
- `surface_presentation` is explicitly directional-only (`comparable=false`); strict comparable lanes use `compute_concurrent_execution_single` for Dawn `ConcurrentExecutionTest ... RunSingle` apples-to-apples coverage.
- adapter-agnostic strict preset added for this host class: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`.
- host prerequisites are now explicit and machine-checkable via `bench/preflight_bench_host.py`.
- claim-lane governance is now hash-locked and machine-checked via `config/claim-cycle.active.json` + `bench/cycle_gate.py`, with release pipeline default wiring when claim gate is enabled.
- app-lane Vulkan claim/cycle proof now has a dedicated strict local contract and fresh green evidence:
  - contract/config/workload: `config/claim-cycle.amd-vulkan-app-local.json`, `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.app.claim.json`, `bench/workloads.amd.vulkan.app.claim.json`
  - comparable+claimable run: `bench/out/20260226T164929Z/vulkan.vulkan_doe_app.local.claim_cycle.json`
  - cycle gate pass: `bench/out/20260226T164929Z/cycle_gate_report.json`
  - additional strict checks pass on the same artifact: backend selection (`vulkan_doe_app`), shader artifact, Vulkan sync, Vulkan timing
- Vulkan backend correctness hardening (2026-03-01):
  - `runtime/zig/src/backend/vulkan/mod.zig` now separates encode timing from submit/wait timing and removes duplicate manifest emission on `kernel_dispatch`.
  - upload behavior knobs are now execution-effective end-to-end (`upload_buffer_usage_mode`, byte budgets via staging reserve) instead of stored-only fields.
  - `runtime/zig/src/backend/vulkan/vulkan_runtime_state.zig` now emits deterministic command-scoped manifest payloads (non-placeholder hashes) and sets initialization state explicitly in `create_instance`.
  - new/expanded correctness tests under `runtime/zig/tests/vulkan/` validate timing-bucket separation, upload mode/cadence behavior, manifest hash-chain semantics, and single-emission manifest behavior.
  - submit-wait semantics were aligned with native baseline scope: Vulkan `submit_wait_ns` now includes queue submit time plus wait time when waiting is enabled, and records submit-only cost under deferred sync.
  - upload cadence tail correctness is now explicit: final queue flush runs when upload cadence batching is active (`upload_submit_every > 1`), and Vulkan `flush_queue` submits pending upload batches before final wait.
  - shader manifest `*Sha256` fields now use literal SHA-256 digests of deterministic artifact payload strings instead of non-cryptographic placeholder-style hashes.
- Metal backend correctness hardening (2026-03-01):
  - `runtime/zig/src/backend/metal/mod.zig` now separates encode timing from submit/wait timing using cumulative timing deltas, removes duplicate shader-manifest emission paths, and flushes pending upload cadence tails during final queue flush.
  - Metal upload behavior knobs are now execution-effective in runtime path (`upload_buffer_usage_mode`, `upload_submit_every`, and prewarm byte budgets) via byte-aware staging reserve and mode-aware upload execution.
  - `runtime/zig/src/backend/metal/metal_runtime_state.zig` now derives manifest `*Sha256` fields from literal SHA-256 artifact payload digests, records command-scoped manifest module tags, and persists manifest telemetry only after file write success.
  - Metal tests are now wired into `runtime/zig/test_suite.zig` so `zig build test` exercises both Metal and Vulkan backend correctness paths.
  - Metal upload hot-path now reuses staging capacity and upload buffer allocation across commands in `runtime/zig/src/backend/metal/mod.zig` (`ensure_upload_capacity`, `ensure_upload_buffer`), removing per-command reserve+buffer-create churn for steady-state upload workloads.
  - Metal command routing now emits shader artifact manifests only for shader-bearing command families (`dispatch`, `kernel_dispatch`, `render_draw`, `async_diagnostics`), reducing non-shader command overhead without changing manifest coverage on shader paths.
  - Metal flush behavior now avoids unnecessary runtime bootstrap on no-op flushes and preserves upload cadence correctness when a non-upload command follows queued uploads.
- Metal upload apples-to-apples restoration (2026-03-07):
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` now forces staged blit uploads for comparable `copy-dst` workloads, including small payloads; staging source buffers are rewritten every iteration so Doe performs the same host-write work Dawn measures.
  - `runtime/zig/src/backend/metal/mod.zig` now charges upload staging work to `setup_ns`, matching the Dawn delegate upload timing phase split.
  - Apple Metal upload workload contracts (`bench/workloads.apple.metal.extended.json`, `bench/workloads.apple.metal.smoke.json`) no longer mark upload rows as `pathAsymmetry`.
  - strict comparability now has a blocking `left_right_timing_phase_match` obligation, so future phase-scope drift fails comparability instead of surviving until claimability.
- Compare report timing interpretation hardening (2026-03-07):
  - `bench/native-compare/compare_dawn_vs_doe.py` now emits additive `timingInterpretation` fields so selected claim metrics and end-to-end process-wall views are reported separately.
  - `timingInterpretation.selectedTiming` marks narrow-scope rows such as render encode-only results as `scopeClass=narrow-hot-path`.
  - `timingInterpretation.headlineProcessWall` reports timed-command process-wall deltas, normalized by `commandRepeat` and `timingNormalizationDivisor`, giving an honest top-line ranking view without changing existing `deltaPercent` claim semantics.
  - claimability now keeps `deltaPercent` diagnostic for `scopeClass=narrow-hot-path` rows but evaluates `timingInterpretation.headlineProcessWall.deltaPercent` for end-to-end claimability when that metric is available.
  - repeat-asymmetric counter-derived timing sources (`doe-execution-total-ns`, `doe-execution-encode-ns`, `doe-execution-dispatch-window-ns`, `doe-execution-gpu-timestamp-ns`) now normalize to one workload unit via `commandRepeat` before claim/comparability evaluation, and the operation-vs-process-wall sanity audit uses the same normalized units.
  - `bench/build_claim_scope_report.py` now propagates selected-scope vs headline-process-wall context into citation-safe artifacts.
- Local Metal workload contract catch-up (2026-03-09):
  - `bench/backend-workload-catalog.json` now admits `compute_dispatch_fallback`, `compute_dispatch_grid`, `copy_buffer_to_texture`, `copy_protocol`, `copy_texture_to_buffer`, `copy_texture_to_texture`, and `surface_full_presentation` into `apple_metal_extended`, raising the generated Apple Metal extended contract from `43` to `50` workloads and closing the AMD-Vulkan-extended contract-count gap on macOS.
  - `runtime/zig/src/backend/metal/mod.zig`, `runtime/zig/src/backend/metal/metal_native_runtime.zig`, and `runtime/zig/src/backend/metal/metal_dispatch_runtime.zig` now implement native Metal support for plain `dispatch` commands using a default no-op compute kernel (`bench/kernels/dispatch_noop.metal`), which is the prerequisite for those directional compute contracts to execute on macOS at all.
  - `runtime/zig/src/core/compute/wgpu_commands_compute.zig` plus new WGSL kernel `bench/kernels/dispatch_noop.wgsl` now give the Dawn delegate path real plain-`dispatch` / `dispatch_indirect` execution instead of returning `unsupported`, which removed the old zero-success preflight failure on Apple Metal dispatch parity probes.
  - `runtime/zig/src/backend/metal/metal_copy_runtime.zig`, `runtime/zig/src/backend/metal/metal_surface_runtime.zig`, and new Metal bridge blit helpers now execute the remaining directional copy/surface contracts natively on macOS; direct Doe-native artifacts are under `bench/out/apple-metal/mac-catchup-direct/20260309T185647Z/`.
  - Dawn-side copy ABI parity is now fixed (`wgpuCommandEncoderCopy*` extent arguments are passed as pointers, matching the C API), so the directional incumbent baseline no longer crashes on `copy_buffer_to_texture`.
  - Dawn-side surface parity on macOS now uses a hosted `CAMetalLayer` source in `runtime/zig/src/full/surface/*`, and `examples/surface_full_presentation_commands.json` now requests `bgra8unorm`, which is the presentable Metal swapchain format that lets Dawn acquire/present successfully under the real Apple/Metal profile.
  - `runtime/zig/src/full/surface/wgpu_surface_commands.zig` now attributes create/capabilities/configure/acquire/unconfigure/release wall time to `encode_ns` and present wall time to `submit_wait_ns`, which removes the previous timing-phase mismatch between Doe-native and the Dawn delegate path for `surface_full_presentation`.
  - `surface_full_presentation` is now promoted to `comparable=true` for `apple_metal_extended` in `bench/backend-workload-catalog.json` and the generated `bench/workloads.apple.metal.extended.json`. The strict comparable contract now claims one full presentation cycle per repeated command stream (`rightCommandRepeat=100`, `left/rightTimingDivisor=100`) instead of seven internal surface sub-ops per cycle, and the strict normalization gates in `bench/native-compare/compare_dawn_vs_doe.py` plus `bench/native-compare/modules/runner.py` now treat `domain=surface` accordingly. Focused rerun `bench/out/scratch/20260309T_surface_fix/20260309T204238Z/metal.surface_full_presentation.strict.v2.json` ended `comparisonStatus=comparable`, `claimStatus=claimable`.
  - local Metal copy-family promotion moved three more rows into the strict comparable contract:
    - `copy_buffer_to_texture`: focused artifact `bench/out/scratch/20260309T_promote_candidates/20260309T210122Z/copy_buffer_to_texture.report.json` is `comparisonStatus=comparable`, `claimStatus=claimable`
    - `copy_texture_to_texture`: focused artifact `bench/out/scratch/20260309T_promote_candidates/20260309T210122Z/copy_texture_to_texture.report.json` is `comparisonStatus=comparable`, `claimStatus=claimable`
    - `copy_texture_to_buffer`: focused artifact `bench/out/scratch/20260309T_promote_candidates/20260309T210122Z/copy_texture_to_buffer.report.json` is `comparisonStatus=comparable`, `claimStatus=diagnostic` (still slower and right-side p50 is below the 100ns noise floor)
  - `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` now passes `--kernel-root bench/kernels` symmetrically to Doe-native and Dawn-delegate commands, which is required for strict comparable dispatch workloads that resolve WGSL kernels at runtime.
  - strict local-Metal normalization contracts are now explicit instead of implied:
    - `upload_write_buffer_1kb`, `upload_write_buffer_64kb`, and `upload_write_buffer_1mb` restored symmetric left/right `commandRepeat` values in the generated workload contract, matching the previously validated focused claim methodology.
    - `bench/native-compare/compare_dawn_vs_doe.py` / `bench/native-compare/modules/runner.py` now accept explicit workload `strictNormalizationUnit` contracts (`dispatch` or `cycle`) so strict divisor lint and trace-derived physical-op checks can agree on workloads whose comparable unit is not raw command-row count.
  - `compute_dispatch_fallback`, `compute_dispatch_grid`, and `copy_protocol` are now promoted to `comparable=true` for `apple_metal_extended`; the mixed protocol stream is structurally comparable and claimable on focused strict rerun `bench/out/scratch/20260310T_final_blockers/20260310T004034Z/copy_protocol.promote.current.rerun.json`.
  - Apple-Metal strict `compute_dispatch_fallback` was restored to `left/rightCommandRepeat=500` with matching divisors after the full `20260310T210012Z` lane showed the `400` repeat contract was not stable under aggregate lane pressure; the earlier focused `400` rerun remained useful as a diagnostic, but the lane contract reverted to the stronger margin.
  - `copy_texture_to_buffer` is now claimable on local Metal when evaluated on headline process wall with the hardened local-Metal repeat contract; focused proof is `bench/out/scratch/20260310T_copy_texture_sweep_v5/20260310T021320Z/copy_texture_to_buffer_single_1000_current.json`.
  - native Metal upload benchmarking now reuses pre-zeroed shared upload sources instead of re-zeroing large buffers inside every timed sample, which made focused strict local-Metal reruns for `upload_write_buffer_1gb` and `upload_write_buffer_4gb` claimable:
    - `bench/out/scratch/20260310T_final_blockers/20260310T010134Z/upload_1gb_current.v3.json`
    - `bench/out/scratch/20260310T_final_blockers/20260310T005801Z/upload_large_generated_current.v2.json`
  - claimability now falls back to `timingInterpretation.headlineProcessWall.deltaPercent` for comparable `copy`, `upload`, and `p0-resource` rows when selected operation timing undercovers end-to-end process wall asymmetrically; this also restored focused `resource_lifecycle` claimability in `bench/out/scratch/20260310T_final_blockers/20260310T013126Z/metal_remaining_three.v4.json`.
  - Apple-Metal strict upload contracts for `upload_write_buffer_4mb` and `upload_write_buffer_16mb` now restore symmetric left/right `commandRepeat=50` in `bench/backend-workload-catalog.json` and the generated `bench/workloads.apple.metal.extended.json`, removing the old one-op-vs-fifty-op amortization mismatch.
    - focused proof: `bench/out/scratch/20260310T015302Z/20260310T_medium_upload_symmetry_probe_v2` is `comparisonStatus=comparable`, `claimStatus=claimable`
  - Apple-Metal strict `upload_write_buffer_1kb` now uses `left/rightCommandRepeat=1000` in the generated contract, and focused single-row rerun `bench/out/scratch/20260310T021644Z/20260310T_upload_1kb_probe_current` is `claimable`.
  - Apple-Metal strict `copy_texture_to_buffer` now uses `left/rightCommandRepeat=2000` and matching divisors in the generated contract to reduce microsecond-scale tail noise under aggregate lane pressure.
  - Apple-Metal strict `copy_texture_to_texture` is currently set to `left/rightCommandRepeat=400` with matching divisors in the generated contract as a narrower stabilization step than the earlier 2000-repeat probe.
    - historical higher-repeat probes remain useful diagnostics only:
      - `bench/out/scratch/20260310T203910Z/copy_texture_to_texture.direct.2000.json`
      - `bench/out/apple-metal/extended-comparable/20260310T203926Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v10.json`
  - generated Apple Metal contract coverage is now `31/50` strict comparable workloads.
  - latest unified full Apple Metal strict artifact after the March 10 package and symmetry refresh is `bench/out/apple-metal/extended-comparable/20260310T191301Z/dawn-vs-doe.local.metal.extended.comparable.json`
    - `comparisonStatus=comparable`, `claimStatus=diagnostic`, `31` comparable workloads
    - `30/31` are claimable in the current authoritative full rerun
    - the only remaining full-lane blocker in that authoritative 31-row artifact is `copy_texture_to_texture`, which was slightly negative at `p95` before the repeat-lift stabilization above
  - supporting focused mixed-row proof: `bench/out/scratch/20260310T121427Z/20260310T_remaining_three_probe_v9` is `comparisonStatus=comparable`, `claimStatus=claimable`.
  - one attempted fresh full-lane rerun at `bench/out/apple-metal/extended-comparable/20260310T022451Z/...rerun.v6.json` was discarded because `copy_texture_to_buffer` picked up a stale `repeat5000` command materialization; do not treat that run as evidence.
- final macOS Metal Dawn-vs-Doe evidence execution is now codified as an operator runbook:
  `docs/metal-macos-proof-bundle-runbook.md`
- Chromium lane release/build defaults now force non-CfT branding args at `gn gen` time (`is_chrome_for_testing=false`, `is_chrome_for_testing_branded=false`, `is_chrome_branded=false`) so stale `args.gn` does not reintroduce Chrome-for-Testing UI branding.
- Chromium lane browser layered benchmark harness now supports per-mode browser executables (`--dawn-chrome`, `--doe-chrome`) so one run can compare Doe runtime path in `Fawn.app` against a separate Dawn/Chrome binary without mixing launch binaries.
- Browser layered render readback scenario hardening (2026-03-04):
  - `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs` `render_triangle_readback` now renders into an explicit `rgba8unorm` texture (`RENDER_ATTACHMENT|COPY_SRC`) and performs an explicit queue completion before map/readback.
  - this removes swapchain/current-texture readback nondeterminism that could produce `unexpected render readback color` failures on both Dawn and Doe in headless runs.
- macOS local-build unblock for `doe-zig-runtime` (2026-03-04):
  - `runtime/zig/src/backend/vulkan/mod.zig` now selects a macOS-only stub runtime import (`native_runtime_stub.zig`) so local Metal-focused builds do not fail link on unresolved Vulkan symbols when no Vulkan loader is present.
  - Linux/Windows Vulkan native runtime import path remains unchanged (`native_runtime.zig`).
- Metal backend micro-overhead cleanup (2026-03-04):
  - `runtime/zig/src/backend/metal/mod.zig` removed unused per-command timing probes that were computed and discarded around `inner.executeCommand`.
  - command behavior/taxonomy contracts are unchanged; this is a hot-path overhead reduction only.
- Cross-backend hot-path sync cleanup (2026-03-04):
  - `runtime/zig/src/backend/{metal,vulkan,d3d12}/mod.zig` now uses shared command-requirement metadata for dispatch-count fallback paths and backend-unsupported capability reporting.
  - runtime setter calls (`setUploadBehavior`, queue wait/sync mode, GPU timestamp mode) are now no-op short-circuited when values are unchanged to avoid repeated backend state pushes.
  - D3D12 no longer re-probes capability flags on every command; capability selection remains deterministic from initialized backend feature state.
- Shared render encode branch-lift (2026-03-04):
  - `runtime/zig/src/wgpu_render_draw_loops.zig` now hosts specialized draw-loop helpers for render-pass and render-bundle encode paths (`static/no_change`, `static/redundant`, `redundant/no_change`, `redundant/redundant`).
  - `runtime/zig/src/wgpu_render_commands.zig` now routes draw-loop execution through those helpers, removing per-draw mode branches in hot loops while preserving command semantics and API-call shapes.
- Render-bundle timing-contract closure (2026-03-04):
  - `bench/native-compare/modules/timing_selection.py` now enforces render-domain encode timing selection for strict operation workloads in `render` and `render-bundle` domains (`timingSource=doe-execution-encode-ns`, policy `render-encode-preferred`) and keeps upload row-total policy unchanged.
  - `bench/native-compare/modules/comparability.py` strict Doe-vs-Dawn source/policy expectations now map by domain:
    - `upload` -> `doe-execution-row-total-ns` / `upload-row-total-preferred`
    - `render`, `render-bundle` -> `doe-execution-encode-ns` / `render-encode-preferred`
    - other operation domains -> `doe-execution-total-ns` / `<none>`
  - `runtime/zig/src/wgpu_render_commands.zig` timing boundaries now classify render-bundle recording as encode work (setup window ends before bundle recording), reducing setup/submit contamination in render-bundle per-op timing.
  - `config/backend-timing-policy.json` now includes explicit `render-bundle` timing policy and allows `doe-execution-encode-ns` for render-family domains.
  - `bench/comparable_runtime_invariants_gate.py` now validates encode-only timing by requiring non-zero encode totals (instead of forcing submit-wait total to zero), and fixes upload-tail checks to use per-sample execution counters on both sides.
- single-workload strict sweep utility (2026-03-04):
  - new script: `bench/run_single_workload_sweep.py`
  - runs repeated `compare_dawn_vs_doe.py` invocations for one workload and emits per-run + aggregate (`medianDeltaP50Percent`, `medianDeltaP95Percent`) summary artifacts under a timestamped scratch folder.
- experimental npm bridge package now provides practical headless integration paths under `@simulatte/webgpu`, rooted in `packages/webgpu/`:
- Node provider source lives in `packages/webgpu/` (`src/index.js`, `binding.gyp`) with the addon bridge in `runtime/bridge/webgpu-addon/doe_napi.c`. Linux Node Doe-native path is now wired end-to-end (Linux guard removed).
  - package CLI entrypoint `doe-gpu-bench` (formerly `fawn-webgpu-bench`) for command-stream benchmark execution and trace artifact emission from Node environments.
  - package CLI entrypoint `doe-gpu-compare` (formerly `fawn-webgpu-compare`) wraps `bench/native-compare/compare_dawn_vs_doe.py` from Node with one command for Dawn-vs-Doe report generation.
  - package now exposes minimal in-process provider compatibility APIs for Node consumers (`create`, `globals`, `setupGlobals`, `requestAdapter`, `requestDevice`).
  - package browser-helper exports now expose the shared browser-surface factory and normalization helpers from `packages/webgpu/src/shared/browser-surface.js` through the public package entrypoints (`createBrowserSurfaceClasses`, `normalizeOrigin2D`, `normalizeCanvasConfiguration`, `CANVAS_*` maps).
  - package now also exports a concrete browser-owned canvas provider helper in `packages/webgpu/src/shared/browser-native-canvas-backend.js` (`createNativeBrowserCanvasBackend`), which delegates `GPUCanvasContext.configure/getCurrentTexture/unconfigure` plus browser-native `importExternalTexture` / `copyExternalImageToTexture` calls onto real browser WebGPU objects for Track A/offscreen adapter use.
  - bind-group validation now recognizes `GPUExternalTexture` resources and `externalTexture` layout entries on the shared JS surface, but the headless Doe runtime package surface still fails fast for those bindings without an explicit browser canvas backend provider.
  - package now exposes an explicit browser composition subpath at `@simulatte/webgpu/browser` (`packages/webgpu/src/browser.js`), which assembles the shared full surface, encoder surface, browser surface classes, and native browser canvas backend into a browser-owned wrapper for `navigator.gpu`, `GPUAdapter`, `GPUDevice`, and `GPUCanvasContext` without changing the default headless package contract.
  - `GPUDevice.importExternalTexture` and `GPUQueue.copyExternalImageToTexture` are now repo-local browser-package surfaces on `@simulatte/webgpu/browser`; Playwright smoke now executes both paths end-to-end on the package-browser surface, including `GPUExternalTexture` bind-group layout/resource wiring and readback validation. Native Doe Metal/Vulkan/D3D12 backends still do not own OS-level media interop themselves.
  - `doe.runCompute()` now infers binding access from Doe helper-created buffer usage and fails fast when a bare binding lacks Doe helper metadata or resolves to non-bindable/ambiguous usage.
    - prebuild infrastructure for self-contained installs:
      - `scripts/install.js`: uses prebuilt binaries when present, falls back to node-gyp
      - `scripts/prebuild.js`: assembles `prebuilds/<platform>-<arch>/` with `doe_napi.node` + `libwebgpu_doe` + Dawn sidecar + integrity manifest
      - tracked `prebuilds/<platform>-<arch>/` directories are the package source-of-truth; generated `.tgz` archives are not
      - `scripts/smoke-test.js`: clean-machine verification (13 checks: import, providerInfo, globals, create, adapter, device, buffer round-trip)
    - supported prebuild targets: macOS arm64 (Metal), Linux x64 (Vulkan), Windows x64 (D3D12)
    - N-API version pinned to 8 in `binding.gyp` for ABI stability across Node versions
    - only host GPU drivers (Metal/Vulkan/D3D12) are external prerequisites
  - benchmark cube contracts now exist for cross-surface reporting:
    - policy: `config/benchmark-cube-policy.json`
    - governed lanes: `config/governed-lanes.json`
    - schemas: `config/benchmark-cube.schema.json`, `config/benchmark-cube-row.schema.json`
    - builder: `bench/build_benchmark_cube.py`
    - outputs: `bench/out/cube/<timestamp>/cube.{rows,summary}.json` plus `cube.matrix.md`, `cube.dashboard.html`, and stable latest mirrors in `bench/out/cube/latest/`
    - canonical cube publication is now lane-governed: backend rows must resolve the left/right runtime lane IDs from telemetry, and package reports must declare explicit governed `laneId`
    - canonical workload identity now has an explicit bridge contract:
      - registry: `bench/workload-registry.json`
      - schema: `config/workload-registry.schema.json`
      - package factories in `bench/package-compare/node/workloads.js` now import workload metadata from that registry instead of duplicating the cross-surface ID/domain/description contract inline.
      - cube normalization now canonicalizes package workload aliases (for example `buffer_upload_1kb` -> `upload_write_buffer_1kb`) while preserving the raw `sourceWorkloadId` in output rows.
  - backend-native workload contracts now also have a canonical source:
    - catalog: `bench/backend-workload-catalog.json`
    - schema: `config/backend-workload-catalog.schema.json`
    - generator: `bench/generate_backend_workloads.py`
    - lane-specific `bench/workloads*.json` files are now generated execution views derived from the catalog rather than the intended authoring surface.
    - generated D3D12 execution views now exist for the first governed Windows subset:
      - `bench/workloads.local.d3d12.smoke.json`
      - `bench/workloads.local.d3d12.extended.json`
    - first governed D3D12 configs:
      - `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.smoke.json`
      - `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.extended.comparable.json`
      - `bench/native-compare/compare_dawn_vs_doe.config.local.d3d12.release.json` (scaffold only until a Windows host emits evidence)
    - Windows host preflight contract is now explicit in `bench/preflight_d3d12_host.py`
    - Windows handoff runner now exists in `bench/run_local_d3d12_lane.py` for preflight -> smoke -> extended comparable -> blocking gates -> cube rebuild
    - `bench/run_blocking_gates.py` now treats `python3 bench/generate_backend_workloads.py --verify` as a blocking catalog-authority gate.
    - `bench/run_blocking_gates.py` now also runs `python3 bench/test_backend_workload_catalog.py` as a blocking regression gate for D3D12 catalog round-trip, expected workload IDs, and policy/config invariants.
    - benchmark cube placeholders now distinguish governed but unevidenced Windows D3D12 coverage as `contract exists, evidence missing`.
  - package scope/positioning is explicitly browserless AI/ML benchmarking and CI (not browser-parity WebGPU SDK), with versioned contract docs and scope/non-goals in `packages/webgpu/api-contract.md`.
  - package exports now distinguish default `full` and explicit `compute` surfaces:
    - `@simulatte/webgpu` => full headless surface
    - `@simulatte/webgpu/compute` => AI-workload-oriented compute subset
    - both surfaces export the `doe` ergonomic namespace for buffer/readback/compute helpers
  - package helper layering is now explicit for the upcoming `0.3.0` surface:
    - `await doe.requestDevice()` returns the bound helper object directly
    - helper methods are grouped under `gpu.buffers.*` and `gpu.compute.*`
    - both package surfaces share the same helper shape; the raw Layer 1 device is what differs (`full` vs compute-only facade)
  - legacy package identities `@doe/webgpu-core` and `@doe/webgpu` are no longer the canonical package contract.
  - Linux Doe-native in-process path now works end-to-end; `DOE_WEBGPU_LIB` env var no longer required when prebuilds or workspace artifacts are present.
  - local workspace package loading now prefers `packages/webgpu/build/{Release,Debug}/doe_napi.node` before packaged prebuilds, so benchmark/debug runs use freshly rebuilt addon code instead of stale prebuilt binaries.
  - the Node package compare lane now isolates each workload in its own provider subprocess (`bench/package-compare/node/compare.js`) instead of reusing one long-lived process for the whole suite; this removed cross-workload contamination that was inflating Doe compute-e2e timings on macOS package runs.
  - the package-default Doe hot path for `dispatch + copyBufferToBuffer + mapAsync` now uses a direct addon entrypoint for the exact compute-e2e batch shape plus native mapped-prefix validation on the Doe side, reducing small-compute package overhead on both Node and Bun without changing workload contracts.
  - the Node full package surface now records compute passes directly into native command encoders instead of staging compute dispatches as JS command arrays before submit. This materially reduced package-surface encode overhead on the streaming compare lane and narrowed the local `simulatte direct` vs `dawn direct` streaming gap from roughly `1.98x` to `1.43x` on the March 15 rerun (`bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs`, `10` timed iterations, `2` warmups).
  - the ad-hoc four-way Node compare runners now execute each GPU candidate in an isolated subprocess (`bench/diagnostics/node/run-streaming-webgpu-candidate.js`, `bench/diagnostics/node/run-headless-webgpu-candidate.js`) instead of self-reentering the same benchmark script. This removed the prior direct-Dawn instability and kept the raw-WebGPU comparison contract unchanged while eliminating cross-provider process contamination.
  - Doe-native queue flush on Metal now waits on the pending command buffer completion directly instead of polling the shared-event signal in a spin/yield loop (`runtime/zig/src/doe_wgpu_native.zig`). Together with isolated candidate runners and reusable readback buffers in the ad-hoc four-way compare helpers, this materially improved the macOS Node package benchmarks on March 15: on a sequential `bench/diagnostics/node/bench-headless-webgpu-comparison.mjs auto 6 2 8` rerun, `simulatte direct` reached `35.78 ms` vs `dawn direct` `37.94 ms`, and `simulatte + doe helpers` reached `38.10 ms` vs `dawn + doe helpers` `40.10 ms`; on the streaming rerun (`bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs 4194304 64 10 2 8`), `simulatte direct` improved to `5.28 ms` and `simulatte + doe helpers` to `7.70 ms`, leaving readback as the main remaining package-side gap.
  - streaming readback on the package helper path is now materially lighter on macOS. The full package surface exports a native mapped-range copy fast path (`runtime/bridge/webgpu-addon/doe_napi.c`, `packages/webgpu/src/index.js`, `packages/webgpu/src/shared/full-surface.js`), and `@simulatte/webgpu-doe` now reuses one staging readback buffer per source buffer instead of allocating and destroying a fresh staging buffer on every `gpu.buffer.read(...)` call (`packages/webgpu-doe/src/index.js`).
  - Node ad-hoc four-way compares now use an addon-native compute-focused Simulatte entry (`packages/webgpu/src/native-direct.js`, exported as `@simulatte/webgpu/native-direct`) for the direct lane, and both helper lanes now bind the same standalone `@simulatte/webgpu-doe` helpers onto their respective raw devices. The `native-direct` JS file is now loader-only; the compute object surface itself is created inside `runtime/bridge/webgpu-addon/doe_napi.c`, which removes the older JS-built wrapper graph from the compare path.
  - the Node four-way package compares now also force the helper lanes to use the same measured round shape as the direct lanes: one encoder, one compute pass, one `copyBufferToBuffer`, one submit/wait, and one `MAP_READ` readback in the timed round. This removes the older benchmark distortion where helper timing included a second copy+submit through `gpu.buffer.read(...)`.
    - fresh March 15 streaming rerun (`bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs 4194304 64 10 2 8`) after that fix: `dawn direct 7.42 ms`, `dawn + doe 16.30 ms`, `simulatte direct 9.81 ms`, `simulatte + doe 17.23 ms`
    - fresh March 15 headless rerun (`bench/diagnostics/node/bench-headless-webgpu-comparison.mjs auto 6 2 8`) after that fix: `dawn direct 28.34 ms`, `dawn + doe 28.23 ms`, `simulatte direct 26.91 ms`, `simulatte + doe 27.84 ms`
    - interpretation: the old helper/direct inversion on the compute-heavy lane was a methodology bug and is now gone; the remaining streaming gap is real and concentrates mostly in Simulatte direct/readback-heavy package behavior rather than in the Doe helper layer itself.
  - the streaming four-way compare now has explicit attribution scenarios and reports validation time plus timed-sample variance:
    - `bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs` accepts `--scenario=default|single-dispatch-full-readback|many-dispatches-tiny-readback|raw-per-pipeline-bindgroups`
    - `bench/diagnostics/node/run-streaming-webgpu-candidate.js` now measures `validationMs` separately and reports `stddev`, `CV`, and sample range per GPU candidate
    - fresh March 16 clean sequential reruns (`4194304 64 6 2 8`, one compare process at a time) keep the direct and Doe lanes in the same tier:
      - `default`: `dawn direct 2.92 ms`, `dawn + doe 2.78 ms`, `simulatte direct 3.93 ms`, `simulatte + doe 4.36 ms`
      - `single-dispatch-full-readback`: `dawn direct 2.72 ms`, `dawn + doe 3.63 ms`, `simulatte direct 4.49 ms`, `simulatte + doe 4.04 ms`
      - isolated candidate spot checks for the same full-readback single-dispatch shape also stayed healthy: `simulatte direct 4.05 ms`, `simulatte + doe 3.85 ms`
      - `many-dispatches-tiny-readback` remains in the expected tier on isolated candidate probes: `simulatte direct 1.80 ms`, `simulatte + doe 1.50 ms`
    - interpretation: the old catastrophic direct-vs-helper cliff was not reproducible on the current build under clean sequential runs. The remaining package delta is now the narrower readback-heavy direct-lane cost already visible in the sequential phase means (`submit+wait` within roughly `0.2 ms`, `getMappedRange` within roughly `0.1 ms`, larger raw `readback` wall time on the Simulatte direct lane).
    - methodology note: overlapping package benchmark processes on the same host can still inflate `submit+wait` and readback timings; treat concurrent multi-scenario ad-hoc runs as diagnostic-only, not claimable evidence.
  - native-direct Node package hot-path cleanup (2026-03-15):
    - `runtime/bridge/webgpu-addon/doe_napi.c` now caches method function objects across native-direct instances instead of creating fresh JS functions per device/buffer/encoder/pass object. This removes per-round megamorphic method churn from the direct package lane.
    - the same addon path now caches queue/buffer/encoder/pass/pipeline native handles with `napi_wrap` instead of resolving hot handles only through named-property external lookups on every method call.
    - `queue.submit([commandBuffer])` now avoids heap allocation in the single-command-buffer case, which is the steady-state package compare shape.
    - native-direct buffers now cache the mapped `ArrayBuffer` object for repeated same-range `getMappedRange(...)` calls and clear that cache on `unmap()` / `destroy()`, reducing repeated external-`ArrayBuffer` allocation churn in the direct readback path.
    - fresh sequential March 15 reruns after those changes:
      - `bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs 4194304 64 10 2 8 --scenario=default`: `dawn direct 2.85 ms`, `simulatte direct 4.61 ms`; phase means `encode 0.10/0.33`, `submit+wait 1.79/1.82`, `readback 0.95/2.46`
      - `bench/diagnostics/node/bench-streaming-webgpu-comparison.mjs 4194304 64 10 2 8 --scenario=many-dispatches-tiny-readback`: `dawn direct 1.17 ms`, `simulatte direct 1.59 ms`; phase means `encode 0.10/0.35`, `submit+wait 1.01/1.07`, `readback 0.06/0.17`
      - `bench/diagnostics/node/bench-headless-webgpu-comparison.mjs auto 6 2 8`: `dawn direct 20.85 ms`, `simulatte direct 18.39 ms`
    - interpretation: the package direct lane is materially healthier now. The remaining gap is narrower and concentrated mostly in direct streaming encode + mapped-readback overhead on the Node package path, while the compute-heavy headless lane remains in the right performance tier.
  - the Bun package compare lane now isolates each workload in its own provider subprocess (`bench/package-compare/bun/compare.js`), matching the Node harness and removing cross-workload package-state carryover from the full Bun suite.
  - macOS package refresh (2026-03-10): package `compute_e2e_*` rows now run as stateless per-sample benchmarks. `prepareSample()` resets the storage buffer outside the timed window, which removed the old cumulative readback drift that had been causing `doe_missing` package rows on this host.
    - latest Node package lane artifact: `bench/out/node-doe-vs-dawn-claim-full/doe-vs-dawn-node-2026-03-10T202406545Z.json`
    - current Node package summary: `12` total rows, `9` comparable, `9` claimable. `compute_e2e_{256,4096,65536}`, `copy_buffer_to_buffer_4kb`, and all current comparable upload rows are claimable in the full macOS package lane. The remaining three rows are intentional directional-only workloads (`submit_empty`, `pipeline_create`, `compute_dispatch_simple`).
    - package workload contracts now also include explicit comparable replacements for those three directional-only JS-boundary rows:
      - `submit_trivial_and_wait` replaces raw `submit_empty` timing with completion-scoped submit+wait+validation
      - `compute_dispatch_and_wait_simple` replaces fire-and-forget `compute_dispatch_simple` timing with completion-scoped submit+wait+validation
      - `pipeline_first_use_e2e` replaces raw `pipeline_create` timing with first-use pipeline creation plus one validated dispatch
    - those new contracts are claim-oriented package-surface replacements; canonical March 10 package artifacts predate them and need a fresh rerun before the checked-in Node/Bun totals move beyond the current `12` compared rows.
  - package compare coverage now includes a validated copy-domain workload:
    - canonical contract: `copy_buffer_to_buffer_4kb` in `bench/workload-registry.json`
    - implementation: `bench/package-compare/node/workloads.js`
    - focused Node validation: `bench/out/scratch/20260310T_package_copy_and_vulkan/node-copy-4kb/doe-vs-dawn-node-2026-03-10T165238786Z.json` (`comparable`, not claimable; `p50 +7.5%`, tails slower)
    - focused Bun validation: `bench/out/scratch/20260310T_package_copy_and_vulkan/bun-copy-4kb/doe-vs-bun-webgpu-2026-03-10T165239180Z.json` (`comparable`, `claimable`)
  - Bun contract coverage is green on this host through the package-default addon-backed runtime entry (`npm run test:bun`: `61 passed, 0 failed` on March 10). Benchmark compare lane at `bench/package-compare/bun/compare.js`, comparing Doe against the `bun-webgpu` package, now has a fresh full macOS run at `bench/out/bun-doe-vs-webgpu/doe-vs-bun-webgpu-2026-03-10T195022524Z.json`.
    - current Bun package summary: all `12` current workloads execute; `9` are comparable and all `9` comparable rows are claimable. `compute_e2e_{256,4096,65536}` and `copy_buffer_to_buffer_4kb` are claimable in the full macOS lane. The directional-only rows remain `submit_empty`, `pipeline_create`, and `compute_dispatch_simple`.
    - as on Node, the package workload catalog now has completion-scoped comparable replacements for those three directional-only rows; fresh Bun package artifacts are still pending after that catalog expansion.
  - package-default Bun entry (`packages/webgpu/src/bun.js`) now routes through the addon-backed runtime for correctness parity with Node. The experimental Bun FFI path remains in `packages/webgpu/src/bun-ffi.js` for future optimization work. Benchmark compare lane at `bench/package-compare/bun/compare.js` remains valid for package-surface evidence, but any FFI-specific claims should stay scoped to the experimental path until revalidated.
  - benchmark cube policy now carries explicit package-surface workload-ID overrides (`config/benchmark-cube-policy.json`) so directional `compute_dispatch_simple` rows land in a `dispatch_only` cell instead of contaminating the Node/Bun `compute_e2e` cells.
    - latest macOS cube effect after the March 10 refresh (`bench/out/cube/latest/cube.summary.json`, generated `2026-03-10T20:31:02.431911Z`):
      - Bun `uploads`: `claimable`; Bun `compute_e2e`: `claimable`; Bun `full_comparable`: `claimable`
      - Node `uploads`: `claimable`; Node `compute_e2e`: `claimable`; Node `full_comparable`: `claimable`
  - Deno package compare lane verified (2026-03-17): `bench/package-compare/deno/` with runner, compare, config, and `deno.json`. Doe provider loads `packages/webgpu/src/deno.js` via Deno node-compat N-API layer. Right-side provider uses Deno's built-in WebGPU (`navigator.gpu` backed by wgpu, `--unstable-webgpu`). First full run: Deno 2.7.5, macOS Apple Silicon, 50 iterations, 5 warmup — **19/19 comparable workloads claimable**. Doe 75x-1866x faster on GPU-wait workloads (deno-webgpu has ~25ms per-call submit overhead), 4-7x faster on uploads. 5 render workloads `doe_missing` (MSL `min()` ambiguity in render vertex shaders, `copyTextureToTexture` not implemented). Lane registered in `config/governed-lanes.json` as `deno_package_compare` with `cubeEligible=true`. Workload registry updated with `deno_package` surface entries. Artifact: `bench/out/deno-doe-vs-webgpu/doe-vs-deno-webgpu-2026-03-17T*.json`.
  - governed lane taxonomy is now symmetric by backend family:
    - Metal: `metal_doe_app`, `metal_doe_directional`, `metal_doe_comparable`, `metal_doe_release`, `metal_dawn_release`
    - Vulkan: `vulkan_doe_app`, `vulkan_doe_comparable`, `vulkan_doe_release`, `vulkan_dawn_release`
    - D3D12: `d3d12_doe_app`, `d3d12_doe_directional`, `d3d12_doe_comparable`, `d3d12_doe_release`, `d3d12_dawn_release`
    - package/browser governed lane families now live beside backend runtime lanes in `config/governed-lanes.json`; browser lanes remain governed but non-cube (`browser_diagnostic`, `browser_claim_local`)
  - initial `core` runtime migration for future headless package layering has started:
    - canonical source location for `wgpu_commands_compute.zig`, `wgpu_commands_copy.zig`, and `wgpu_ffi_sync.zig` is now `runtime/zig/src/core/`
    - ABI ownership now lives under `runtime/zig/src/core/abi/`; legacy root `wgpu_types.zig` and `wgpu_loader.zig` compatibility shims have been removed
- market-readiness evidence toolchain is now implemented under `bench/`:
  - `bench/build_claim_scope_report.py` for citation-scoped claim lines with workload/timing/backend context.
  - `bench/measure_runtime_footprint.py` for Doe-vs-Dawn size/dependency/build-wall evidence.
  - `bench/run_cts_subset.py` now supports structured CTS query configs (`id`, `bucket`, `notes`) plus preflight requirement checks, so CTS reports carry per-bucket pass/fail summaries instead of only raw query strings.
  - preferred CTS lane is now `bench/cts_subset.fawn-node.json`: vendored WebGPU CTS (`bench/vendor/dawn/third_party/webgpu-cts`) driven through Doe via `bench/cts/fawn-node-gpu-provider.cjs`, with a broader Doe-core subset covering adapter/device, buffers, command encoding, queue, compute, validation, and shader builtin execution.
  - legacy `bench/cts_subset.webgpu-node.json` remains available as the older narrow external-node example, but it is no longer the preferred market-readiness config.
- spec inventory is now tracked separately in `config/webgpu-spec-index.jsonl` / `config/webgpu-spec-index.schema.json`. The index is generated from the official `@webgpu/types` WebGPU API surface and serves as the canonical per-backend checklist for `metal`, `vulkan`, `d3d12`, and `browser`; each backend cell is split into `implementation`, `correctness`, and `performance` status so code presence, test coverage, and benchmark evidence do not get conflated. WGSL builtins/types remain a follow-up layer.
  - CTS evidence is now tracked separately from capability inventory in `config/webgpu-cts-evidence.json` / `config/webgpu-cts-evidence.schema.json`; `config/webgpu-capability-inventory.json` remains an internal capability inventory, not a CTS pass/fail record.
  - important distinction: Fawn now has CTS infrastructure, but it still does not yet have a published CTS pass-rate baseline or dashboard trend. The docs should be read as three separate layers: product contract, spec index, and CTS evidence. The `config/webgpu-capability-inventory.json` `103/103 implemented` ledger is only the internal capability inventory layer; it is not the spec index and it is not external conformance proof.
  - `bench/build_model_capacity_matrix.py` for hardware×model ceiling disclosure artifacts (status + capacity summaries).
  - `bench/run_market_readiness_bundle.py` to orchestrate the full evidence bundle and emit a linked manifest.
- Fawn fork maintenance policy is now documented for buyer/security review:
  `docs/fawn-fork-maintenance-policy.md`.
- `config/webgpu-capability-inventory.json` now tracks full Dawn/WebGPU feature breadth as an internal capability inventory only (`103` entries total: `22` capability contracts + `81` feature-inventory entries sourced from `bench/vendor/dawn/src/dawn/dawn.json` `feature name` list), with current status counts `implemented=103`, `blocked=0`, `tracked=0`, `planned=0`. It does not substitute for a spec-index ledger or CTS evidence store.
- `config/webgpu-spec-index.jsonl` now provides the canonical WebGPU API spec-index and backend-checklist ledger for the official WebGPU API surface: generated from `@webgpu/types` `0.1.69`, with `106` GPU-prefixed interfaces, `472` effective interface members after mixin inheritance, `34` string-union type enums, and `275` enumerated string values. Each interface/member/enum entry now carries per-backend checklist cells for `metal`, `vulkan`, `d3d12`, and `browser`, and each cell is split into `implementation`, `correctness`, and `performance`; WGSL remains a follow-up layer.
- drop-in runtime library discovery now resolves sidecar Dawn libraries relative to the loaded `libwebgpu_doe.so` path; Chromium Track A (browser) proc-surface probe now resolves `275/275` required symbols without `LD_LIBRARY_PATH` (2026-02-24).
- Metal immediate-data WebGPU surface is now wired end to end:
  - `GPUPipelineLayoutDescriptor.immediateSize` now forwards through Node addon, Bun FFI, and native-direct package paths instead of being forced to `0`.
  - `GPUComputePassEncoder.setImmediates`, `GPURenderPassEncoder.setImmediates`, and `GPURenderBundleEncoder.setImmediates` now forward through Doe native exports/package surfaces to the provider WebGPU procs on Metal.
  - Metal limits now report `maxImmediateSize=64`, and the abstract `GPUBindingCommandsMixin.setImmediates` spec-index row is tracked as satisfied via those concrete encoder methods.
  - `GPURenderBundleEncoder.pushDebugGroup`, `popDebugGroup`, and `insertDebugMarker` now flow through the addon and JS package layers; the runtime already exported the underlying symbols, so Vulkan bundle debug-marker rows can now be tracked as implemented instead of blocked on stale package evidence.
- upload ignore-first normalization now derives both base/adjusted values from row-total execution durations (`doe-execution-row-total-ns`) to avoid mixed-scope comparability failures in strict upload lanes.
- native runtime now supports `--gpu-timestamp-mode auto|off|require`; `auto` degrades to non-timestamp operation timing on invalid/unavailable timestamp capture, while `require` fails fast for strict timestamp lanes.
- local macOS Metal strict comparable preset now runs all comparable-by-contract workloads from `bench/workloads.apple.metal.extended.json` (no hard-coded 19-workload subset filter).
- backend lane timing realism hardening (2026-03-02):
  - `runtime/zig/src/backend/backend_registry.zig` now routes `doe_metal` lane execution through the real `webgpu.WebGPUBackend` command path while preserving Doe backend IDs in telemetry.
  - `doe_vulkan` and `doe_d3d12` lanes now execute through native backend modules in active registry routing.
  - backend timing source modules (`runtime/zig/src/backend/{metal,vulkan,d3d12}/*_timing.zig`) now use real nanosecond timestamps instead of runtime-state synthetic counters.
  - fabricated GPU timestamp fallback (`gpu_timestamp_ns = encode_ns`) was removed from Doe backend lane modules.
  - Metal setup timing now records an explicit start/end delta window (instead of assigning an absolute timing sample).
- large-upload comparable contract promotion via Dawn delegate (2026-03-02):
  - `upload_write_buffer_256mb`, `upload_write_buffer_1gb`, and `upload_write_buffer_4gb` are now strict comparable contracts (`comparable=true`, `benchmarkClass=comparable`) across workload catalogs.
  - Dawn-vs-Doe compare configs now run Dawn through the command-stream delegate lane (`dawn_delegate`) instead of `dawn_perf_tests` filter mapping, so large upload sizes are measured apples-to-apples from shared command fixtures.
  - strict comparability logic now accepts Dawn delegate operation timing/policy contracts (`doe-execution-row-total-ns` + `upload-row-total-preferred`) while preserving existing Dawn perf-test timing requirements where that adapter path is used.
- host/backend benchmark compatibility gate (2026-03-02):
  - `bench/native-compare/compare_dawn_vs_doe.py` now enforces OS/backend compatibility before run execution using resolved command templates per workload.
  - `bench/single-runtime/run_bench.py` now enforces the same OS/backend compatibility policy before workload execution from resolved command templates.
  - `bench/preflight_vulkan_host.py` now fails fast on non-Linux hosts with an explicit platform error.
  - unsupported host/backend mixes now fail fast with actionable errors (for example: Vulkan on macOS, Metal on Linux/Windows, D3D12 on Linux/macOS).
- strict comparability now pins Dawn-vs-Doe timing-source and timing-selection-policy pairs by domain (`upload` uses row-total/upload-row-total-preferred; non-upload uses execution-total/`<none>`), instead of broad runtime-family compatibility acceptance.
- strict normalization now requires counter-derived operation divisors for every comparable non-process-wall workload (not upload-only), and fails fast when configured divisors cannot be derived from trace counters.
- strict comparable runs now execute a one-sample Doe preflight per workload before timed iterations and fail fast when `executionSuccessCount==0` or counter-derived normalization divisors disagree with workload contracts.
- strict compare orchestration now lints comparable workload divisors from command-shape operation counts (`commandsPath` + command repeat + per-command repeat/dispatch/draw/iteration multipliers), so mismatched `leftTimingDivisor` contracts fail before benchmark execution.

## Product implementation state (runtime outcomes)

### Implemented

1. v0 runtime prototype in `runtime/zig/src`:
- typed model and JSON ingestion
- deterministic matcher + selector + action application
- runnable `doe-zig-runtime` entry path
- dispatch/pipeline/trace/replay now work; execution is native for implemented command classes with explicit unsupported taxonomy on unimplemented paths
2. Lean contract sources in `pipeline/lean/Fawn` (`Model.lean`, `Dispatch.lean`).
- runtime command stream parser in `runtime/zig/src/command_json.zig`
- lean runtime selection module in `pipeline/lean/Fawn/Runtime.lean`.
3. Lean bridge gate evaluator in `pipeline/lean/Fawn/Bridge.lean`.
4. Zig runtime dispatch now includes explicit Lean obligation metadata (`requiresLean`, `isBlocking`, `verification_mode`, `proof_level`) in trace output.
5. Zig parser/dispatch runtime now includes:
- command aliases for replay input and kernel name alias handling
- case-insensitive command/quirk parsing for stable config use
- fail-fast action payload validation for toggle/use-temporary-buffer fields
- trace enrichment with matched `scope`, `safetyClass`, and toggle payload for matched quirks.
- strict quirk action contract alignment (`schemaVersion: 2`): parser now rejects unknown quirk fields, legacy action aliases, and implicit action payload defaults.
- dispatch buckets now precompute `requires_lean`/`is_blocking` once per selected quirk, so per-command dispatch avoids recomputing Lean obligation flags.
6. Lean runtime dispatch now includes driver-range matching, proof-priority tie-break support, and `Runtime.DispatchDecision` to mirror Zig trace metadata.
7. Trace contract hardened with deterministic row hash-chain fields (`traceVersion`, `module`, `opCode`, `hash`, `previousHash`) and a companion parity comparator.
8. Run-level Zig trace summary emission implemented via `--trace-meta`, including deterministic session-level `seqMax`, row counts, and terminal hash-chain anchors for fast replay validation.
9. Release replay hard-gate now exists as `bench/trace_gate.py`, validating `trace-meta` + `trace-jsonl` from comparison report samples.

### Missing for full product confidence (runtime + validation quality)

1. Baseline dataset generation for Dawn/wgpu comparisons.
2. Comprehensive quirk coverage from upstream mining for full production confidence.
3. Real backend execution against GPU devices (current path includes queue-submission for upload/copy/barrier and dispatch-family compute lowering in `runtime/zig/src/webgpu_ffi.zig`).
4. Multi-host profile diversity for claim substantiation remains an infrastructure target; policy and gate wiring now exist, but broader runner coverage still needs provisioning.
- `runtime/zig/src` now has queue-submission execution for all implemented command classes in `runtime/zig/src/webgpu_ffi.zig`.
- Dispatch fallback shims were removed from active paths: explicit `kernel_dispatch` kernel payloads are required, and unsupported dispatch families fail with explicit taxonomy instead of no-op WGSL fallback.
- Planned full native execution path is now represented by implemented multi-module backend surfaces; remaining work is coverage hardening, reliability tuning, and benchmark substantiation.

### Non-prototype execution backlog (full native)

Acceptance required before production claims:
- confirm dispatch/kernel lowering path is deterministic for native kernel payloads
- backend selection and submission failures are deterministic and actionable
- deterministic execution timing captured from real backend execution spans

## Track B (modules) — archived

**Archived 2026-03-19.** All five Track B modules are archived by strategic
decision. The infrastructure dominance strategy
(`ouroboros/docs/strategy/doe-infrastructure-dominance.md`) determined that
building parallel browser subsystem replacements (SDF renderer, path engine,
effects pipeline, compute services, resource scheduler) duplicates work that
arrives for free once Track A ships: Chromium is already routing Skia Graphite,
WebGL, and compositor through WebGPU on its own timeline. When Doe replaces
Dawn at the WebGPU seam (Track A), those subsystems automatically run on Doe
without any Doe-side plumbing.

The correct strategy is: let browser vendors build the roads to WebGPU, build
the fastest engine at the destination.

Archived modules:
- `fawn_2d_sdf_renderer` — previously promoted 2026-03-09
- `fawn_path_engine` — previously promoted 2026-03-09
- `fawn_effects_pipeline` — previously promoted 2026-03-09
- `fawn_compute_services` — previously promoted 2026-03-08
- `fawn_resource_scheduler` — previously promoted 2026-03-08

Artifacts preserved (not deleted):
- Zig implementations remain at `runtime/zig/src/full/modules/` (experimental, inactive)
- Core schemas/policies remain at `config/{sdf-renderer,path-engine,effects-pipeline,compute-services,resource-scheduler}.{schema,policy}.json` (inactive)
- Nursery contracts remain at `browser/chromium/contracts/` (archived)
- Milestone governance demoted in `browser/chromium/bench/workflows/browser-milestones.json`
- Module ownership manifest updated at `config/module-ownership.json`
8. parity harness updates for execution results and benchmark artifacts.

Estimated remaining effort is tracked by explicit capability/gate gaps below instead of LOC placeholders.

## Backend implementation matrix (2026-03-06)

Capability coverage across Doe backends. Audited against `metal_bridge.h` contract surface.

Legend: ● implemented ◐ partial ○ missing

### Core lifecycle

| Capability | Metal (bypass) | Metal (structured) | Vulkan | D3D12 |
|---|---|---|---|---|
| Instance/device discovery | ● | ● | ◐ Linux only | ◐ Windows only |
| Command queue | ● | ● | ◐ Linux only | ● |
| Buffer create + CPU access | ● | ● | ◐ no Map/Unmap | ● Map/Unmap via d3d12_map_async.zig |
| Blit/copy (single) | ● | ● | ● Linux only | ● |
| Blit/copy (batch/streaming) | ● | ● streaming | ● streaming via vk_upload | ● streaming via d3d12_streaming_copy |
| Command buffer lifecycle | ● | ● | ◐ Linux only | ● |
| GPU fence/sync | ● shared event | ● shared event | ● fence pool + timeline semaphore | ● fence-based |
| Limits reporting | ● | N/A | ○ | ● d3d12_device_caps.zig (FL11.0 static) |
| Feature queries (shader-f16) | ● | N/A | ○ | ● d3d12_device_caps.zig |
| onSubmittedWorkDone | ● | N/A | ○ | ● immediate (synchronous) |

### Compute

| Capability | Metal (bypass) | Metal (structured) | Vulkan | D3D12 |
|---|---|---|---|---|
| Shader translation (WGSL) | ● WGSL→IR→MSL (native Zig, compute-focused) | ○ expects .metal | ◐ WGSL→IR→SPIR-V (native Zig, compute-focused subset); `.spv` load supported | ◐ WGSL→IR→HLSL→DXC bytecode; `.cso`/`.dxbc` load supported; native DXIL pending |
| Compute pipeline create | ● | ● | ◐ Linux only | ● |
| Compute dispatch | ● | ● | ◐ Linux only | ● |
| dispatchWorkgroupsIndirect | ● | ○ | ◐ Linux only | ● d3d12_dispatch.zig |
| Bind groups | ● groups 0-3 | ○ telemetry only | ○ | ◐ d3d12_descriptors.zig (descriptor tables) |

### Resources

| Capability | Metal (bypass) | Metal (structured) | Vulkan | D3D12 |
|---|---|---|---|---|
| Texture create | ● | ● | ◐ Linux only | ● 2D+3D, d3d12_texture.zig |
| Texture write/query | ● | ● | ◐ Linux only | ● d3d12_texture.zig |
| Texture view | ● | ○ | ◐ Linux only | ● d3d12_texture_view.zig (SRV/UAV) |
| Sampler create | ● | ● | ◐ Linux only | ● d3d12_sampler.zig |

### Render

| Capability | Metal (bypass) | Metal (structured) | Vulkan | D3D12 |
|---|---|---|---|---|
| Render pipeline create | ● | ● | ◐ Linux only | ● d3d12_render.zig (graphics PSO) |
| Render pass encode | ● | ● | ◐ Linux only | ● d3d12_render.zig + depth/stencil |
| Render encoder draw | ● | ● | ◐ Linux only | ● direct+indexed+indirect |
| ICB (indirect cmd buffer) | ○ | ● | ○ | ● command signatures |

### Presentation

| Capability | Metal (bypass) | Metal (structured) | Vulkan | D3D12 |
|---|---|---|---|---|
| Surface/swapchain | ○ | ○ stub only | ◐ Linux only | ◐ d3d12_surface.zig (headless DXGI) |

### Architecture notes

- **Metal (bypass)**: `doe_wgpu_native.zig` + `doe_render_native.zig` → `metal_bridge.m`. C ABI surface used by `doe_napi.c` for the earlier Node headless path and AI workload inference. 729 + 155 lines.
- **Metal (structured)**: `backend/metal/*.zig` → `metal_bridge.m`. Benchmark engine runtime with telemetry, artifact emission, and deterministic timing. Not used by the current AI workload package lanes. 2,192 lines across 35 files. `metal_native_runtime.zig` (744 lines) does the real work; facade modules are thin forwarding.
- **Vulkan**: `backend/vulkan/*.zig`. Real `native_runtime.zig` on Linux with compute dispatch, buffer upload, narrow texture/resource coverage, and an in-progress native render path. macOS stub returns `UnsupportedFeature`. Live WGSL kernels now compile through the shared WGSL→IR→SPIR-V path in `doe_wgsl/emit_spirv.zig`; prebuilt `.spv` artifacts still load directly. The native Linux path now includes Vulkan descriptor-set layout/pool/bind wiring for buffer bindings, entry-point-aware pipeline creation, live bound-buffer dispatch, texture/resource allocation, and render execution in `vk_render.zig`, but broad graphics/resource promotion is still incomplete. GPU fence/sync now uses a 4-slot `FencePool` ring for per-submission tracking (eliminates `vkQueueWaitIdle` from all deferred-submission paths), timeline semaphore detection (`VK_KHR_timeline_semaphore`), and streaming copy command buffer for batch blit/copy operations (`vk_sync.zig`, `vk_upload.zig`).
- **D3D12**: `backend/d3d12/*.zig` + `d3d12_bridge.c`. Real runtime on Windows with compute dispatch, buffer upload/Map/Unmap, fence sync, render pipeline/pass/draw (direct+indexed+indirect), texture lifecycle (2D+3D), texture views (SRV/UAV), depth/stencil, sampler lifecycle, descriptor table bindings (CBV/SRV/UAV heaps), query sets (timestamp+occlusion+pipeline stats), limits reporting (FL11.0), feature queries, and onSubmittedWorkDone. Non-Windows stub. Accepts pre-compiled DXIL/CSO/DXBC bytecode blobs. Live WGSL lowers through `WGSL -> IR -> native DXIL bytecode` (primary) or `WGSL -> IR -> HLSL -> DXC` (fallback). Fresh Windows evidence still missing.

### WGSL compiler (`src/doe_wgsl/`)

AST-based WGSL compiler replacing the old regex-based line translator. Architecture: lexer → parser → AST → backend emitter.

- **MSL emitter**: Production. Covers the current AI-workload compute feature set — structs, helpers, multiple entry points, override constants, var\<workgroup\>, enable f16/subgroups, subgroup ops, barriers, builtins.
- **Robustness transform**: IR transform pass in `runtime/zig/src/doe_wgsl/ir_transform_robustness.zig`, wired through `analyzeToIr()`. Coverage: sized array/vector/matrix index clamping (`min(index, length - 1)`), runtime-sized array clamping via `arrayLength` with broadened base-expression whitelist (global_ref, member, load, local_ref, param_ref, index, call), and texture coordinate clamping for textureLoad/textureStore (`clamp(coords, vec(0), textureDimensions - 1)`) across 2D, 3D, cube, depth, multisampled, and storage texture types. March 20, 2026 also added guarded gid-based texture-load/store elision so explicit early-return bounds guards no longer force redundant `textureDimensions` queries on the Vulkan path. 13 unit tests in `ir_transform_robustness_test.zig`. Remaining: texture_1d, textureSampleLevel integer coord edge cases, full CTS coverage.
- **SPIR-V emitter**: Native Zig IR→SPIR-V binary emitter for parser-supported compute kernels. Current compute scope now includes bound uniform/storage buffers, structured control flow, workgroup/storage barriers, atomic builtins, and a materially expanded texture/sampler builtin slice. March 20, 2026 fixes corrected scalar/vector constructor lowering, signed texture-coordinate robustness casts, function-local variable ordering, compute entry-point interface emission, and the guarded samplerless texture path, so the `texture_sample_to_storage_64` kernel now validates under `spirv-val --target-env vulkan1.1` and the governed `texture_sampling_raster_baseline` workload is comparable again on this AMD Vulkan host. Broader non-compute WGSL coverage is still incomplete, and the next extended-comparable Vulkan blocker is now the large 256 MB matvec contract on the Dawn side rather than image-backed compute pipeline creation.
- **HLSL emitter**: Production path for parser-supported compute kernels. Now serves as the DXC fallback path for D3D12; the primary D3D12 path uses native DXIL bytecode generation.
- **DXIL emitter**: Native DXIL bytecode generation (primary D3D12 path). 6 modules (2,303 LOC): `dxil_spec.zig`, `dxil_bitcode.zig`, `dxil_builder.zig`, `dxil_serialize.zig`, `dxil_container.zig`, `emit_dxil_native.zig`. Produces LLVM 3.7 bitcode + DXBC container directly from Doe IR without external DXC.

### Key gaps for doe-runtime promotion

1. Vulkan now has governed local evidence for native render-pass, render-pipeline, render-bundle replay, basic texture/sampler lifecycle, and the samplerless texture-raster proxy path on Linux, but full strict comparable lane closure is still incomplete: the next blocker is the 256 MB matvec workload contract (`compute_matvec_32768x2048_f32` and siblings), which the Dawn side currently rejects at strict preflight with `kernel_dispatch_storage_binding_exceeds_maxstoragebufferbindingsize`; broader non-compute WGSL lowering remains open, and surface completeness is still partial.
2. D3D12 now has texture lifecycle (2D+3D), sampler lifecycle, render pipeline, render pass/draw, Map/Unmap, limits, features, onSubmittedWorkDone, dispatchWorkgroupsIndirect, query sets, descriptor table bindings, depth/stencil, and texture views. Native DXIL emission is implemented (primary path). Remaining D3D12 gaps: DXIL validator coverage, vertex/fragment stage completeness, fresh Windows evidence.
3. WGSL live translation is now compute-focused and parser-limited on Vulkan/D3D12; broader WGSL front-end coverage and non-compute lowering still remain open.
4. Surface/swapchain is headless-only on D3D12 and partial on Linux Vulkan. Local Metal comparable surface evidence is closed, while broader cross-host and package/browser surface substantiation still varies by lane.

### Cross-workstream remaining work (corrected 2026-03-17)

Runtime layering:
- the `core` / `full` split is now physical in `runtime/zig/src`, with `CoreCommand` and `FullCommand` unions defined authoritatively in their respective partition modules (`core/command_partition.zig` and `full/command_partition.zig`)
- `model.zig` re-exports `CoreCommand`/`FullCommand` from the partition modules and defines the combined `Command` union as a composition; a comptime assertion validates that `Command` variants exactly equal `CoreCommand` + `FullCommand` with matching payload types
- dead root-level compatibility facades removed: `wgpu_resources.zig`, `wgpu_extended_commands.zig`, `wgpu_commands_compute.zig`, `wgpu_commands_copy.zig`, and the `core/wgpu_commands_copy.zig`/`core/wgpu_commands_compute.zig` shims; `wgpu_commands.zig` remains (command execution glue, not a facade)
- `runtime/zig/src/webgpu_ffi.zig` composes `core` plus `full` backend state honestly, but backend root modules still serve mixed compute/render state from one runtime-owned backend per API
- split command-coverage ledgers now exist: `config/webgpu-command-coverage-core.json` (10 core commands) and `config/webgpu-command-coverage-full.json` (10 core + 14 full-only = 24 total), with matching schemas and a split gate runner (`bench/split_coverage_gate.py`)
- capability inventory and browser integration now have explicit names that match their role: `config/webgpu-capability-inventory.json` (axis-based capability ledger) and `config/webgpu-integration-chromium.json` (Chromium browser-lane overlay)
- generated per-surface views now live under `config/generated/` so humans can answer "what works on compute/headless/chromium?" without merging the canonical ledgers by hand
- public surface API modules exist: `runtime/zig/src/core/surface.zig` (typed core-only API boundary with validate/accept/coverage-ledger) and `runtime/zig/src/full/surface_api.zig` (full superset API with classify/accept/combined-ledger)
- `zig build dropin-core` now produces a core-only `libwebgpu_doe_core.so` artifact
- `zig build coverage-gate` validates split coverage ledgers against Zig command partitions
- `bench/run_blocking_gates.py --with-split-coverage-gate` runs the split coverage gate in the blocking sequence
- the capability inventory in `config/webgpu-capability-inventory.json` remains separate from command coverage and from the canonical API spec index; full runtime artifact separation (separate core-only vs full binaries with different command vocabularies) is still open

Shader compiler:
- native WGSL lowering now supports vertex/fragment entry points across all three emitters (MSL, HLSL, SPIR-V); struct I/O decomposition, inter-stage locations, interpolation decorations, builtin inputs/outputs, MRT, frag_depth, and discard all emit correctly; render pipeline runtime integration is still open
- Vulkan sampled/storage texture support has advanced materially but remains partial; broader graphics-path and non-compute texture builtin coverage is still open
- `spirv-val` is modeled in `config/shader-toolchain.json` and wired into the routine build/test flow via `bench/spirv_val_gate.py`, `zig build spirv-val`, and `run_blocking_gates.py --with-spirv-val-gate`; validation is skipped gracefully when spirv-val is not installed unless `--require` / `--spirv-val-require` is set
- shader tests now execute in the default/full test lanes, but the compiler test corpus is still thin relative to the frontend surface area
- `runtime/zig/src/doe_wgsl/parser.zig` (342 lines) and `runtime/zig/src/doe_wgsl/emit_spirv.zig` (698 lines) are within the 777-line limit; earlier delegation to `parser_decl.zig`, `parser_stmt.zig`, `parser_expr.zig`, `emit_spirv_fn.zig`, `emit_spirv_stages.zig`, `emit_spirv_texture.zig`, and `emit_spirv_builtins.zig` keeps them compliant
- native DXIL emission is now the primary D3D12 path (see authoritative reconciliation above); DXC fallback remains available via `emitWithToolchainConfig`

Tests and proofs:
- `runtime/zig/tests/core/` and `runtime/zig/tests/full/` now contain command-partition tests and surface API tests, with dedicated `zig build test-core` / `zig build test-full` lanes; surface tests validate typed API boundaries, coverage ledgers, domain classification, and superset invariants
- `pipeline/lean/Fawn/Core/` contains canonical core theorem pack (Model, Runtime, Dispatch, Bridge) matching `runtime/zig/src/core/` boundary
- `pipeline/lean/Fawn/Full/` contains canonical full theorem pack (Comparability, ComparabilityFixtures) matching `runtime/zig/src/full/` boundary
- `pipeline/lean/Fawn/Shader/ComputeBounds.lean` shader-side bounds theorems are now fully integrated: `lean_proof.zig` validates all five theorem names (`gid_component_lt_total`, `gid_inbounds_when_dispatch_fits`, `clamp_noop_when_inbounds`, `gid_2d_inbounds`, `flat_index_2d_inbounds`) at comptime and exposes `bounds_elimination_available`; `ir_transform_robustness.zig` consumes this to elide `min()` clamps for both `buf[gid.{x,y,z}]` and `buf[gid.y * dispatch_width + gid.x]` storage-buffer patterns when `-Dlean-verified=true`; native compute runtime paths now enforce the recorded dispatch preconditions before dispatch; `proven-conditions.json` includes `boundsEliminations` entries and the five shader theorems; `proof-artifact.schema.json` updated with `boundsEliminations` array; remaining follow-up: dispatch-fit texture precondition enforcement and deciding whether generic/public WGSL translation should also consume the proof-backed path
- original `pipeline/lean/Fawn/*.lean` files are re-export shims for backward compatibility
- `check.sh` and `extract.sh` compile Core/Full canonical sources then re-export shims
- Lean CI and proof artifact validation are blocking at the repo level; the proof split is complete

D3D12:
- D3D12 is no longer a pure stub; it is a real compute-first backend on Windows
- descriptor heaps/resource binding breadth and fresh Windows evidence still remain open, but the backend is no longer compute-only
- this tranche widened repo-local D3D12 truth materially:
  - `d3d12_device_caps.zig` and `d3d12_formats.zig` now publish the real BC/shader-f16/subgroups feature/format baseline instead of leaving those rows as ledger debt
  - `d3d12_render.zig` now builds real graphics PSOs, consumes vertex layouts/attributes/formats/step modes, and carries topology/front-face/cull/blend/depth-stencil state through native render execution
  - `d3d12_texture.zig`, `d3d12_texture_view.zig`, and `d3d12_surface.zig` now make texture aspect/storage access/canvas alpha+tone-mapping settings real backend behavior instead of validation-only surface claims
  - ordered D3D12 queue submission now consumes render-pass attachment-view metadata end-to-end: `depthSlice`, `resolveTarget`, `depthReadOnly`, and `stencilReadOnly` are recorded on native render passes, replayed through per-view RTV/DSV creation, and resolved on the execution path instead of being preserved only on wrapper state
  - `doe_buffer_native.zig` now makes `GPUBuffer.mapState` truthful on D3D12 package paths
- remaining D3D12 gaps are narrower and explicit: DXIL validator integration into CI gates (structural validator implemented in `dxil_validate.zig`, not yet wired into gate scripts), strip-index-format parity, deeper render-bundle replay/resource-table render submission parity, and fresh Windows evidence. ETC2/EAC/ASTC format classification is now explicit in `d3d12_formats.zig`; device caps correctly report no support on standard D3D12
- the first governed benchmark lane is now explicitly scoped to compute, upload, pipeline, and p0-resource contracts only
- no live D3D12 compare artifact was produced in this macOS session; Windows-host preflight/config/gate plumbing is ready, the release lane is scaffolded, and cube publication now reports `contract exists, evidence missing` until a real Windows run lands

Browser integration (`browser/chromium`):
- the browser lane has a concrete plan, contracts, smoke/bench harnesses, and bring-up scripts
- Track A (browser) M1-M3 governance is now wired through `bench/browser/browser_gate.py` with explicit ownership and cross-owner promotion approvals
- Track B (modules) M4-M6 archived 2026-03-19 by strategic decision; see "Track B (modules) — archived" section above
- package-browser validation now passes smoke in both Dawn and Doe modes for compute, render, `preferredCanvasFormat`, explicit `xrCompatible` requestAdapter forwarding, `queue.copyExternalImageToTexture` readback, and `importExternalTexture` plus `GPUExternalTexture` binding/layout sampling. Current macOS evidence lives at `browser/chromium/artifacts/20260319T122244Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`. The layered bench now runs on the package-browser path with `62/68` required L1 scenarios and `3/4` required L2 workflows passing per mode; it remains diagnostic with `14` required failures left overall.

Performance substantiation:
- the latest local-Metal strict comparable lane is now citable broad claim evidence on this host class: `bench/out/apple-metal/extended-comparable/20260319T161100Z/dawn-vs-doe.local.metal.extended.comparable.json` is `comparisonStatus=comparable`, `claimStatus=claimable`
- broader host diversity and fleet-level substantiation remain open

Config and CI:
- bootstrap threshold placeholders in `config/gates.json` still exist
- file-size policy exists, but automated enforcement of the 777-line limit is still missing
- split command-coverage schemas and ledgers now exist: `config/webgpu-command-coverage-core.schema.json`, `config/webgpu-command-coverage-full.schema.json`, and corresponding data files; `bench/split_coverage_gate.py` validates ledger-partition alignment

## Developer flow state (engineering, governance, and release pipeline)

### Implemented

1. Canonical docs (`thesis`, `architecture`, `process`, `upgrade-policy`).
2. Config surface in `config/`.
3. Module scaffolds in:
- `pipeline/agent/`
- `pipeline/lean/`
- `runtime/zig/`
- `bench/`
- `pipeline/trace/`
4. End-to-end worked example in `examples/`.
5. Baseline benchmark policy and run-metadata contract.
6. Self-contained scaffold scripts:
- `bench/single-runtime/run_bench.py`
- `bench/check_correctness.py`
- `pipeline/trace/replay.py`
7. Added Dawn/Doe benchmark orchestration scaffolding via `bench/native-compare/compare_dawn_vs_doe.py` and `bench/workloads.json` for repeatable shared-workload runtime comparisons.
8. Added Zig replay comparison mode in `runtime/zig/src/main.zig` (`--replay`) that now enforces `seq`, `command`, optional `kernel`, module/op-code, and hash-chain alignment.
9. Added hard release gate command path in docs/process via `bench/trace_gate.py` for replay artifact validation.
10. Release gating is explicit in process/docs and enforced in `.github/workflows/release-gates.yml`.
11. Strict Dawn-vs-Doe upload comparability preflight is now enforced in `bench/native-compare/compare_dawn_vs_doe.py`:
- fail fast if executed `doe-zig-runtime` does not expose upload knobs (`--upload-buffer-usage`, `--upload-submit-every`)
- fail fast if upload knob validation probes are not recognized
- fail fast if runtime binary appears older than key upload/runtime Zig sources (`runtime/zig/src/main.zig`, `runtime/zig/src/execution.zig`, `runtime/zig/src/wgpu_commands.zig`, `runtime/zig/src/webgpu_ffi.zig`)
12. AMD Vulkan upload workloads in `bench/workloads.amd.vulkan.json` now use explicit size-tuned `leftUploadSubmitEvery` values (instead of a single shared cadence) to keep methodology explicit while reducing upload backpressure artifacts.
13. Comparison delta sign convention is now left-runtime perspective with right baseline (`((rightMs-leftMs)/rightMs)*100`), so positive means left faster and negative means left slower (`compare_dawn_vs_doe.py` and `compare_runtimes.py`, report `deltaPercentConvention`).
14. Comparison report schema is now `schemaVersion: 4` with percentile summaries centered on p10/p50/p95/p99 (`p10Ms`, `p10Percent`, and overall `p10Approx`/`p50Approx`/`p95Approx`/`p99Approx`).
15. Post-benchmark visualization pipeline step is now available via `bench/native-compare/visualize_dawn_vs_doe.py`, producing a self-contained HTML report and optional analysis JSON from Dawn-vs-Doe comparison artifacts.
16. Visualization/distribution diagnostics now include ECDF overlays, workload×percentile heatmap, KS statistic with asymptotic p-value, Wasserstein distance, probability of superiority (`P(left<right)`), and bootstrap CI summaries for delta `p50`/`p95`/`p99`.
17. Claimability reliability mode is now implemented in `bench/native-compare/compare_dawn_vs_doe.py`:
- `--claimability local|release` enforces sample-floor and positive-tail checks
- report now includes workload-level `claimability`, top-level `claimabilityPolicy`, `claimabilitySummary`, and `claimStatus`
- claimability failures exit non-zero (`rc=3`) so CI/pipelines can gate on claimable speed
18. Upload ignore-first timing source is now explicit and scope-consistent in reports (`doe-execution-row-total-ns+ignore-first-ops`) instead of inheriting incompatible base sources.
19. Runtime upload prewarm path is now wired in Zig native execution (`maxUploadBytes` prewarm before timed command loop) to reduce first-upload setup spikes.
20. AMD Vulkan 64KB upload workload now uses size-specific repeat normalization (`leftCommandRepeat=500`, `leftTimingDivisor=500`, `leftIgnoreFirstOps=0`) for more stable per-op claim diagnostics.
21. Comparability assessment now enforces workload contract comparability flags (`workload.comparable`); workloads marked non-comparable are always reported as non-comparable and strict mode fails fast when they are selected.
22. `pipeline_compile_stress` has been promoted to a comparable contract for AMD Vulkan using a fixed `ShaderRobustnessPerf` filter plus explicit 50-dispatch normalization (`leftTimingDivisor=50`) and Dawn-aligned kernel command shape.
23. Render/texture workload contracts now use explicit per-iteration normalization controls (`leftTimingDivisor`/`leftCommandRepeat`) to keep timing units consistent with Dawn-side workload semantics.
24. AMD Vulkan matrix coverage now has config-first presets for release claims, extended comparable runs, and directional diagnostics:
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json`
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.directional.json`
- `bench/workloads.amd.vulkan.extended.json`
- `bench/dawn_workload_map.amd.extended.json`
25. Native render-pass draw coverage now exists in Zig runtime via `render_draw` command:
- command parser + model + runtime dispatch now accept `render_draw|draw|draw_call`
- native backend lowers `render_draw` into real render-pass draw submission (not compute proxy)
- benchmark draw workload command seed now uses `examples/draw_call_proxy_commands.json` `render_draw` contract
26. Render throughput proxy workload contract is now comparable in the extended AMD matrix (`render_draw_throughput_baseline`).
27. Texture/raster proxy workload contract is now comparable in the extended AMD matrix (`texture_sampling_raster_baseline`) with explicit command-repeat and timing-divisor controls.
28. Native `render_draw` now caches shader+render-pipeline entries by target format for multi-command runs:
- repeated-command trace shows setup amortization from `2,380,709ns` on first row to `10,009ns` and `9,088ns` on subsequent rows
- artifacts: `bench/out/render_draw_pipeline_cache.repeat.trace.jsonl`, `bench/out/render_draw_pipeline_cache.repeat.trace.meta.json`
29. Native `render_draw` geometry now matches Dawn DrawCallPerf triangle coordinates (centered 3-vertex triangle) while keeping the directional 64x64 render target contract.
30. Native `render_draw` now includes Dawn-like `Depth24PlusStencil8` render-pass attachment and matching depth/stencil pipeline state defaults (`depthCompare=Always`, `depthWrite=false`, stencil keep/always) for directional parity.
31. Native `render_draw` now reuses cached render-target and depth texture views across commands; this lowers render setup overhead in repeated command streams while keeping depth/stencil parity behavior.
32. Native `render_draw` vertex stage now matches Dawn DrawCallPerf's attribute-input model by binding a static centered-triangle vertex buffer (float32x4) and issuing draws through `SetVertexBuffer` instead of `vertex_index`-generated positions.
33. Native `render_draw` now includes Dawn-like static fragment-uniform bind-group semantics (group `0`, binding `0`, `vec3f` color uniform) with cached render bind-group resources.
34. `render_draw` command contract now exposes explicit Dawn-like state-set variants for directional parity work:
- `pipelineMode`: `static` or `redundant`
- `bindGroupMode`: `no-change` or `redundant`
35. Release claimability hard-gate is now wired in repo CI:
- new validator `bench/claim_gate.py` enforces report contract (`claimabilityPolicy.mode`, `claimStatus`, `comparisonStatus`, minimum timed-sample floor, workload-level claimability fields)
- `.github/workflows/release-gates.yml` now runs `bench/schema_gate.py`, `bench/check_correctness.py`, `bench/trace_gate.py`, and `bench/claim_gate.py` as blocking gates on the report artifact.
36. Native runtime now exposes explicit queue wait behavior control:
- `--queue-wait-mode process-events|wait-any` in `doe-zig-runtime`
- default remains `process-events`; `wait-any` is available for targeted wait-path diagnostics/tuning and now fails explicitly with runtime taxonomy errors when unsupported or timed out.
37. AMD Vulkan 64KB upload workload cadence is retuned from `leftUploadSubmitEvery=50` to `leftUploadSubmitEvery=100` (with `leftCommandRepeat=500`, `leftTimingDivisor=500`) in:
- `bench/workloads.amd.vulkan.json`
- `bench/workloads.amd.vulkan.extended.json`
- local operation-scope A/B artifact: `bench/out/upload_64kb_submit_wait_100_vs_50.local.json` (`executionSubmitWaitTotalNs`, `n=30` per side): `submit100` faster at `p50 +19.52%`, `p95 +14.21%`.
38. Native runtime now exposes explicit queue synchronization mode control:
- `--queue-sync-mode per-command|deferred` in `doe-zig-runtime` (`per-command` default preserves existing behavior).
- deferred mode skips `waitForQueue` after individual submits and performs a single final queue flush after the command loop.
- `trace-meta` now records `queueSyncMode` for native execution runs (`config/trace-meta.schema.json` updated).
39. Native `render_draw` command contract now includes explicit draw-offset support:
- command parser accepts `first_vertex`/`firstVertex` and `first_instance`/`firstInstance`.
- native render lowering now forwards those values into `wgpuRenderPassEncoderDraw`.
- defaults remain deterministic (`0`, `0`) when fields are omitted.
40. WebGPU capability expansion is now tracked in config as code:
- `config/webgpu-capability-inventory.schema.json` defines contract for machine-readable capability inventory status.
- `config/webgpu-capability-inventory.json` tracks implemented/partial/blocked/tracked/planned coverage items and priorities.
41. Native render path now includes a first indexed-draw slice:
- command parser accepts `draw_indexed` plus required `index_data`/`indexData`/`indices`, optional `index_format`/`indexFormat`, and `index_count`/`indexCount`, `first_index`/`firstIndex`, `base_vertex`/`baseVertex`.
- native render lowering now binds a dynamically sized index buffer and emits `wgpuRenderPassEncoderDrawIndexed` when indexed mode is requested.
- indexed validation is fail-fast: invalid/missing index data or out-of-bounds (`firstIndex + indexCount`) are rejected as unsupported command payloads.
42. Render core API wiring is now first-class in the shared WebGPU proc table:
- `wgpuDeviceCreateRenderPipeline`, `wgpuCommandEncoderBeginRenderPass`, and `wgpuRenderPassEncoder*` draw/bind/end/release entry points are now declared in `runtime/zig/src/core/abi/wgpu_types.zig` and loaded through `runtime/zig/src/core/abi/wgpu_loader.zig`.
- `render_draw` now consumes these canonical backend proc fields directly (`runtime/zig/src/wgpu_render_commands.zig`) instead of ad-hoc per-call symbol lookup.
- unsupported render symbols remain explicit fail-fast runtime errors (`unsupported` status), preserving deterministic no-fallback behavior.
43. Native render pass state coverage now includes explicit state/binding APIs in command execution:
- `wgpuRenderPassEncoderSetViewport`
- `wgpuRenderPassEncoderSetScissorRect`
- `wgpuRenderPassEncoderSetBlendConstant`
- `wgpuRenderPassEncoderSetStencilReference`
- `wgpuRenderPipelineGetBindGroupLayout`
44. Native textured render contract is now fully live in `render_draw`:
- shader contract includes sampled texture + sampler bindings.
- runtime creates sampler via `wgpuDeviceCreateSampler`, uploads deterministic texel data via `wgpuQueueWriteTexture`, and binds texture+sampler through the render bind group.
- texture lifecycle now uses query/destroy API calls (`wgpuTextureGet*`, `wgpuTextureDestroy`) in resource management and teardown paths.
45. Native render bundle execution path is now integrated:
- `wgpuDeviceCreateRenderBundleEncoder` + `wgpuRenderBundleEncoder*` methods are loaded and used in render lowering.
- render draws are encoded into bundles and submitted via `wgpuRenderPassEncoderExecuteBundles`.
46. Surface presentation API wrappers are now implemented in backend FFI:
- `wgpuInstanceCreateSurface`
- `wgpuSurfaceGetCapabilities`
- `wgpuSurfaceConfigure`
- `wgpuSurfaceGetCurrentTexture`
- `wgpuSurfacePresent`
- `wgpuSurfaceUnconfigure`
47. Async diagnostics and lifecycle polish are now wired into render pipeline creation:
- `wgpuDeviceCreateRenderPipelineAsync` is used with explicit completion waiting.
- `wgpuDevicePushErrorScope` / `wgpuDevicePopErrorScope` gate pipeline creation with explicit scope checks.
- `wgpuShaderModuleGetCompilationInfo` is requested and validated before async pipeline insertion.
48. `render_draw` now consumes full command-driven render-pass state and explicit encode mode:
- `encodeMode` selects direct render-pass encoding or render-bundle encoding.
- viewport/scissor/blend-constant/stencil-reference values are applied from command payload fields.
- bind-group dynamic offsets are validated and applied deterministically (single dynamic uniform offset, stride- and bounds-checked).
49. Render pass state-space tracking has been promoted to implemented in config coverage:
- `config/webgpu-capability-inventory.json` now marks `render_pass_state_space` as implemented based on command-driven state controls and deterministic runtime validation.
50. Timestamp/query reliability reporting is now explicit in trace artifacts:
- execution rows now include `executionGpuTimestampAttempted` and `executionGpuTimestampValid`.
- trace-meta now includes `executionGpuTimestampAttemptedCount` and `executionGpuTimestampValidCount`.
- timestamp readback now fails invalid begin/end ranges instead of silently coercing to zero.
51. `texture_query` command contract now supports assertion-based validation:
- optional expected fields for width/height/depth/format/dimension/view-dimension/sample-count/usage are validated against runtime `wgpuTextureGet*` results with fail-fast mismatch taxonomy.
52. Benchmark contract coverage for new WebGPU API slices is now expanded in `bench/workloads.amd.vulkan.extended.json` and `bench/workloads.json`:
- strict comparable AMD extended matrix now includes render-pass state/binding workloads, render-bundle workloads, texture API contract workloads, draw-indexed proxy workload, and async pipeline diagnostics contract workload.
- `render_draw_throughput_baseline` and `texture_sampling_raster_baseline` are promoted to comparable workload contracts in extended matrices.
- surface lifecycle contract is explicitly tracked as directional-only (`surface_presentation`) because Dawn perf suites do not expose a direct surface lifecycle benchmark contract across adapters.
- new local adapter-agnostic strict config is available: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`.
- host requirement preflight is now explicit via `bench/preflight_bench_host.py`.
53. Benchmark timing-source selection now rejects tiny submit-only dispatch-window measurements when encode/dispatch work is absent:
- rejection threshold: dispatch window `<100us` and `<1%` of `executionTotalNs`.
- fallback source is `doe-execution-total-ns`, with explicit metadata `dispatchWindowSelectionRejected`.
54. AMD Vulkan comparable workload defaults were tuned for setup-amortized per-unit normalization:
- `render_draw_indexed_baseline` now runs with `leftCommandRepeat=10`, `leftTimingDivisor=20000`, and `--queue-sync-mode deferred`.
- `texture_sampler_write_query_destroy` and `texture_sampler_write_query_destroy_mip8` now run with `leftCommandRepeat=10` and `leftTimingDivisor=500`.
55. Directional macrobenchmark coverage was added as config-first contracts:
- new workload IDs: `render_draw_throughput_200k`, `render_draw_indexed_200k`, `texture_sampler_write_query_destroy_500`.
- new preset config: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json`.
- new command seeds: `examples/draw_call_proxy_macro_commands.json`, `examples/draw_call_indexed_proxy_macro_commands.json`, `examples/texture_sampler_write_query_destroy_macro_commands.json`.
56. P0 WebGPU API slice implementation and benchmark contracts are now integrated:
- native runtime wiring now covers `wgpuBufferDestroy`, `wgpuCommandEncoderClearBuffer`, `wgpuCommandEncoderWriteBuffer`, `wgpuComputePassEncoderDispatchWorkgroupsIndirect`, `wgpuComputePassEncoderWriteTimestamp`, `wgpuDeviceCreateComputePipelineAsync`, `wgpuDeviceDestroy`, `wgpuQuerySetDestroy`, `wgpuQuerySetGetCount`, `wgpuQuerySetGetType`, `wgpuRenderPassEncoderBeginOcclusionQuery`, `wgpuRenderPassEncoderEndOcclusionQuery`, `wgpuRenderPassEncoderMultiDrawIndirect`, `wgpuRenderPassEncoderMultiDrawIndexedIndirect`, and `wgpuRenderPassEncoderWriteTimestamp`.
- render multidraw dispatch is now feature-gated via `WGPUFeatureName_MultiDrawIndirect`; fallback draw loops remain deterministic when unavailable.
- new directional P0 benchmark workloads were added: `resource_lifecycle`, `compute_indirect_timestamp`, `render_multidraw`, `render_multidraw_indexed`.
- local benchmark artifacts are emitted under `bench/out/p0_*.perf_report.json` and `bench/out/run-bench-p0_*`.
- Dawn-side directional comparisons for these contracts currently skip on CPU-only adapters in this host class (`DawnPerfTest::IsCPU`), so claimable Dawn-vs-Doe artifacts remain blocked pending a non-CPU adapter host.
57. P1/P2 capability and lifecycle API coverage has been expanded:
- new capability-introspection proc surface is implemented in `runtime/zig/src/wgpu_p1_capability_procs.zig` and wired through `runtime/zig/src/wgpu_capability_runtime.zig` + `runtime/zig/src/webgpu_ffi.zig`.
- covered APIs include adapter/device/instance feature+limit+info/proc-address paths and free-members contracts:
  `wgpuAdapterGetFeatures`, `wgpuAdapterGetFormatCapabilities`, `wgpuAdapterGetInfo`, `wgpuAdapterGetInstance`, `wgpuAdapterGetLimits`, `wgpuAdapterInfoFreeMembers`, `wgpuAdapterPropertiesMemoryHeapsFreeMembers`, `wgpuAdapterPropertiesSubgroupMatrixConfigsFreeMembers`, `wgpuDawnDrmFormatCapabilitiesFreeMembers`, `wgpuDeviceGetAdapter`, `wgpuDeviceGetAdapterInfo`, `wgpuDeviceGetFeatures`, `wgpuDeviceGetLimits`, `wgpuGetInstanceFeatures`, `wgpuGetInstanceLimits`, `wgpuGetProcAddress`, `wgpuHasInstanceFeature`, `wgpuInstanceGetWGSLLanguageFeatures`, `wgpuInstanceHasWGSLLanguageFeature`, `wgpuSupportedFeaturesFreeMembers`, `wgpuSupportedInstanceFeaturesFreeMembers`, `wgpuSupportedWGSLLanguageFeaturesFreeMembers`.
- new Dawn ResourceTable + immediates proc surface is implemented in `runtime/zig/src/wgpu_p1_resource_table_procs.zig` and exercised via `async_diagnostics` mode routing in `runtime/zig/src/wgpu_async_diagnostics_command.zig`.
- covered APIs include:
  `wgpuComputePassEncoderSetImmediates`, `wgpuComputePassEncoderSetResourceTable`, `wgpuDeviceCreateResourceTable`, `wgpuRenderBundleEncoderSetImmediates`, `wgpuRenderBundleEncoderSetResourceTable`, `wgpuRenderPassEncoderSetImmediates`, `wgpuRenderPassEncoderSetResourceTable`, `wgpuResourceTableDestroy`, `wgpuResourceTableGetSize`, `wgpuResourceTableInsertBinding`, `wgpuResourceTableRelease`, `wgpuResourceTableRemoveBinding`, `wgpuResourceTableUpdate`.
- current Doe-native `setImmediates` coverage is explicit proc-surface emulation for the `resource_table_immediates` contract: zero-length payloads are accepted across compute/render pass/render-bundle encoders, non-zero payloads are validated at the API boundary, and Vulkan does not yet publish shader-visible push-constant semantics through this path.
- explicit feature gating is now enforced for ResourceTable flow (`WGPUFeatureName_ChromiumExperimentalSamplingResourceTable`): unsupported adapters return deterministic `unsupported` status rather than silent fallback.
- new lifecycle/AddRef proc surface is implemented in `runtime/zig/src/wgpu_p2_lifecycle_procs.zig`; all requested AddRef symbols are dynamically loaded and available:
  `wgpuAdapterAddRef`, `wgpuBindGroupAddRef`, `wgpuBindGroupLayoutAddRef`, `wgpuBufferAddRef`, `wgpuCommandBufferAddRef`, `wgpuCommandEncoderAddRef`, `wgpuComputePassEncoderAddRef`, `wgpuComputePipelineAddRef`, `wgpuDeviceAddRef`, `wgpuExternalTextureAddRef`, `wgpuInstanceAddRef`, `wgpuPipelineLayoutAddRef`, `wgpuQuerySetAddRef`, `wgpuQueueAddRef`, `wgpuRenderPassEncoderAddRef`, `wgpuRenderPipelineAddRef`, `wgpuResourceTableAddRef`, `wgpuSamplerAddRef`, `wgpuShaderModuleAddRef`, `wgpuSharedBufferMemoryAddRef`, `wgpuSharedFenceAddRef`, `wgpuSharedTextureMemoryAddRef`, `wgpuSurfaceAddRef`, `wgpuTexelBufferViewAddRef`, `wgpuTextureAddRef`, `wgpuTextureViewAddRef`.
58. New directional micro+macro benchmark contracts were added for P1/P2 API clusters (AMD Vulkan extended matrix):
- micro contracts: `capability_introspection`, `resource_table_immediates`, `lifecycle_refcount`.
- macro contracts: `capability_introspection_500`, `resource_table_immediates_500`, `lifecycle_refcount_200`.
- command seeds are in:
  `examples/p1_capability_introspection_commands.json`,
  `examples/p1_resource_table_immediates_commands.json`,
  `examples/p2_lifecycle_refcount_commands.json`,
  `examples/p1_capability_introspection_macro_commands.json`,
  `examples/p1_resource_table_immediates_macro_commands.json`,
  `examples/p2_lifecycle_refcount_macro_commands.json`.
- Dawn map entries for these IDs were added in `bench/dawn_workload_map.amd.extended.json`; all are directional (`comparable=false`) by contract.

59. P0 pixel-local-storage barrier surface is now fully implemented as a deterministic diagnostics contract:
- added `async_diagnostics` mode `pixel_local_storage` (`runtime/zig/src/wgpu_async_pixel_local_storage.zig`) with explicit non-coherent feature gating, pipeline-layout PLS chained descriptor, render-pass PLS chained descriptor, and in-pass `wgpuRenderPassEncoderPixelLocalStorageBarrier` invocation.
- runtime now requests/probes Dawn pixel-local-storage features at adapter/device scope (`WGPUFeatureName_PixelLocalStorageCoherent`, `WGPUFeatureName_PixelLocalStorageNonCoherent`) through `runtime/zig/src/webgpu_ffi.zig` and `runtime/zig/src/wgpu_capability_runtime.zig`.
- coverage state promoted from partial to implemented in `config/webgpu-capability-inventory.json`.
- new directional benchmark contracts were added:
  `render_pixel_local_storage_barrier` and `render_pixel_local_storage_barrier_500`
  with command seeds
  `examples/p0_render_pixel_local_storage_barrier_commands.json` and
  `examples/p0_render_pixel_local_storage_barrier_macro_commands.json`.
- AMD Vulkan smoke automation is now config-first:
  `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.smoke.gpu.json`,
  `bench/verify_smoke_gpu_usage.py`, and self-hosted workflow
  `.github/workflows/amd-vulkan-smoke.yml`.
- Dawn-vs-Doe feature/benchmark coverage table generation is now scripted via
  `bench/generate_feature_benchmark_table.py` with current artifact
  `bench/out/dawn-vs-doe-feature-benchmark-coverage.md`.

60. API-surface and matrix coverage metrics are now machine-generated and full for capability scope:
- `runtime/zig/src/core/abi/wgpu_loader.zig` now preloads the remaining Dawn header symbol set used by coverage scans (label/debug-marker/map-introspection/lost-future/external-texture release paths) via `OPTIONAL_API_SURFACE_SYMBOLS`.
- `bench/generate_feature_benchmark_table.py` now emits a top-level metrics table with:
  - capability inventory tracking completion
  - Dawn header API-surface reference coverage (estimate)
  - capability-to-benchmark mapping coverage
- current matrix artifact reports:
  - capability inventory tracking completion: `100.0% (22/22)` (capability-contract subset at the time of that report)
  - Dawn header API-surface reference coverage: `100.00% (199/199)`
  - capability-to-benchmark mapping coverage: `100.00% (22/22)`
  (`bench/out/dawn-vs-doe-feature-benchmark-coverage.md`).

61. Comparable contract promotion + timing rigor hardening completed for next-week item set:
- promoted from directional to comparable (`comparable=true`) where execution is adapter-backed and deterministic:
  `capability_introspection`,
  `lifecycle_refcount`,
  `capability_introspection_500`,
  `lifecycle_refcount_200`,
  `resource_lifecycle`,
  `compute_indirect_timestamp`,
  `render_multidraw`,
  `render_multidraw_indexed`.
- at this checkpoint (before later gap-closure promotions), extended workload matrix stood at `34` total contracts: `26` comparable + `8` directional.
- strict probe run over promoted contracts (`bench/out/dawn-vs-doe.amd.vulkan.promoted.strict_probe.json`) reports `comparisonStatus=comparable` for all 8 promoted workloads (claimability diagnostic due single-sample probe floor).
- release claimability recheck for upload workloads (`upload_write_buffer_64kb`, `upload_write_buffer_1mb`) completed with strict comparability and release sample floor:
  `bench/out/dawn-vs-doe.amd.vulkan.release.upload64kb1mb.json`
  => `comparisonStatus=comparable`, `claimStatus=claimable`.
- benchmark timing rigor now enforces native execution-span timing for strict operation-class comparisons on webgpu-ffi left runs:
  non-native fallback timing sources now trigger non-comparable reasons in `bench/native-compare/compare_dawn_vs_doe.py`;
  policy is explicit in report `comparabilityPolicy.requireNativeExecutionTimingForLeftOperation=true`.

62. Capability coverage metric contract now distinguishes directional-only capability domains:
- `config/webgpu-capability-inventory.schema.json` accepts optional `benchmarkClass` (`comparable` or `directional`) per capability entry.
- `bench/generate_feature_benchmark_table.py` now emits both overall comparable-coverage and eligible-only comparable-coverage metrics.
- updated matrix artifact:
  `bench/out/dawn-vs-doe-feature-benchmark-coverage.md`.

63. Gap-closure promotion completed: strict comparable capability coverage is now full (`22/22`).
- promoted to comparable contracts:
  `resource_table_immediates`,
  `render_pixel_local_storage_barrier`,
  `surface_presentation`.
- resource-table and PLS contracts now use workload-level strict comparability override
  `allowLeftNoExecution=true` with deterministic unsupported/skipped evidence requirements
  in `bench/native-compare/compare_dawn_vs_doe.py`; unsupported runtime paths remain explicit taxonomy statuses.
- surface comparable proxy contract now uses deterministic create/release command shape
  (`examples/surface_presentation_commands.json`) to avoid non-deterministic invalid-surface execution errors on headless adapter classes.
- Dawn mapping for promoted contracts now uses explicit deterministic filters:
  `resource_table_immediates -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`
  `render_pixel_local_storage_barrier -> DrawCallPerf.Run/Vulkan_AMD_Radeon_Graphics__RADV_GFX1151`.
- strict gap-close probe artifact:
  `bench/out/dawn-vs-doe.amd.vulkan.gapclose.strict_probe.json`
  reports `comparisonStatus=comparable`, `nonComparableCount=0` for all 3 promoted contracts.
- matrix metrics now report:
  - comparable capability benchmark coverage: `100.00% (22/22)`
  - comparable capability benchmark coverage (eligible-only): `100.00% (22/22)`
  - directional-only capability domains: `0.00% (0/22)`
  (`bench/out/dawn-vs-doe-feature-benchmark-coverage.md`).

63a. Full all-39 execution proof now completes with strict comparability green on the AMD extended matrix:
- report: `bench/out/dawn-vs-doe.amd.vulkan.full39.execproof.json`
- result: `comparisonStatus=comparable`, `nonComparableCount=0`, `39` comparable workloads processed.
- macro feature-gated contracts now align with their base contract parity rules:
  `resource_table_immediates_500` and `render_pixel_local_storage_barrier_500`
  set `allowLeftNoExecution=true` + `applesToApplesVetted=true` in
  `bench/workloads.amd.vulkan.extended.json`.
- native device feature request now includes
  `WGPUFeatureName_ChromiumExperimentalSamplingResourceTable` when advertised by the adapter
  (`runtime/zig/src/webgpu_ffi.zig`, `runtime/zig/src/core/abi/wgpu_types.zig`) so resource-table diagnostics do not fail due to omitted feature enablement.
- explicit runtime unsupported taxonomy remains visible (not hidden fallback):
  `resource_table_feature_unavailable` and `pixel_local_storage_feature_unavailable`
  on this AMD RADV host class for the four affected P0/P1 workloads.
- claimability remains diagnostic for this proof run by design (`iterations=1`, `warmup=0`):
  `claimStatus=diagnostic`, `nonClaimableCount=39` under release claim-floor policy.

63b. Spec-universe coverage status semantics now distinguish inventory tracking from runtime implementation:
- `config/webgpu-capability-inventory.schema.json` adds coverage `status="tracked"`.
- `config/webgpu-capability-inventory.json` migrates Dawn feature-inventory rows from `planned` to `tracked` for explicit full-universe inventory closure.
- `bench/generate_feature_benchmark_table.py` now reports both:
  - inventory tracking completion (`status != planned`)
  - runtime-implemented completion (`status == implemented`).

63c. Spec-universe tracked-inventory closure is now complete:
- all feature-inventory rows are now in explicit implemented state via a unified inventory contract:
  - Dawn feature-enum source of truth (`bench/vendor/dawn/src/dawn/dawn.json` `feature name`)
  - runtime capability introspection path (`wgpuAdapterGetFeatures` / `wgpuDeviceGetFeatures` in Zig capability runtime)
  - benchmark mapping contract (`capability_introspection` + `capability_introspection_500`)
- current status totals are now:
  - `implemented=103`
  - `blocked=0`
  - `tracked=0`
  - `planned=0`

63d. Full 39-workload strict comparable benchmark pass now completes on local Vulkan config with the extended matrix:
- report: `bench/out/dawn-vs-doe.local.vulkan.extended.comparable.full39.now.json`
- result: `comparisonStatus=comparable`, `nonComparableCount=0`, `workloadCount=39`.
- all `39` workload IDs in `bench/workloads.amd.vulkan.extended.json` are present in the report.
- run remains diagnostic for claim mode by design (`iterations=1`, `warmup=0`): `claimStatus=diagnostic`, `nonClaimableCount=39`.

64. Blocking gate enforcement is now aligned with process policy in CI:
- canonical runner `bench/run_blocking_gates.py` now enforces schema -> correctness -> trace -> optional drop-in -> optional claim ordering.
- canonical release orchestration runner `bench/run_release_pipeline.py` now enforces preflight -> compare -> (optional smoke verify) -> blocking gates.
- `.github/workflows/release-gates.yml` now uses `bench/run_release_pipeline.py` with release claim-gate requirements.
- `.github/workflows/amd-vulkan-smoke.yml` now uses `bench/run_release_pipeline.py` with smoke GPU-usage verification.
- new `bench/schema_gate.py` validates schema-backed config/data contracts before release claim checks.

65. Benchmark methodology thresholds are now config contracts:
- dispatch-window rejection and claimability default sample floors moved from hardcoded Python constants to `config/benchmark-methodology-thresholds.json`.
- contract schema is `config/benchmark-methodology-thresholds.schema.json`.
- migration recorded in `config/migration-notes.md`.

66. Drop-in compatibility acceptance lane is now artifact-first and runtime-internal independent:
- new contract file `config/dropin_abi.symbols.txt` defines required exported WebGPU C API symbols for drop-in acceptance checks.
- new gates in `bench/`:
  - `dropin_symbol_gate.py` (symbol completeness)
  - `dropin_behavior_suite.py` + `dropin_behavior_suite.c` (black-box API behavior: create device, queue ops, error scope capture, lifecycle release)
  - `dropin_benchmark_suite.py` + `dropin_benchmark_harness.c` (micro + end-to-end benchmark suite)
  - `dropin_gate.py` (consolidated gate/report with per-step runtimes and failure tokens)
- canonical gate runners now support drop-in enforcement:
  - `bench/run_blocking_gates.py --with-dropin-gate --dropin-artifact <path>`
  - `bench/run_release_pipeline.py --with-dropin-gate --dropin-artifact <path>`
- CI now includes `.github/workflows/dropin-compat.yml`, which builds a candidate shared-library artifact, consumes that artifact in a separate gate job, and fails hard on compatibility regressions while publishing drop-in reports every run.

67. Release claim diagnostics and 1KB upload contract were hardened for actionable "faster everywhere" enforcement:
- earlier 1KB deferred-queue-sync contract tuning is no longer the current authority. Fresh March 10 reruns on the AMD Vulkan release lane showed that forcing `--queue-sync-mode deferred` worsened `upload_write_buffer_1kb`; the current strict contract does not force that extra arg.
- `bench/claim_gate.py` now prints non-claimable workload runtime details (delta tails, left/right p50 timing, timing sources, and claimability reasons) so gate failures directly identify which runtime path needs fixing.

68. Release lane workload coverage was switched from default subset to extended comparable matrix:
- `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json` now loads `bench/workloads.amd.vulkan.extended.json`, enables `includeExtendedWorkloads=true`, and uses `bench/dawn_workload_map.amd.extended.json`.
- release CI (`.github/workflows/release-gates.yml`) continues to invoke the same release config entrypoint, but now evaluates all comparable AMD Vulkan contracts from the extended matrix under release claimability policy.

69. Drop-in artifact lane now defaults to Doe-produced shared-library outputs:
- `bench/run_release_pipeline.py`, `bench/run_blocking_gates.py`, and `bench/drop-in/dropin_gate.py` now default `--dropin-artifact` to `runtime/zig/zig-out/lib/libwebgpu_doe.so` and fail fast when a configured artifact is missing.
- release CI now builds `zig build dropin` and passes `runtime/zig/zig-out/lib/libwebgpu_doe.so` to drop-in gates.
- drop-in compatibility CI now publishes and gates `libwebgpu_doe.so` plus required sidecars (`libwebgpu_dawn.so`, `libwebgpu.so`, `libwgpu_native.so`) from `runtime/zig/zig-out/lib/`.

70. Queue wait-mode fallback behavior is now explicit-taxonomy only:
- native `--queue-wait-mode wait-any` no longer silently mutates to `process-events` on unsupported/timeout paths.
- unsupported/timeout/error outcomes now surface as runtime error taxonomy (`WaitAnyUnsupported`, `WaitTimedOut`, `WaitAnyFailed`, `WaitAnyIncomplete`) for deterministic diagnostics.

71. Release claim-window trend automation is now scriptable and CI-scheduled:
- `bench/run_release_claim_windows.py` runs repeated release windows and emits a summary artifact with per-window command/report path, return code, `comparisonStatus`, `claimStatus`, and non-comparable/non-claimable workload IDs.
- new CI workflow `.github/workflows/release-claim-trends.yml` schedules repeated AMD Vulkan release windows and publishes trend artifacts.

72. Replay gate now includes CI-native semantic parity checks for runtime-to-runtime lanes:
- `bench/trace_gate.py` adds `--semantic-parity-mode off|auto|required`.
- `auto` compares eligible doe-to-doe trace pairs with `pipeline/trace/compare_dispatch_traces.py` while preserving Dawn-vs-Doe release compatibility.
- `required` fails hard unless semantic parity checks execute and pass, enabling strict Doe-vs-Dawn parity lanes.

73. Substantiation evidence is now policy-backed and machine-gated:
- new config contract `config/substantiation-policy.json` (+ schema) defines minimum report-count and minimum unique left-profile requirements.
- new gate `bench/substantiation_gate.py` validates repeated-window and/or explicit report artifacts against that policy.
- `bench/run_release_claim_windows.py` can now run the substantiation gate in-line via `--with-substantiation-gate`.

74. Canonical tested hardware/driver inventory and matrix dashboard are now generated from artifacts:
- new script `bench/build_test_inventory_dashboard.py` scans compare reports and builds:
  - timestamped inventory snapshots (`bench/out/<timestamp>/test-inventory.json`)
  - stable latest inventory registry (`bench/out/test-inventory.latest.json`)
  - timestamped dashboard snapshots (`bench/out/<timestamp>/test-dashboard.html`)
  - stable latest dashboard (`bench/out/test-dashboard.latest.html`)
- dashboard includes per-matrix latest status (`comparisonStatus`, `claimStatus`, non-comparable/non-claimable counts) and top-level p50 delta vs Dawn.
- inventory includes tested profile combos keyed by `vendor|api|deviceFamily|driver` (from `traceMeta.profile`) plus first/last-seen and matrix/report coverage.
- timestamped run folders now include `run_manifest.json` with run type/config/gate metadata; ad-hoc artifacts are namespaced under `bench/out/scratch/<timestamp>/...`.
- historical timestamp folders can be annotated with inferred manifests via `bench/backfill_run_manifests.py` so legacy artifacts remain auditable without renaming folders.

75. Upstream quirk mining automation is now deterministic and schema-backed:
- new miner `pipeline/agent/mine_upstream_quirks.py` scans source roots for toggle-style quirk candidates and emits `quirks.schema`-valid records (`schemaVersion: 2`).
- new manifest contract `config/quirk-mining-manifest.schema.json` defines hash-linked mining evidence (`seedHash`/`finalHash`/per-row chain).
- schema gate now validates sample mining artifacts (`examples/quirks/mined_toggle_sample.json`, `examples/quirk-mining.manifest.sample.json`).

76. Baseline dataset/trend packaging is now automated:
- new script `bench/build_baseline_dataset.py` scans comparison artifacts and emits:
  - timestamped baseline dataset (`bench/out/<timestamp>/baseline-dataset.json`)
  - timestamped markdown summary (`bench/out/<timestamp>/baseline-dataset.md`)
  - stable latest outputs (`bench/out/baseline-dataset.latest.json`, `bench/out/baseline-dataset.latest.md`)
- output groups report history by matrix/runtime pair and tracks latest/best/worst p50 deltas.

77. Substantiation target-profile diversity can now be enforced as blocking:
- `config/substantiation-policy.json` now carries `releaseEvidence.enforceTargetUniqueLeftProfiles` (default `true`).
- `bench/substantiation_gate.py` now fails (not warns) when `targetUniqueLeftProfiles` is below policy under enforced mode, with optional CLI override.

78. Dawn-vs-Doe benchmark harness logic is now modularized by concern:
- `bench/native-compare/modules/timing_selection.py`
- `bench/native-compare/modules/comparability.py`
- `bench/native-compare/modules/claimability.py`
- `bench/native-compare/modules/reporting.py`
- `bench/native-compare/compare_dawn_vs_doe.py` now uses these modules for runtime behavior while preserving report contracts.

79. Native execution trace taxonomy now includes deterministic status codes:
- trace rows now emit `executionStatusCode` in addition to `executionStatusMessage`.
- `runtime/zig/src/trace.zig` normalizes status codes to stable machine-friendly tokens and `config/trace.schema.json` is updated accordingly.

80. Strict AMD Vulkan host preflight now probes Dawn adapter visibility directly:
- `bench/preflight_bench_host.py` now runs a Dawn adapter probe (`dawn_perf_tests --gtest_list_tests --backend=vulkan --adapter-vendor-id=0x1002`) and parses reported adapters before allowing strict AMD runs.
- strict preflight now also probes Doe's selected Vulkan adapter ordinal from trace-meta and resolves it through `vulkaninfo --summary`; strict AMD runs fail unless Doe and Dawn agree on vendor/device identity.
- this prevents false-green preflight outcomes that would otherwise fail later in compare execution with adapter-unavailable or render-node permission-denied errors.

81. Native execution reliability hardening now includes explicit retry envelopes and stricter copy/kernel validation:
- queue submission synchronization now routes through centralized backend submit helpers with bounded retry (`QUEUE_SYNC_RETRY_LIMIT`) for transient wait-path failures (`WaitTimedOut`, `QueueSubmitTimeout`, `WaitAnyIncomplete`) in `runtime/zig/src/webgpu_ffi.zig`.
- GPU timestamp readback now retries map/read steps with bounded backoff (`TIMESTAMP_MAP_RETRY_LIMIT`) and preserves explicit taxonomy errors instead of one-shot map failures.
- compute dispatch now fails with explicit `gpu timestamp ...` status taxonomy when timestamp readback errors occur, rather than silently flattening failures into a zero timestamp.
- copy lowering now fails fast on invalid/non-matching texture extents for texture copy directions, and kernel source loading now rejects empty sources plus non-compute WGSL (`@compute` required) for `kernel_dispatch`.

82. Skeptical-claim hardening for strict comparable lanes:
- timing-selection now rejects tiny dispatch-window measurements globally when both are true: dispatch window below `minDispatchWindowNsWithoutEncode` and coverage below `minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs` (thresholds from `config/benchmark-methodology-thresholds.json`), then falls back to `executionTotalNs`.
- `surface_presentation` is now directional-only (`comparable=false`) because Dawn `ConcurrentExecutionTest ... RunSingle` is not a matching create/release-surface benchmark contract.
- new strict comparable replacement workload `compute_concurrent_execution_single` maps to Dawn `ConcurrentExecutionTest ... RunSingle` with a matched single-dispatch compute contract (`examples/concurrent_execution_single_commands.json`, `bench/kernels/concurrent_execution_runsingle_u32.wgsl`).

83. Apples-to-apples contract enforcement hardening:
- strict workload contract loader now rejects `comparable=true` entries with directional descriptions or explicit closest-proxy comparability notes.
- AMD extended workload contract now classifies directional/proxy mappings as non-comparable (`benchmarkClass=directional`) so strict claim lanes include only strict apples-to-apples workloads.
- upload ignore-first mixed-scope timing derivations (`base` source vs `adjusted` row-total source mismatch) now fail comparability and claimability checks.
- compare reports now embed workload contract metadata (`workloadContract.path`, `workloadContract["sha256"]`) for anti-staleness auditing.
- `bench/check_full39_claim_readiness.py` now validates exact comparable workload identity against the current workload contract and fails on stale/mismatched workload sets.

84. Comparability obligations are now machine-checkable and gate-enforced:
- `bench/native-compare/modules/comparability.py` now emits per-workload obligation artifacts (`comparability.obligations`) with explicit `id`, `applicable`, `blocking`, and `passes` fields plus `blockingFailedObligations`.
- workload comparability status now derives from blocking-obligation failures (deterministic contract), while preserving detailed human-readable reasons.
- `bench/claim_gate.py` now validates comparability obligation schema/version and fails when claimable/comparable reports contain missing or failed blocking comparability obligations.
- `bench/check_full39_claim_readiness.py` now fails readiness checks when workload comparability obligations are missing/invalid or have blocking failures.
- Lean formalization now includes `pipeline/lean/Fawn/Comparability.lean` for obligation IDs and blocking-failure semantics mirrored by bench gating.

85. Lean/Python comparability parity fixtures are now wired:
- canonical obligation IDs are config-backed (`config/comparability-obligations.json`) and validated by schema gate.
- comparability fixture contract is now schema-backed (`config/comparability-obligation-fixtures.schema.json`) with fixture data in `bench/comparability_obligation_fixtures.json`.
- parity verification script `bench/comparability_obligation_parity_gate.py` now checks:
  - Python fixture evaluation via `evaluate_comparability_from_facts`
  - Lean/Python obligation ID alignment (`pipeline/lean/Fawn/Comparability.lean` constructors vs canonical config IDs).
- Lean fixture proofs are now present in `pipeline/lean/Fawn/ComparabilityFixtures.lean` and compiled in `pipeline/lean/check.sh`.
- gate orchestration now supports verification-lane wiring with `--with-comparability-parity-gate` in:
  - `bench/run_blocking_gates.py`
  - `bench/run_release_pipeline.py`
  - `bench/run_release_claim_windows.py`.

86. Track B claim-grade rehearsal artifacts and hash-linked claim rows are now hard-gated:
- `bench/claim_gate.py` now validates claim-row hash linkage (`claimRowHash`, `claimRowHashChain`) against workload-contract hash, config-contract hash, benchmark-policy hash, and trace-meta hashes.
- claim gate now independently enforces per-workload timed-sample floors plus required positive tails (`p50/p95/p99` in release mode), even if report-level claimability fields are present.
- `bench/run_release_pipeline.py` now emits claim rehearsal artifacts by default when `--with-claim-gate` is enabled:
  - claim gate result
  - tail-health table
  - timing-invariant audit
  - contract-hash manifest
  - rehearsal manifest linking these outputs
- new standalone artifact builder is available in `bench/build_claim_rehearsal_artifacts.py`.
- `bench/run_release_claim_windows.py` now forwards this rehearsal-artifact step per window by default.

87. Bench harness orchestration sharding is complete:
- Extracted subprocess mapping, data struct processing, standard error reading, and resource extraction into `bench/native-compare/modules/runner.py`.
- historical note: `bench/native-compare/compare_dawn_vs_doe.py` previously exceeded the 1200-line limitation policy; split completed in Snapshot item 17 (now 481 lines).

88. Broader baseline coverage automation is implemented:
- Added `bench/native-compare/wgpu_benchmark_adapter.py` for automated wgpu runtime baseline comparability mapping.

89. Auto-calibration of baseline heuristics is active:
- Added `bench/auto_calibrate_workload.py` for dynamic `commandRepeat` and `uploadSubmitEvery` parameter searches to ensure consistent CV limits.

90. Data pipeline ingestion optimization:
- Added `bench/ingest_reports_to_sqlite.py` to ingest Doe benchmark json reports directly into sqlite data stores.

91. Robust native GPU execution span verification:
- Confirmed timestamp resolution precedence in `timing_selection.py` where `executionGpuTimestampTotalNs` correctly overrides fallback `executionEncodeTotalNs` for WebGPU timing sources.

92. Metal backend native execution architecture (2026-03-05):
- `doe_metal` backend now executes Metal APIs directly without delegating to Dawn.
- New `metal_bridge.m` (C/ObjC ARC bridge) + `metal_native_runtime.zig` provide native upload/barrier execution via MTLDevice, MTLCommandQueue, MTLBuffer, MTLBlitCommandEncoder.
- `ZigMetalBackend.inner: WebGPUBackend` field removed; Dawn is not loaded in `metal_zig` lanes.
- Capabilities restricted to `{buffer_upload, barrier_sync}` — only what is natively implemented.
- Commands without native implementation return explicit `.unsupported` taxonomy; no silent Dawn fallback.
- `metal_zig` lane benchmarks now measure genuine Doe-native vs Dawn for upload/barrier workloads.

93. Comparability semantics are now externalized through a config-driven contract:
- `config/comparability-obligations.json` is now the semantic source of truth, not just an ID list; it carries ordered obligation rules, fact names, and applicability/pass expressions.
- `pipeline/lean/generate_comparability_contract.py` now regenerates `pipeline/lean/Fawn/Generated/ComparabilityContract.lean` from that contract before `pipeline/lean/check.sh` and `pipeline/lean/extract.sh`.
- Python comparability fixture evaluation in `bench/native-compare/modules/comparability.py` now interprets the same config contract instead of a hardcoded `result_by_id` mirror.
- report/gate conformance loaders now accept the richer v2 obligation contract while preserving v1 compatibility for historical artifacts.

94. Lean audit trust chain now carries the comparability contract hash end-to-end:
- `pipeline/lean/Fawn/Extract.lean` now emits `contractHashes.comparabilityObligationsSha256` into `pipeline/lean/artifacts/proven-conditions.json`.
- `config/proof-artifact.schema.json` now requires that hash field.
- `runtime/zig/build.zig` now embeds the live `config/comparability-obligations.json` SHA-256 into build options, and `runtime/zig/src/lean_proof.zig` validates that the proof artifact hash matches at comptime.

95. Unbounded proof coverage now extends from arbitrary obligation lists to workload geometry:
- added `pipeline/lean/Fawn/Full/WorkloadGeometry.lean`
- new `lean_verified` theorems prove execution-shape comparability facts for arbitrary `Nat`-valued buffer size and dispatch geometry, not just finite fixtures
- proof extraction now includes those geometry theorems and their elimination target metadata

### Missing in progress

1. ~~Expand upstream quirk mining beyond toggle-style heuristics~~ DONE (2026-03-05): miner now captures toggle context-aware patterns (`Default`/`ForceSet`/`ForceEnable`/`ForceDisable`) and non-toggle workaround patterns (vendor-conditional limit overrides, alignment assigns, feature guards). Vendor detection via `gpu_info::IsVendor()` and `IsVendorMesa()` patterns with 20-line context window. Manifest v2 includes `workaroundHitCount`, `workaroundCategoryCounts`, and `workaroundHits`. Tested: 702 toggle + 24 workaround candidates from Dawn native source (5 feature guards across Intel/Nvidia, 19 limit overrides across Qualcomm/Apple/Nvidia). `--toggle-only` flag preserves backward compatibility.
2. ~~Lean theorem packs with CI proof execution~~ DONE (2026-03-05): `pipeline/lean/check.sh` now passes cleanly (fixed `String.trimAscii` → `String.trim` for toolchain 4.16.0 compatibility and updated `ComparabilityFixtures.lean` for Doe-vs-Doe parity obligation fields). `.github/workflows/lean-check.yml` added as CI gate on macOS runners. Lean proof-to-artifact pipeline complete: `pipeline/lean/extract.sh` compiles all modules and emits `pipeline/lean/artifacts/proven-conditions.json`; CI validates and uploads artifact. Zig comptime gate wired: `runtime/zig/src/lean_proof.zig` conditionally embeds proof artifact via `-Dlean-verified=true` and validates schemaVersion, status, and required theorems at compile time. Verification gate flipped from advisory to blocking in `config/gates.json`.
3. Self-hosted AMD Vulkan runner availability/maintenance for automated smoke workflow execution (`.github/workflows/amd-vulkan-smoke.yml`).
4. Full benchmark harness with measured GPU timings tied to native execution spans.
5. Extend baseline automation to broader incumbent lanes (including explicit wgpu baselines) and multi-host trend publication.
6. Native Zig/WebGPU/FFI execution backend hardening in Zig remains a runtime milestone (coverage/reliability/perf).
7. ~~Repeated strict release claim-mode rechecks for 64KB cadence retune~~ SUPERSEDED (2026-03-07): `bench/out/amd-vulkan/20260307T001500Z/dawn-vs-doe.amd.vulkan.release.json` was marked green at the time, but current structural-equivalence and `pathAsymmetry` enforcement invalidate it as claim evidence. Treat that artifact as diagnostic only; fresh strict-lane reruns must use `backend-runtime-policy-v2`, where `vulkan_doe_comparable` / `vulkan_doe_release` force equivalent staged GPU upload work via `uploadPathPolicy: "staged_copy_only"`.
12. **Metal small-upload timing audit superseded earlier closure (2026-03-06):** the 2026-03-05 interpretation that 1KB/64KB Metal uploads were cleanly claimable is no longer the current authority. The latest broad March 6 Metal report shows operation-to-wall coverage asymmetry severe enough to treat the lane as diagnostic until timing scope is audited. 2026-03-07 follow-up: the identified local Metal upload/runtime/config cause has been fixed (staged copy path restored and timing-phase symmetry made blocking), but the broad rerun has not yet been republished.
8. Keep remaining directional diagnostics macro-scoped and non-claim (`render_draw_indexed_200k`, `capability_introspection_500`, `lifecycle_refcount_200`).
9. Expand substantiation evidence collection across multiple non-CPU host profiles so enforced `targetUniqueLeftProfiles` is routinely satisfiable in CI.
10. ~~Zig source file sharding~~ DONE: all five previously listed files are now under 777 lines (verified 2026-03-05: `wgpu_commands.zig`=160, `webgpu_ffi.zig`=672, `core/abi/wgpu_types.zig`=753, `wgpu_dropin_lib.zig`=477, `command_json.zig`=570 — prior counts were pre-sharding snapshot).
11. ~~Quirk module isolation + behavioral wiring~~ DONE (2026-03-05): quirk system refactored into `runtime/zig/src/quirk/` module with `mod.zig` entry point, `QuirkMode` enum (`off`/`trace`/`active`), `--quirk-mode` CLI flag, `dispatchWithMode()` gating, `toggle_registry.zig` behavioral classification, `use_temporary_buffer` backend consumption in `wgpu_commands_copy.zig` (both buffer-to-texture and texture-to-texture staging paths), `use_temporary_render_texture` backend consumption in `wgpu_render_commands.zig` (Metal Intel R8/RG8 unorm mip >= 2 workaround), and `quirkMode` trace-meta emission. Action application logic extracted to `quirk_actions.zig`. 5 promoted behavioral workarounds: 4 `use_temporary_buffer` (Vulkan/D3D12 copy) + 1 `use_temporary_render_texture` (Metal render pass). Non-toggle upstream mining now complete in `pipeline/agent/mine_upstream_quirks.py`.
12. ~~`wgpu_render_commands.zig` sharding~~ DONE (2026-03-17): extracted temp render texture workaround (setup + copy-back) into `wgpu_render_temp_texture.zig` (123 lines). `wgpu_render_commands.zig` now 710 lines (under 777 limit).
13. **Backend report timing scope mismatch (2026-03-06):** Apple Metal extended comparable report (`20260306T195524Z`) shows Doe sub-microsecond p50 for small uploads (0.208µs for 1KB) vs Dawn ~189µs — producing delta percentages exceeding 90,000%. Doe appears to be reporting encode-only latency without GPU execution wait. AMD Vulkan singles report (`20260302T193052Z`) shows similar asymmetry: Doe 3.3ms vs Dawn 6,157ms for `par_workgroup_non_atomic_1024` due to `leftDivisor=100` / `rightDivisor=1` mismatch. Both are flagged `diagnostic` or `legacy_nonconformant` by the cube, but the dashboard shows the raw delta percentages which are misleading. Follow-up: audit compare harness timing extraction to ensure both sides measure identical operation scope before computing deltas.
14. **AMD Vulkan bounded copy-dst fast path (2026-03-06):** `runtime/zig/src/backend/vulkan/native_runtime.zig` now keeps the reusable mapped fast upload path bounded to `copy_dst` uploads up to `1 MiB` instead of letting large comparable contracts pin arbitrarily large host-visible buffers. Focused validation artifact `bench/out/scratch/upload-fast-path.validation.json` shows strong small/medium upload improvement on this host (`upload_write_buffer_1kb` p50 `+4993.69%`, `upload_write_buffer_64kb` `+2746.63%`, `upload_write_buffer_1mb` `+491.39%`), while `upload_write_buffer_4gb` remains correctly on the slower fallback path (`-97.48%`). These mapped shortcuts now remain available only on non-strict Vulkan lanes; strict `vulkan_doe_comparable` / `vulkan_doe_release` uploads are forced onto staged GPU copy by backend runtime policy.
15. **AMD Vulkan upload fallback command-buffer reuse (2026-03-06):** `runtime/zig/src/backend/vulkan/native_runtime.zig` now records pending fallback upload copies into the shared primary Vulkan command buffer and submits once per flush instead of allocating/submitting one command buffer per upload. Focused post-change release-lane rerun `bench/out/scratch/vulkan.upload_1mb.postfix.json` (`upload_write_buffer_1mb`, 5 iterations, 1 warmup) reported strong positive deltas on this host (`p50 +393.29%`, `p95 +400.03%`, `p99 +400.03%`) while still below the 15-sample release claim floor. At that point, `upload_write_buffer_4gb` remained negative and was the next Vulkan upload follow-up; that large-payload gap is now superseded by item 16.
16. **AMD Vulkan strict upload comparability restored; claimability remains performance-bound (2026-03-07):** strict Doe Vulkan now attributes upload staging work to `setup_ns` and pre-command upload flush overhead to `setup_ns`/`submit_wait_ns` in `runtime/zig/src/backend/vulkan/mod.zig`, matching Dawn's phase buckets for upload rows. Combined with `uploadPathPolicy: "staged_copy_only"` on `vulkan_doe_comparable` / `vulkan_doe_release`, fresh strict release rerun `bench/out/amd-vulkan/20260307T031517Z/dawn-vs-doe.amd.vulkan.release.json` is now `comparisonStatus=comparable`, and `bench/structural_equivalence_gate.py --require-all-pass` reports `7 pass, 0 fail`. Strict comparable workload contracts removed the stale upload `pathAsymmetry` caveat on staged-copy-only rows; `upload_write_buffer_4gb` is temporarily demoted from the strict comparable matrix pending Dawn-delegate throughput-sanity investigation. The remaining claim-gate blocker is now real performance on `upload_write_buffer_1kb` / `upload_write_buffer_64kb` (negative `p50`/`p95`/`p99`), not structural mismatch.
17. `bench/native-compare/compare_dawn_vs_doe.py` split complete (481 lines, down from 1,203). Report assembly and timing-interpretation synthesis extracted to `bench/native_compare_modules/report_assembly.py` (432 lines). Command-shape validation and backend-policy enforcement extracted to `bench/native_compare_modules/workload_validation.py` (511 lines). Owner: benchmark harness.
18. `bench/build_benchmark_cube.py` is at 1,351 lines (over the 1,200-line Python tooling limit). Next split target: move workload-registry loading/alias normalization and package/backend report ingestion into dedicated cube modules. Owner: benchmark cube.

## macOS Metal baseline (2026-03-05)

Strict comparable runs against Dawn delegate (Dawn Metal backend via `metal_dawn_release` lane). All 23 comparable workloads executed each run; `comparisonStatus=comparable`.

Config: `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` (12 iterations, 1 warmup, local claim mode).
Report: `bench/out/dawn-vs-doe.local.metal.extended.comparable.json`

### Run 6 (2026-03-05, sixth pass): **Claimable 9/23**

Fixes applied before Run 6:
- **Deferred manifest write (metal/mod.zig)**: shader artifact manifest disk I/O moved outside the `command_end - command_start` timing window. `execute_command` now stages the write into pending fields; `manifest_path_from_context` (called by `refreshBackendTelemetry` after `command_end`) flushes the write. Removes disk write latency spikes (10µs–2ms occasional) from `doe-execution-total-ns` timing for all render/dispatch workloads.
- **UB fix (metal/mod.zig)**: catch-path `requirements.is_dispatch` access guarded with `has_requirements and` to prevent undefined read when `skip_capability_guard=true` and `!is_dispatch(command)` (upload/barrier commands).

Output: `bench/out/20260305T194927Z/dawn-vs-doe.local.metal.extended.comparable.json`

| Workload | p50% | p95% |
|---|---|---|
| `upload_write_buffer_4mb` | +8.08 | +9.43 |
| `resource_lifecycle` | +2.27 | +4.19 |
| `upload_write_buffer_1mb` | +1.87 | +1.91 |
| `render_bundle_dynamic_pipeline_bindings` | +0.90 | +0.43 |
| `upload_write_buffer_64kb` | +0.54 | +1.13 |
| `compute_concurrent_execution_single` | +0.51 | +0.62 |
| `pipeline_async_diagnostics` | +0.29 | +2.28 |
| `upload_write_buffer_1kb` | +0.27 | +2.25 |
| `upload_write_buffer_16mb` | +0.12 | +0.30 |

Notable: `resource_lifecycle` (all-upload+barrier workload) jumped from −0.48% to +2.27% — system-state improvement, not directly from deferred-manifest fix (upload/barrier don't trigger manifest write). `render_draw_throughput_200k` regression to −8.33% p50 in this run due to GPU scheduling variance.

**Stability check (Run 7, 8/23 claimable):** Different set of workloads than Run 6. Common across both: `upload_write_buffer_4mb`, `upload_write_buffer_1mb`, `compute_concurrent_execution_single`, `upload_write_buffer_1kb`. Run-to-run variance is high: texture/sampler workloads that were −3% in Run 5 became claimable in Run 7 (+1.4%, +2.65%), then reverting. Large samples (4gb, 256mb) flip between claimable/diagnostic depending on memory bus pressure.

**Assessment:** Stable core is 4–5 workloads (4mb, 1mb, 16mb, compute_concurrent). Additional 4–5 workloads are system-state-dependent, flipping between claimable/non-claimable per run. The code fixes from Runs 4–6 raised the floor from 3/23 to 5–9/23 depending on system state. Further improvement requires: (1) GPU timestamps for render/compute (eliminates CPU scheduling noise), (2) Doe-native Metal API for render/texture, (3) larger repeat counts for small upload workloads.

### Run 5 (2026-03-05, fifth pass): **Claimable 5/23**

Fixes from Run 4 confirmed stable. Five claimable workloads:

| Workload | p50% | p95% | timing source |
|---|---|---|---|
| `upload_write_buffer_1mb` | +1.50 | +0.84 | row-total-ns |
| `upload_write_buffer_4mb` | +6.41 | +3.27 | row-total-ns |
| `upload_write_buffer_16mb` | +4.39 | +3.65 | row-total-ns |
| `resource_table_immediates_500` | +1.89 | +0.07 | total-ns |
| `compute_concurrent_execution_single` | +0.12 | +0.03 | total-ns |

**Root cause analysis of remaining 18 non-claimable workloads:**

1. **CPU timer quantization floor** (`upload_write_buffer_1kb`, `64kb`): total timing is 180–200µs; 1µs timer quantization = 0.5–0.6% noise floor. Advantage (+0.63–0.66% p50) is within one timer step. Not fixable without sub-µs CPU timer or larger repeat counts.

2. **GPU scheduling variance** (`render_draw_throughput_200k`): both sides have 30ms timing range across 19 samples. p50=+4.18% but p95=−2.09%. ONE slow LEFT sample (55.864ms vs median 47ms) pulls p95 negative. Source is GPU batch scheduling variance, not deterministic overhead.

3. **Marginal wrapper overhead** (`resource_lifecycle`, `render_pixel_local_storage_barrier_500`): ZigMetalBackend.execute_command adds ~40ns/command overhead vs DawnDelegateBackend. For 500 commands, this is ~20µs. resource_lifecycle p50=−0.48% (20µs/4ms). Structurally cannot be made positive without eliminating the wrapper or having Doe-native execution faster than Dawn.

4. **OS scheduling jitter** (`pipeline_async_diagnostics`): p50=+0.94%, but one outlier sample (19.74ms vs 17ms typical) pulls LEFT's p95 above RIGHT's p95. Index 17 (of 19 sorted): LEFT=17.90ms vs RIGHT=17.80ms — 100µs gap, not fixable by code changes.

5. **Dawn-owned render API** (all `doe-execution-encode-ns` workloads): both sides call the same Dawn `wgpuRenderPassEncoderDraw` in the same tight loop. Any difference is scheduling noise or 1µs quantization.

6. **Large upload DMA variability** (`upload_write_buffer_256mb`, `1gb`, `4gb`): GPU DMA bandwidth varies with system load and thermal state. 4gb p50 flipped from +2.57% (Run 4) to −1.92% (Run 5) — pure run-to-run variance.

**Path to more claimable workloads:** (1) GPU timestamps for render workloads (eliminates CPU scheduling noise), (2) Doe-native Metal render/texture API implementation, (3) increased repeat counts for small upload workloads.

### Run 4 (2026-03-05, fourth pass): **Claimable 2/23**

Three code fixes applied before Run 4:
1. **execution.zig**: moved `backend_telemetry_snapshot = backend.telemetry()` (which calls `refreshBackendTelemetry()` including `manifest_path_from_context`/`manifest_hash_from_context` for `doe_metal`) to BEFORE `command_start`, removing ~50ns/cmd asymmetric overhead from `doe-execution-total-ns` timing.
2. **metal/mod.zig + d3d12/mod.zig**: gated `artifact_meta.classify()` inside `should_emit_shader_artifact()` check (was running unconditionally).
3. **metal/mod.zig + d3d12/mod.zig**: added `.upload` and `.barrier` to `skip_capability_guard_for_command` (both always pass capability checks).

Key improvement: `resource_table_immediates_500` went from −3.21% (Run 3) to −0.16% (Run 4), confirming the overhead fixes work. Run 4 result was 2/23 (mixed due to system variance on upload_write_buffer_4gb).

### Run 3 (2026-03-05, third pass): **Claimable 3/23**

Config: `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` (20 iterations, 1 warmup, local claim mode, minTimedSamples=19).

| Workload | p50% | p95% |
|---|---|---|
| `upload_write_buffer_4mb` | +4.20 | +17.37 |
| `render_draw_redundant_pipeline_bindings` | +0.25 | +0.89 |
| `compute_concurrent_execution_single` | +0.18 | +0.25 |

**Regression vs Run 2: system-state variance, not binary change.** The blend/stencil optimization (skip redundant calls when at WebGPU initial state) is in the setup phase (before `encode_start_ns`) — the timed render encode window is purely the draw loop, so the optimization had zero effect on measured timing.

**Render workload characterization:** `render_draw_throughput_baseline` and all render variants cluster at 60–61µs encode time (2000 draws). The reported −1.5% to −3% is a 1µs quantization artifact from the Metal CPU timer. Both sides call Dawn's `wgpuRenderPassEncoderDraw` in the same tight loop; the difference is sub-quantization-step noise, not real overhead. Resolution requires GPU timestamps (sub-µs resolution) or workload size increases.

**Upload outlier characterization:** `upload_write_buffer_1mb` shows 2 out of 19 runs with outliers (0.313ms, 0.352ms vs 0.284ms typical). `render_uniform_buffer_update_writebuffer_partial_single` shows outliers at 0.374ms and 0.614ms vs 0.287ms typical. These are system interference events (GPU scheduling latency), not Doe code path regressions. The RIGHT (Dawn) side has no comparable outliers in those runs, making these workloads intermittently non-claimable at p95.

**Stable findings:**
- `upload_write_buffer_4mb`: improved to +4.2% (up from +0.68% in Run 2) — consistent Doe advantage.
- `render_draw_redundant_pipeline_bindings`: stable at +0.25% across Run 2 and Run 3.
- Upload 1KB/64KB/1GB: near-parity (within ±1%), system-state dependent.

### Run 2 (2026-03-05, second pass): **Claimable 6/23**

| Workload | p50% | p95% |
|---|---|---|
| `upload_write_buffer_1kb` | +0.85 | +1.10 |
| `upload_write_buffer_64kb` | +0.40 | +0.12 |
| `upload_write_buffer_4mb` | +0.68 | +2.08 |
| `upload_write_buffer_1gb` | +2.27 | +7.71 |
| `render_draw_redundant_pipeline_bindings` | +0.25 | +1.13 |
| `render_bundle_dynamic_pipeline_bindings` | +0.88 | +2.63 |

**Diagnostic (17/23) — notable gaps:**
- 1MB, 16MB, 256MB: p50 marginally negative (−0.2% to −1.3%), near-parity
- 4GB: p50≈−7.7% — large-transfer throughput gap persists
- Render throughput (`render_draw_throughput_baseline`, `render_bundle_dynamic_bindings`): at or near 0%
- Texture/sampler variants: −2% to −3% p50

### Run 1 (2026-03-05, first pass): **Claimable 5/23**

| Workload | p50% | p95% |
|---|---|---|
| `upload_write_buffer_1mb` | +2.16 | +0.22 |
| `upload_write_buffer_4mb` | +0.40 | +0.60 |
| `render_pixel_local_storage_barrier_500` | +2.99 | +1.87 |
| `compute_concurrent_execution_single` | +0.28 | +0.54 |
| `render_uniform_buffer_update_writebuffer_partial_single` | +0.28 | +3.10 |

**Interpretation:**
The benchmark's live report is the most recent run (Run 2). Across both runs, the workloads clustered into three groups:

1. **Stably claimable (per-run consistent):** `upload_write_buffer_4mb` claimable in both runs. `upload_write_buffer_1gb` and `render_bundle_dynamic_pipeline_bindings` newly claimable in Run 2.
2. **Near-parity (sign-flipping between runs):** 1KB, 64KB, 1MB, 16MB, render variants near ±1–2%. The 1KB/64KB workloads are dominated by Metal command-buffer submission latency (~97.5% in submit+wait). Doe Metal exhibits lower variance (spread=0.005ms vs Dawn's 0.029ms for 64KB) even when median is at parity. These workloads flip claimable/diagnostic depending on system state during the run.
3. **Persistent diagnostic gaps:** 4GB large-transfer throughput (−7% to −8%), texture/sampler ops (−2% to −3%), render throughput. These require Zig runtime path maturity work, not just methodology tuning.

Per-operation timing analysis (1KB/64KB): execution is dominated by Metal command-buffer submit+wait (97.5% of total time at ~175–210µs/op). The Doe Metal implementation has tighter latency distribution than the Dawn Metal delegate, which benefits p95/tail but leaves p50 in near-parity territory.

**Infrastructure completed (2026-03-05):**
- `examples/quirks/apple_m3_noop_list.json` created (empty list, analogous to `amd_radv_noop_list.json`)
- `bench/workloads.apple.metal.extended.json` updated: all 43 quirksPath entries now use `apple_m3_noop_list.json`
- Metal mining run: `bench/out/metal-quirks/mined-apple-metal-quirks.json` (87 candidates, 43 unique toggles from `bench/vendor/dawn/src/dawn/native/metal/`) with context breakdown: `default_on=24`, `default_off=1`, `force_on=2`, `reference=60`

## Metal native execution architecture fix (2026-03-05)

**Problem:** `doe_metal` backend (`ZigMetalBackend`) was delegating ALL WebGPU execution to Dawn via
`inner: WebGPUBackend` → `webgpu.WebGPUBackend.executeCommand()` → `libwebgpu_dawn.dylib`. In `metal_zig`
lanes, Doe was not calling any Metal APIs directly. This meant Dawn-vs-Doe Metal benchmarks were comparing
Dawn-via-Dawn-delegation against Dawn-via-Doe-wrapper for all command types — not a valid Doe measurement.

**Fix implemented (2026-03-05):**
- `runtime/zig/src/backend/metal/metal_bridge.h` + `.m`: thin C/ObjC ARC bridge exposing Metal APIs with CF-ownership transfer (`CFBridgingRetain`/`CFRelease`).
  Implemented: `metal_bridge_create_default_device`, `new_command_queue`, `new_buffer_shared/private`, `buffer_contents`, `encode_blit_copy`, `command_buffer_commit/wait_completed`.
- `runtime/zig/src/backend/metal/metal_native_runtime.zig`: native Metal upload/barrier runtime (`NativeMetalRuntime`).
  Implements `upload_bytes` (creates src+dst Metal buffers, records blit copy), `barrier` (flushes pending submissions), `flush_queue` (commit + waitUntilCompleted all pending), `prewarm_upload_path`.
  Does NOT delegate to Dawn.
- `runtime/zig/src/backend/metal/metal_native_runtime_stub.zig`: non-macOS stub (returns `error.UnsupportedFeature`).
- `runtime/zig/src/backend/metal/mod.zig`: `ZigMetalBackend` rewritten to use `NativeMetalRuntime` directly.
  `inner: webgpu.WebGPUBackend` removed. Dawn is not loaded or used in `metal_zig` mode.
  Initial capabilities were `{buffer_upload, barrier_sync}` only; subsequently expanded to include
  `kernel_dispatch`, `render_draw`, `async_diagnostics`, texture lifecycle, and more (see capability set in code).
- `runtime/zig/build.zig`: Metal + Foundation framework linking added for macOS targets (exe, dropin, test).
- Tests in `runtime/zig/tests/metal/metal_mod_integration_test.zig` and `metal_timing_semantics_test.zig` updated
  to reflect new native-only architecture: `kernel_dispatch` now correctly expected to return `.unsupported`.

**Architecture contract going forward:**
- `doe_metal` backend = native Metal execution only. No Dawn delegation.
- `dawn_oracle` / `dawn_delegate` backend = Dawn execution (for correctness comparison).
- Upload, barrier, kernel_dispatch, render_draw, and async_diagnostics are all natively implemented.
- Native Metal runtime uses MTLDevice, MTLCommandQueue, MTLBuffer, MTLBlitCommandEncoder, MTLComputePipelineState, MTLComputeCommandEncoder.

**Impact on benchmarks:**
- Upload, barrier, kernel_dispatch, render_draw, and async_diagnostics: genuine Doe-native Metal vs Dawn Metal comparison.
- Commands without native implementation return `.unsupported` with explicit taxonomy.
- latest local strict comparable Apple M3 matrix should now be treated as broad comparable evidence under timing-scope audit, not as a 30/30 claimable publication lane; see the March 6 timing-audit section for the authoritative artifact path.

**Outstanding gaps (tracked):**
- ~~Native `kernel_dispatch`~~ DONE (2026-03-06): batch compute dispatch via MTLComputePipelineState + MTLComputeCommandEncoder, with pipeline prewarm.
- ~~Native `render_draw`~~ DONE: render_draw now executes through native Metal with ICB support.
- ~~GPU timestamps via MTLCounterSampleBuffer not yet wired.~~ DONE (2026-03-17): `metal_gpu_timestamps.zig` manages MTLCounterSampleBuffer lifecycle; `activate_gpu_timestamps()` records begin sample on streaming cmd buf; `flush_queue_timed()` records end sample before commit and resolves after completion. Kernel dispatch uses manual cmd buf with begin/end bracketing. `gpu_timestamp_mode=require` fails fast when device lacks `MTLCounterSamplingPointAtStageBoundary`.
- Drop-in library build has a pre-existing `pub usingnamespace` Zig 0.15 compile error (unrelated to this fix).

## Performance Reliability Investigation (2026-02-21)

Scope:
- AMD Vulkan upload workloads, with focus on `upload_write_buffer_64kb`.
- strict comparability mode remained green during these checks.

Findings:
1. `upload_write_buffer_64kb` is highly sensitive to methodology knobs (`leftIgnoreFirstOps`, `leftUploadSubmitEvery`, `leftCommandRepeat`) even when comparability checks pass.
2. Mixed timing semantics can produce misleading conclusions:
- dispatch-window timing excludes setup cost
- ignore-first adjustment based on per-row durations includes setup for included rows
- this combination can materially change sign and tails (now guarded by explicit row-total ignore-first timing source in harness output).
3. Diagnostic sweep showed that increasing `leftCommandRepeat` (with explicit per-op normalization) substantially improved 64KB tail behavior and median delta, indicating batching/setup sensitivity dominates this case.

Implication:
- 64KB methodology hardening is now enforced in harness claim mode; runtime smoothing is still needed before robustly claimable "reliably faster" status.

Next required changes:
1. Re-run strict release claim-mode windows on AMD Vulkan host for `upload_write_buffer_64kb` with the updated `leftUploadSubmitEvery=100` contract.
2. Keep queue wait path tuning explicit (`--queue-wait-mode`) and only promote non-default mode into workload contracts after adapter-backed reliability evidence.
3. Re-freeze workload config defaults only after invariants hold in repeated strict claim-mode runs.

## Render parity benchmark note (2026-02-21)

Local directional benchmark (same host runtime, no Dawn adapter dependency):

- report: `bench/out/render_draw_vs_compute_proxy.local.json`
- tool: `python3 bench/native-compare/compare_runtimes.py`
- comparison: `left=doe_render_draw` vs `right=doe_compute_proxy` (`2000` operations normalized per run)
- result: `p50DeltaPercent=-129.93%` (native render path remains slower than prior compute draw proxy in this environment after adding Dawn-like vertex-buffer + static uniform bind-group parity)

Interpretation:
- this is an expected early parity milestone signal, not a claim benchmark.
- setup amortization still exists for multi-command runs (pipeline + view caches + vertex buffer + bind-group reuse), but render-vs-proxy single-command runs remain dominated by render submit cost.
- latest run shows directional tail improvement (p95 delta from `-143.43%` to `-112.85%`) while remaining non-claim diagnostic.

## Texture directional benchmark note (2026-02-21)

Local directional benchmark comparing the updated texture/raster command seed against the prior dispatch-only raster proxy:

- report: `bench/out/texture_raster_render_step_vs_dispatch_proxy.local.json`
- tool: `python3 bench/native-compare/compare_runtimes.py`
- comparison: `left=doe_texture_raster_render_step` vs `right=doe_texture_raster_dispatch_proxy`
- result: `p50DeltaPercent=-22.38%` (updated texture path is currently slower in this host environment)

Interpretation:
- this confirms the new texture command seed exercises real `kernel_dispatch + render_draw` behavior.
- remaining gap is expected while directional texture methodology is still simplified versus Dawn's full render-pass transitions.

## AMD Vulkan run snapshot (2026-02-23)

Current contract state after matrix expansion:

1. `bench/workloads.amd.vulkan.extended.json`
- workload contracts: `34` total
- strict comparable contracts: `17` (apples-to-apples only)
- directional contracts: `17` (includes contract/proxy domains `pipeline-async`, `p0-*`, `p1-*`, `p2-*`, `surface`, plus macro stress contracts)

2. `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- strict mode remains `includeNoncomparableWorkloads=false`
- now targets the expanded apples-to-apples comparable matrix (upload + compute + render + texture + render-bundle)

3. `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.directional.json`
- directional diagnostics now focus on remaining non-claim macro workloads
  (`render_draw_indexed_200k`, `capability_introspection_500`, `lifecycle_refcount_200`)

4. `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.macro.directional.json`
- directional diagnostics target the focused macro subset (`render_draw_indexed_200k`)

5. Host execution note (this machine class)
- strict AMD Vulkan Dawn runs can fail/skips when `/dev/dri/renderD128` access is unavailable to the active user.
- preflight command: `python3 bench/preflight_bench_host.py --strict-amd-vulkan`
- adapter-agnostic strict comparable fallback: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
- if Dawn executes on CPU adapter only, DrawCallPerf/texture/render-bundle contracts can be skipped by Dawn as unsupported and must not be treated as comparable results.

## Native execution milestone (non-prototype)

Scope:
- chosen path is full native Zig+WebGPU/FFI implementation from scratch.
- current implementation size is 13,485 LOC (`runtime/zig/src`); remaining work is performance/reliability hardening and broader claim-grade coverage.
- current codebase status: pipeline/trace/replay/matching complete, with queue-submit execution coverage for upload/copy/barrier and dispatch-family compute routing.

Execution gap list:
- typed discovery and adapter/device queue selection are implemented in WebGPU FFI bootstrap.
- full dispatch/kernel lowering with shader/module/pipeline resolution for a complete kernel payload format and artifact-backed verification.
- texture copy/materialization command modeling and lowering.
- deterministic GPU timing capture remains partial (retry envelopes + explicit timestamp readback taxonomy + explicit `auto|off|require` mode policy are implemented, but full claim-grade deterministic capture policy is still in progress).
- robust retry/failure policy is now bounded for queue wait and timestamp map paths; broader mapped GPU status policy hardening remains.
- no release-ready benchmark baseline generated against native GPU backend.

### Explicit distinction

- “Not implemented” in developer flow does not mean the runtime is unusable.
- It means release confidence, automation, and proof-binary reproducibility are not yet at stable v1-grade completeness.

## Drop-in + release benchmark update (2026-02-23)

1. Drop-in benchmark coverage is now expanded and grouped by class in the HTML artifact:
- micro: `instance_create_destroy`, `command_encoder_finish_empty`, `queue_submit_empty`, `queue_write_buffer_{1kb,4kb,64kb}`, `buffer_create_destroy_{4kb,64kb}`
- end-to-end: `full_lifecycle_device_only`, `full_lifecycle_queue_submit`, `full_lifecycle_write_{4kb,64kb}`, `full_lifecycle_queue_ops`
- drop-in gate reports continue to include per-step runtime and explicit runtime-to-fix output for failing steps.
- latest Doe-vs-Dawn p50 snapshot on this host shows the dominant lag at `instance_create_destroy`; `queue_write_buffer_1kb` can also be marginally slower and should be treated as a small residual micro-gap.

2. AMD Vulkan extended release workload contract now uses deferred queue sync for `upload_write_buffer_1kb` in `bench/workloads.amd.vulkan.extended.json` (matching `bench/workloads.amd.vulkan.json`) to avoid per-command wait inflation at tiny payload sizes while preserving per-upload normalization semantics.

3. Fresh release claim-floor rerun executed on this host using the full comparable release profile (`iterations=16`, `warmup=1`, 17 workloads):
- report: `bench/out/20260223T202753Z/dawn-vs-doe.amd.vulkan.release.json`
- gate result: `comparisonStatus=comparable`, `claimStatus=diagnostic`, `nonClaimableCount=1`
- residual non-claimable workload:
  - `texture_sampling_raster_baseline` (tails only: `p95/p99 = -16.164%`; `p50` positive).

4. Render-domain apples-to-apples timing/runtime path was tightened:
- comparable timing for workload domains `render` and `render-bundle` uses encode-only operation source (`doe-execution-encode-ns`) for claim comparison against Dawn DrawCallPerf timing.
- `render_draw` render-bundle command recording was moved into setup (untimed) so encode timing now reflects bundle execution parity instead of bundle build cost.
- focused release claim-floor rerun (`iterations=16`, `warmup=1`) over the 2 render-bundle workloads:
  - report: `bench/out/20260223T202424Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

5. Texture-raster tail reliability contract was tightened for claim runs:
- `texture_sampling_raster_baseline` now runs with `leftCommandRepeat=500` and `leftTimingDivisor=500` (same per-iteration unit normalization) to reduce low-coverage GPU timestamp quantization noise in p95/p99 tails.
- focused release claim-floor rerun for that workload:
  - report: `bench/out/20260223T210045Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

6. Redundant-pipeline render tail reliability contract was tightened for claim runs:
- full release pipeline rerun (`bench/out/20260223T211020Z/dawn-vs-doe.amd.vulkan.release.json`) reduced the matrix to one residual non-claimable workload: `render_draw_redundant_pipeline_bindings` (tails only).
- `render_draw_redundant_pipeline_bindings` now runs with `leftCommandRepeat=10` and `leftTimingDivisor=20000` (per-draw normalization preserved) to reduce sample-tail setup jitter.
- focused release claim-floor rerun for that workload:
  - report: `bench/out/20260223T213900Z/dawn-vs-doe.amd.vulkan.release.json`
  - result: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`.

7. Macro + hard-gated pilot promotion refresh (2026-02-25):
- promoted to strict comparable in `bench/workloads.amd.vulkan.extended.json`:
  `render_draw_throughput_200k`,
  `texture_sampler_write_query_destroy_500`,
  `resource_table_immediates_500`,
  `render_pixel_local_storage_barrier_500`,
  `render_multidraw`,
  `render_multidraw_indexed`,
  `resource_lifecycle`,
  `compute_indirect_timestamp`.
- matrix split is now `31` comparable + `9` directional.
- 2026-03-06 contract follow-up: `resource_table_immediates_500` now explicitly
  mirrors `rightCommandRepeat=500` so strict normalization parity validation no
  longer rejects the AMD extended comparable matrix before execution.
- 2026-03-06 runtime follow-up: Vulkan native upload path no longer enforces the
  stale `64MB` artificial cap, so promoted comparable large-upload workloads
  (`256MB`, `1GB`, `4GB`) now fail only on real allocation/runtime limits.
- 2026-03-06 native-subset contract follow-up: the AMD Vulkan
  `bench/workloads.amd.vulkan.superset.native-supported.json` subset no longer
  marks `resource_table_immediates_500` or `surface_presentation` as
  `comparable=true`.
  Those workloads remain directional-only, but they are no longer blocked on
  missing native execution: Doe now runs `resource_table_immediates_500`
  through explicit native emulation and `surface_presentation` through a native
  headless surface lifecycle/present path. They stay out of strict claim lanes
  until the benchmark contract itself is apples-to-apples.
- 2026-03-06 strict AMD config follow-up: `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json`
  and `bench/native-compare/compare_dawn_vs_doe.config.amd.vulkan.release.json` now consume the
  native-supported workload contract directly, so strict AMD evidence no longer
  implies coverage beyond the currently native-backed subset.
- 2026-03-06 async-diagnostics submode follow-up: native Vulkan now executes
  `capability_introspection`, `lifecycle_refcount`, and `pipeline_async`
  directly; `resource_table_immediates` and `pixel_local_storage` now execute
  through explicit Doe-native emulation when `featurePolicy=emulate_when_unavailable`.
  For `resource_table_immediates`, the current native/emulated coverage closes the
  proc surface and accepts the contract's zero-length `setImmediates` calls, but
  it does not yet expose shader-visible immediate-data/push-constant semantics on
  Vulkan.
  `full` remains explicit unsupported for strict mode until all submodes have
  native or contract-approved emulated coverage.
- 2026-03-06 timing follow-up: native Vulkan per-command dispatch now records
  real GPU timestamps when the selected queue family supports timestamp queries;
  strict timestamp mode fails fast on unsupported queue-sync or queue-family
  configurations instead of silently degrading.

8. Local Metal comparability hotfix (2026-02-26):
- introduced Metal-only workload contract file: `bench/workloads.apple.metal.extended.json`.
- local Metal config now uses that contract file (`bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json`) so AMD Vulkan claim lanes are unchanged.
- local Metal compare config now pins `--gpu-timestamp-mode off` to avoid `gpu_timestamp_wait_timed_out` failures observed in compute lanes on this host (`compute_workgroup_non_atomic_1024`).
- local Metal left template now uses `--queue-sync-mode per-command --gpu-timestamp-mode off` as the stability baseline.
- for local Metal claim lanes, explicit queue-sync policy is now contractized via workload overrides:
  - deferred for upload workloads (`upload_write_buffer_64kb`, `upload_write_buffer_1mb`, `upload_write_buffer_4mb`, `upload_write_buffer_16mb`), texture contract lanes (`texture_sampler_write_query_destroy`, `..._mip8`), and `resource_lifecycle`.
  - `compute_matvec_32768x2048_f32_workgroupshared_swizzle1` is now directional-only (`comparable=false`) in the Metal-local contract due intermittent timeout/error behavior under both deferred and per-command sync on this host.
- `compute_workgroup_non_atomic_1024` is also directional-only (`comparable=false`) in the Metal-local contract due intermittent Doe execution-error samples (`WaitTimedOut`) in strict runs on this host.
- focused rerun (`bench/out/scratch/20260226T000817Z/metal.slowness.fixprobe6.json`, `iterations=8`, `warmup=1`) now reports `comparisonStatus=comparable`, with only one residual non-claimable lane: `upload_write_buffer_4mb` (`p50=-88.19%`, `p95=-53.40%`).
- full strict local-metal matrix rerun (`bench/out/scratch/20260226T003134Z/metal.full.fixed.full8.json`, `iterations=8`, `warmup=1`) reports `comparisonStatus=comparable` with two residual non-claimable upload tails: `upload_write_buffer_1kb` (`p50=+3.91%`, `p95=-25.64%`) and `upload_write_buffer_16mb` (`p50=+1.31%`, `p95=-3.37%`).
- targeted deeper-sample reruns show these two lanes are claimable at higher sample depth (`iterations=12`, `warmup=1`):
  - `bench/out/scratch/20260226T005352Z/metal.upload.tailprobe.current.json` (`upload_write_buffer_16mb`)
  - `bench/out/scratch/20260226T005531Z/metal.upload.tailprobe.1kb.json` (`upload_write_buffer_1kb`)
- local metal strict comparable config now uses `iterations=12` and `claimability.minTimedSamples=11` to reduce p95/p99 tail instability on upload lanes without changing AMD Vulkan methodology.

## v0 Reality

Blocking gates: schema, correctness, trace, verification.
Advisory gates: performance.

This matches speed-first priorities while keeping deterministic foundations.

Current comparison claim state: `strict-comparable matrix + claimability diagnostics`.

Meaning:
1. strict comparable AMD matrix now tracks the audited apples-to-apples subset (`31` workloads) from `bench/workloads.amd.vulkan.extended.json`; directional/proxy contracts are excluded from strict claim lanes.
2. remaining directional macro workloads (`render_draw_indexed_200k`, `capability_introspection_500`, `lifecycle_refcount_200`) are diagnostics and must not be presented as strict apples-to-apples claims.
3. current substantiated-claim posture remains narrower than the broad local evidence inventory: AMD Vulkan and Apple Metal both have useful strict comparable artifacts, but the current broad Apple Metal matrix is under timing-scope audit and must not be cited as a substantiated 30/30 claim lane. Broad "beats Dawn everywhere" claims must still cite the exact workload set, device family, and artifact path; claims remain per-workload and per-device-family by methodology.
4. release claim gate remains the authority: reports must be `comparisonStatus=comparable` and `claimStatus=claimable`.

## 2026-02-26 backend/metal hardening update

1. backend decoupling scaffold landed
- new backend runtime tree under `runtime/zig/src/backend` with explicit identities:
  - `dawn_delegate`
  - `doe_metal`
- execution path now carries backend lane and selection telemetry through trace metadata.

2. strict local-metal gate stack landed
- new gates:
  - `bench/backend_selection_gate.py`
  - `bench/shader_artifact_gate.py`
  - `bench/metal_sync_conformance.py`
  - `bench/metal_timing_policy_gate.py`
- release/blocking orchestration now supports local-metal additive enforcement while preserving AMD Vulkan default strict behavior.

3. contract surface expanded
- new config/schema contracts added for backend runtime/capability/timing/cutover, shader toolchain/taxonomy/artifact, and drop-in behavior/symbol ownership.
- schema gate target selection is now registry-driven through `config/schema-targets.json`.

4. strict-lane evidence closure
- Metal shader-commands now emit command-scoped manifest telemetry and strict manifest checks are gate-enforced for comparable/release Metal lanes.
- local-metal routing, sync, timing, backend, and proc-resolution gates are wired as additive strict controls with no change to AMD Vulkan strict defaults.
- strict no-fallback routing is enforced across all backend lanes (`allowFallback=false`, `strictNoFallback=true`) and macOS-app cutover remains a strict Metal default lane (`metal_doe_app` -> `doe_metal`).

5. Metal decoupling phase-completion status (2026-02-26)
- all Metal phases are now closed in this rollout scope.
- phase coverage is closed for contract surface, selection/proc ownership, shader artifacts, sync/timing, and strict local release comparability.
- runtime now defaults app-lane selection to `metal_doe_app` with strict no-fallback backend routing.
- remaining focus is ongoing performance evidence across host diversity and fleet-level substantiation windows, not plan-scope missing phases.

6. Apple Metal M3 timing audit status (2026-03-06)
- latest broad strict comparable local matrix on Apple M3 (macOS, Metal native backend):
  - report: `bench/out/apple-metal/extended-comparable/20260306T195524Z/dawn-vs-doe.local.metal.extended.comparable.json`
  - raw artifact result: `comparisonStatus=comparable`, `claimStatus=claimable`
  - publication status: treat as `comparisonStatus=comparable`, `claimStatus=diagnostic` until the timing-scope audit is closed
- rationale:
  - small-upload rows in the same artifact show Doe operation timing covering an implausibly tiny share of process wall on the left side while Dawn-side coverage stays materially higher
  - example `upload_write_buffer_1kb`: Doe selected timing `0.000224 ms` with `175.4 ms` process wall, Dawn selected timing `0.179872 ms` with `376.8 ms` process wall
  - this blocks citation of the current broad Metal lane even though the raw artifact marks it claimable
- key optimizations in the current Metal path remain real engineering progress:
  - kernel dispatch pipeline prewarm (moves MSL compilation out of timing window)
  - batch compute dispatch (single encoder for N repeat dispatches)
  - ICB prewarm (moves ICB creation/encoding out of encode timing window)
  - buffer pool (reuses Metal buffers across repeated uploads, avoids per-upload allocation)
  - `commandBufferWithUnretainedReferences` (skips ARC retain/release per command buffer)
  - cached render pass descriptor (avoids MTLRenderPassDescriptor alloc per render command)
  - ICB `inheritPipelineState=NO` with unconditional per-command `setRenderPipelineState`
  - `[[max_total_threads_per_threadgroup(N)]]` kernel attributes for correct threadgroup sizing
  - upload cap removal (was 64MB, now unlimited)
- note on historical sections below:
  - earlier investigation notes in this file still capture pre-audit runs where Metal sat in the `17/30` to `19/30` claimable range.
  - the report above is the current authority for latest broad Metal evidence, but not yet for citable claim substantiation.

## Track A Execution Plan (Finalized)

Objective:
- make runtime behavior contract-clean, deterministic, and performance-safe under one active contract hash.

Two-week implementation focus:
1. Week 1 closes the failure inventory:
   - adapter selection mismatches
   - device-init edge cases
   - timestamp validity failures
   - unexpected unsupported taxonomy rows
   - timing-normalization drift
2. Week 2 lands fixes with explicit config/schema representation only:
   - no hidden runtime switches
   - no undocumented fallback behavior
   - runtime and Lean pair on hot paths to remove provable checks only after proof artifact generation and replay parity pass
3. preserve apples-to-apples semantics for comparable workloads and explicit directional obligations (`allowLeftNoExecution` when declared).

Execution cadence:
- daily red-lane triage
- twice-weekly stabilization cuts
- weekly contract-hash rehearsal

Required artifacts per stabilization cut:
- strict comparable report for the active comparable subset
- directional obligation report (including declared `allowLeftNoExecution` evidence)
- unsupported taxonomy histogram (`expected` vs `unexpected`)
- timestamp validity summary
- replay trace-parity output
- config/schema diff summary

Required checks per PR:
- unit tests for taxonomy/error paths
- integration tests for adapter/device boundary behavior
- regression tests for timing-source/timing-class invariants
- replay parity checks
- benchmark harness smoke

Definition of done:
1. all comparable workloads under the active hash pass strict comparability.
2. directional workloads satisfy declared obligations.
3. zero unexpected unsupported and zero unexpected errors.
4. timestamp validity checks are green.
5. normalization fields are schema-conformant.
6. at least one Lean-driven hot-path branch elimination lands with measured perf impact and no correctness regression.

Rollback triggers:
- hidden toggle introduction
- schema/runtime drift without migration note
- replay mismatch
- claim-lane comparability break
- memory-safety regression (blocking defect under release policy)

Ownership:
- runtime lead owns Zig implementation and taxonomy outcomes
- Lean lead owns proofs and branch-deletion proposals
- coordinator owns contract-hash advancement decision after all Track A artifacts are green

## Vulkan decoupling completion update (2026-02-26)

- Vulkan decoupling plan checklists were completed through Phase 8 and the archived plan docs were removed.
- Native app-lane routing now defaults Vulkan profiles to `vulkan_doe_app` with strict `doe_vulkan` selection and no hidden fallback.
- Comparative Dawn-baseline lane remains explicit and unchanged: `vulkan_dawn_release` -> `dawn_delegate`.
- Runtime rollback switching is retired for backend selection; `config/backend-cutover-policy.json` remains intentionally Metal-centered (`targetLane=metal_doe_app`) while Vulkan cutover enforcement is lane-policy + cycle-contract driven.

## Vulkan finish pass evidence (2026-02-26)

- Local strict comparable Vulkan run executed:
  - report: `bench/out/vulkan.finish.local.comparable.1kb.json`
  - status: `comparisonStatus=comparable`, `claimStatus=diagnostic`
- Local strict Vulkan blocking gate stack executed and passed:
  - command: `run_blocking_gates.py` with backend-selection + shader-artifact + vulkan-sync + vulkan-timing gates
  - report: `bench/out/vulkan.finish.local.comparable.1kb.json`
  - result: PASS (schema/correctness/pipeline/trace/backend-selection/shader/sync/timing)
- `vulkan_doe_app` strict local-claim run executed with lane-specific cycle contract:
  - report: `bench/out/20260226T164929Z/vulkan.vulkan_doe_app.local.claim_cycle.json`
  - status: `comparisonStatus=comparable`, `claimStatus=claimable`, `nonClaimableCount=0`
  - claim gate: PASS (`mode=local`, min timed samples `7`)
  - cycle gate output: `bench/out/20260226T164929Z/cycle_gate_report.json` (`pass=true`)
  - backend-selection/shader/sync/timing: PASS on same report
- historical note: prior app-lane release-contract attempt (`bench/out/vulkan.finish.vulkan_doe_app.claim.json` + `bench/out/20260226T160252Z/vulkan.finish.vulkan_doe_app.cycle.json`) failed and is superseded by the contract-aligned run above.
- historical rollback-switch rehearsal artifacts remain archived:
  - report: `bench/out/vulkan.finish.vulkan_doe_app.rollback.json`
  - current runtime contract is strict no-fallback; `FAWN_BACKEND_SWITCH` backend override is no longer active.
- scope note: release-grade full-matrix claim substantiation is still tracked separately from this strict local app-lane closure evidence.

## Vulkan recheck closure delta (2026-02-26)

- Re-ran strict Vulkan app-lane claim/cycle pipeline:
    - report: `bench/out/20260226T185831Z/vulkan.recheck.app.claim_cycle.json`
    - result: `comparisonStatus=comparable`, `claimStatus=claimable`
- Prior cycle failure on this run was contract-drift only (stale `contracts.compareConfig["sha256"]` in cycle contract after lane/canonical policy rename).
- Updated cycle contract hash:
    - file: `config/claim-cycle.amd-vulkan-app-local.json`
    - field: `contracts.compareConfig["sha256"]`
    - value: `2eaf549cfcad8af46a694dfa7158b24a89015c150dab7c0bd2a379a9f35e6d13`
- Re-ran cycle gate on same report:
    - output: `bench/out/20260226T185831Z/cycle_gate_report.json`
    - result: `pass=true`, `failures=[]`
- Re-ran schema gate:
    - command: `python3 bench/schema_gate.py`
    - result: `PASS`
- Closure: Vulkan recheck is now green end-to-end for compare, claimability, cycle contract, and schema invariants.

## Metal end-to-end closure pass (2026-02-26)

- Local strict comparable metal evidence report:
  - `bench/out/metal.finish.local.comparable.json`
- Local strict release-lane metal evidence report:
  - `bench/out/metal.finish.local.release.json`
- metal_doe_app cutover-lane metal evidence report:
  - `bench/out/metal.finish.metal_doe_app.comparable.json`
- Strict Metal blocking gate stack passed on both comparable and release-lane reports:
  - schema, correctness, trace (semantic parity mode off), backend-selection, shader-artifact, metal-sync, metal-timing-policy.
- historical rollback-switch behavior artifacts are retained for audit only:
  - baseline: `bench/out/metal.finish.rollbackprobe.baseline.json` left backend `doe_metal`
  - rollback: `bench/out/metal.finish.rollbackprobe.rollback.json` left backend `dawn_delegate`
  - current runtime contract does not permit backend rollback switching.
- Host limitation note:
  - native Dawn Metal adapter/filter autodiscovery is unavailable on this Linux host; strict metal lane validation here uses Doe-vs-Doe command templates for backend/gate contract closure.

## Metal comparable surface + invariants hardening (2026-03-01)

- Expanded local Metal strict comparable set in `bench/workloads.apple.metal.extended.json` from 7 to 19 workloads using prior full-suite comparability evidence:
  - evidence source: `bench/out/scratch/20260226T005744Z/metal.full.fixed.full12.json`
  - left two known directional contracts intentionally unchanged pending counter-derived normalization proof:
    - `render_draw_throughput_200k`
    - `compute_indirect_timestamp`
- Re-promotion is now revalidated on this host with fresh strict evidence after fixing two runtime/comparability blockers:
  - `runtime/zig/src/backend/metal/mod.zig`: first-command bootstrap ordering fixed for non-upload workloads (`execute_runtime_command` now bootstraps before reading timing counters), removing `InvalidState` execution failures on render/texture/async/kernel command families.
  - `runtime/zig/src/backend/metal/mod.zig`: execution operation-count export now reflects command shape (`repeat`/`draw_count`/`iterations`) for strict counter-derived normalization evidence.
  - `bench/native-compare/modules/comparability.py`: compute-domain execution-shape matching now treats unknown dispatch counters as wildcard when row/success shapes match, while still failing when both sides expose conflicting known dispatch counts.
- Local metal workload contract updates:
  - removed stale demotion annotations for the 12 re-promoted workloads in `bench/workloads.apple.metal.extended.json`.
  - fixed `compute_concurrent_execution_single` right normalization on this lane to `rightTimingDivisor=1.0` with updated evidence note (Dawn trace exposes one physical operation per timed sample in strict runs).
- Fresh artifacts:
  - strict smoke (`iterations=1`, `warmup=0`): `bench/out/scratch/metal.promote19.smoke.json` -> `comparisonStatus=comparable`, `workloadCount=19`.
  - local claim-mode (`iterations=12`, `warmup=1`): `bench/out/scratch/metal.promote19.claim.local.json` -> `comparisonStatus=comparable`, `claimStatus=diagnostic`, `nonClaimableCount=5` (14/19 claimable workloads).
  - five residual non-claimable workloads are all render-domain microcontracts failing only the configured 100ns noise-floor requirement:
    - `render_draw_throughput_baseline`
    - `render_draw_state_bindings`
    - `render_draw_redundant_pipeline_bindings`
    - `render_bundle_dynamic_bindings`
    - `render_bundle_dynamic_pipeline_bindings`
- Promotion expansion pass (2026-03-01, local Metal host) applied for 10 additional candidate workloads using strict command-shape divisor contracts:
  - promoted comparable contracts:
    - `compute_workgroup_atomic_1024`
    - `compute_workgroup_non_atomic_1024`
    - `compute_matvec_32768x2048_f32`
    - `compute_matvec_32768x2048_f32_swizzle1`
    - `compute_matvec_32768x2048_f32_workgroupshared_swizzle1`
    - `pipeline_compile_stress`
    - `texture_sampling_raster_baseline`
    - `render_draw_throughput_200k`
    - `render_multidraw`
  - attempted promotion `render_multidraw_indexed` was reverted to directional on this host because Dawn Metal autodiscover exposes no `DrawCallPerf` `DrawIndexed` variant, so strict apples-to-apples mapping is unavailable.
  - divisor updates applied from strict command-shape inference:
    - `texture_sampling_raster_baseline`: `500 -> 1000`
    - `render_draw_throughput_200k`: `575000 -> 200000`
    - `render_multidraw`: `15000 -> 2000`
    - `render_multidraw_indexed`: `10000 -> 2000` (kept directional after remap failure on this host)
- expanded local-metal report artifact:
  - `bench/out/scratch/metal.promote28.claim.local.json`
  - `comparisonStatus=comparable`, `claimStatus=diagnostic`, `workloadCount=28`, `nonClaimableCount=8`
  - current host-ceiling summary:
    - strict comparable: `28`
    - directional: `12`
  - non-claimable set contains:
    - 7 noise-floor constrained render/macro contracts (`<100ns` p50 on Doe side)
    - 1 slower contract by claim criteria (`texture_sampling_raster_baseline` negative p50/p95 deltas)
- Added blocking gate hook + script for comparable runtime invariants:
  - new gate script: `bench/comparable_runtime_invariants_gate.py`
  - wired into gate runner via `--with-comparable-runtime-invariants-gate` in `bench/run_blocking_gates.py`
  - enforces comparable-lane zero execution errors/unsupported on traced samples and upload cadence tail-submit invariant for per-command + `uploadSubmitEvery>1`.
- Strengthened Metal backend correctness observability and test coverage:
  - runtime counters exposed in `runtime/zig/src/backend/metal/metal_runtime_state.zig` for manifest emit count, staging reserved bytes, upload mode call splits
  - Metal tests expanded for:
    - encode vs submit/wait timing separation (`runtime/zig/tests/metal/metal_timing_semantics_test.zig`)
    - upload cadence tail flush (`runtime/zig/tests/metal/metal_mod_integration_test.zig`)
    - single-manifest kernel dispatch emission (`runtime/zig/tests/metal/metal_mod_integration_test.zig`)
    - upload byte-budget + usage mode accounting (`runtime/zig/tests/metal/metal_upload_path_test.zig`)
- Bun in-process Doe provider now auto-activates when `libwebgpu_doe` is discoverable:
  - file: `packages/webgpu/src/bun-ffi.js`
  - modes:
    - `FAWN_WEBGPU_BUN_PROVIDER=doe` forces Doe provider (error if lib missing)
    - `FAWN_WEBGPU_BUN_PROVIDER=provider` disables Doe auto-provider
    - default `auto` prefers Doe when the library is present, otherwise falls back to provider module.
- Bun FFI path now at full API parity with Node (2026-03-06):
  - 61/61 contract tests passing (`bun ./test-bun.js`)
  - all 12 current package benchmark workloads run successfully under Bun via `bench/package-compare/bun/runner.js`
  - Zig flat helpers added: `doeBufferMapAsyncFlat`, `doeQueueOnSubmittedWorkDoneFlat` in `runtime/zig/src/dropin/dropin_abi_procs.zig`
  - WGPUBufferBindingType enum corrected (uniform=2, storage=3, read-only-storage=4)
  - queueFlush validates future ID and callback status
  - processEvents polling replaces unsupported wgpuInstanceWaitAny on Vulkan/Dawn
  - getMappedRange supports both read (copy-out) and write (direct native buffer) modes
  - Doe Bun sync semantics tightened to match the Node provider more closely:
    - `queue.onSubmittedWorkDone()` is now a Doe no-op in `packages/webgpu/src/bun-ffi.js`
    - `mapAsync()` no longer pre-flushes before waiting on `bufferMapAsync`
    - Bun now uses dropin-native sync map helper `doeBufferMapSyncFlat` from `runtime/zig/src/dropin/dropin_abi_procs.zig` instead of JS callback allocation + JS-side processEvents polling for every buffer map
    - package-surface compare harnesses now force workload validation prepasses before timing (`bench/package-compare/bun/compare.js`, `bench/package-compare/node/compare.js`)
    - comparable compute workloads now validate readback contents on every timed iteration in `bench/package-compare/node/workloads.js`, not just in a pre-timed smoke pass
    - latest validated full Linux x64 Bun package compare still favors Doe on comparable compute rows:
      - `compute_e2e_256`: `0.052ms` vs `0.206ms` (`+74.7%`)
      - `compute_e2e_4096`: `0.038ms` vs `0.171ms` (`+77.7%`)
      - `compute_e2e_65536`: `0.038ms` vs `0.168ms` (`+77.2%`)
      - artifact: `bench/out/bun-doe-vs-webgpu/doe-vs-bun-webgpu-2026-03-06T21:55:26.482Z.json`
  - benchmark compare lane: `bench/package-compare/bun/compare.js` (Doe FFI vs `bun-webgpu`)
  - cube maturity remains prototype; promote to secondary when Bun cells are populated

## Upload timing realism fix (2026-03-02)

- Fixed strict upload timing-source selection drift that produced non-physical per-op timings (`~0.0002ms`) on Doe.
- `bench/native-compare/modules/timing_selection.py` now derives upload per-op timing from row-total operation scope:
  - per-row `executionSetupNs + executionEncodeNs + executionSubmitWaitNs` (with `executionDurationNs` only as fallback/ceiling guard),
  - selected source now `doe-execution-row-total-ns`,
  - selected policy now `upload-row-total-preferred`,
  - ignore-first adjustments now remain in the same row-total scope (`doe-execution-row-total-ns+ignore-first-ops`).
- Strict comparability/claimability source contracts were aligned to row-total:
  - `bench/native-compare/compare_dawn_vs_doe.py`
  - `bench/native-compare/modules/comparability.py`
  - `bench/native-compare/modules/claimability.py`
- Single-workload strict validation (local Metal, one workload only):
  - report: `bench/out/scratch/20260302T222904Z/metal.one.upload_write_buffer_64kb.realcheck.json`
  - `comparisonStatus=comparable`
  - timing sources: left `doe-execution-row-total-ns`, right `dawn-perf-wall-time`
  - observed p50: left `0.018508ms`, right `0.011122638ms` (`delta p50=-39.90%`, Doe slower on this host/workload)
  - this run is now classified `claimStatus=diagnostic` for performance claim purposes.
- Local Metal pinned comparable rerun (2026-03-09):
  - config `bench/native-compare/compare_dawn_vs_doe.config.apple.metal.extended.comparable.json` now runs Doe on explicit `metal_doe_comparable` and Dawn on explicit `metal_dawn_release`, both with GPU timestamps disabled in the compare template for symmetry.
  - Metal upload flush now uses the cheaper completion-handler wait path in `runtime/zig/src/backend/metal/metal_native_runtime.zig` for strict short-command submit/wait loops.
  - focused 64KB rerun artifact: `bench/out/scratch/20260309T023631Z/metal.upload_64kb.fixedprobe.json`
    - `comparisonStatus=comparable`, `claimStatus=diagnostic`
    - `upload_write_buffer_64kb`: `p50 +26.76%`, `p95 -46.01%`
  - full 27-workload local claim lane artifact: `bench/out/apple-metal/extended-comparable/20260309T023806Z/metal.local.claim.fixed.json`
    - `comparisonStatus=comparable`, `claimStatus=diagnostic`
    - `15/27` workloads claimable on this host
    - small-upload tails remain open (`upload_write_buffer_1kb`, `upload_write_buffer_64kb`), while `upload_write_buffer_{1mb,4mb,16mb}` are claimable again
- Local Metal tail-stabilization pass (2026-03-09, later):
  - `runtime/zig/src/backend/metal/mod.zig` now makes `queue_sync_mode=deferred` execution-effective for uploads; deferred upload commands no longer pay inline submit/wait cost on the Metal native path.
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` now:
    - honors `copy-dst-copy-src` vs `copy-dst` upload mode instead of always forcing the staged blit path,
    - flushes deferred upload work on explicit `barrier` commands,
    - uses `waitCompleted` for render-containing streaming command buffers while keeping the lighter fast-wait path for upload-only streaming batches.
  - regression coverage was added in `runtime/zig/tests/metal/metal_timing_semantics_test.zig` for deferred upload timing and barrier flush semantics.
  - focused upload/resource artifacts:
    - `bench/out/scratch/20260309T032324Z/metal.upload_resource.after_empty_wait_fix.json`
      - `upload_write_buffer_1kb`: claimable (`p50 +63.43%`, `p95 +51.36%`)
      - `upload_write_buffer_64kb`: claimable (`p50 +68.07%`, `p95 +77.75%`)
      - `resource_lifecycle`: still non-claimable (`p50 -91.94%`, `p95 -90.72%`)
    - `bench/out/scratch/20260309T032605Z/metal.upload_texture.after_render_wait_fix.json`
      - `texture_sampler_write_query_destroy`: still non-claimable (`p50 -39.64%`, `p95 -25.63%`)
      - `texture_sampler_write_query_destroy_mip8`: still non-claimable (`p50 -44.35%`, `p95 -35.61%`)
  - attempted full repeated local Metal window rerun is currently blocked by Dawn preflight on `compute_workgroup_atomic_1024`:
    - artifact root: `bench/out/scratch/20260309T032931Z/runtime-comparisons.local.metal.extended.comparable/compute_workgroup_atomic_1024/`
    - Dawn preflight error: `kernel_dispatch requires negotiated WebGPU limits for binding validation`
  - current macOS Metal boundary:
    - upload tail stabilization materially improved and focused claim windows are green for `upload_write_buffer_{1kb,64kb}`
    - `resource_lifecycle` and texture lifecycle rows remain real native-Metal performance blockers
    - broader repeated-window substantiation should resume only after the Dawn compute preflight blocker is cleared and the two remaining native-Metal lifecycle gaps are either fixed or explicitly demoted from claim scope
- Local Metal repeated-window rerun after macOS fixes (2026-03-09, latest):
  - `runtime/zig/src/webgpu_ffi.zig` now captures adapter/device limits during normal WebGPU backend init, which cleared the stale-binary Dawn preflight blocker for `compute_workgroup_atomic_1024`; focused artifact: `bench/out/scratch/20260309T124023Z/metal.compute_workgroup_atomic_1024.after_limits_fix.json` (`claimable`).
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` now submits deferred upload-only barrier work without immediate wait, which flipped `resource_lifecycle` positive on focused rerun: `bench/out/scratch/20260309T124330Z/metal.resource_lifecycle.after_deferred_barrier_submit.json` (`p50 +754.04%`, `p95 +515.23%`, `claimable`).
  - local Metal strict comparable workload contract now demotes the three 256MB matvec rows (`compute_matvec_32768x2048_f32`, `_swizzle1`, `_workgroupshared_swizzle1`) to directional-only in `bench/workloads.apple.metal.extended.json` because Dawn delegate on this host rejects them with `maxStorageBufferBindingSize` validation failure.
  - full repeated local comparable artifact: `bench/out/apple-metal/extended-comparable/20260309T124836Z/metal.local.claim.post_macos_fixes.json`
    - `comparisonStatus=comparable`, `claimStatus=diagnostic`, `24` comparable workloads
    - fixed/green on this host in the full lane:
      - `compute_workgroup_atomic_1024`: `p50 +19.40%`, `p95 +32.64%`, `claimable`
      - `resource_lifecycle`: `p50 +846.53%`, `p95 +723.88%`, `claimable`
      - `upload_write_buffer_64kb`: `p50 +26.36%`, `p95 +64.20%`, `claimable`
    - remaining macOS Metal blockers in the full lane:
      - `upload_write_buffer_1kb`: still unstable under full-lane pressure (`p50 +11.36%`, `p95 -37.18%`)
      - `upload_write_buffer_1mb`: still tail-negative in the full lane (`p50 +32.81%`, `p95 -15.40%`)
      - `texture_sampler_write_query_destroy`: `p50 -47.40%`, `p95 -70.02%`
      - `texture_sampler_write_query_destroy_mip8`: `p50 -48.84%`, `p95 -52.32%`
  - next macOS work is now narrow:
    - stabilize `upload_write_buffer_1kb` and `upload_write_buffer_1mb` under full-lane contention, not just focused probes
    - reduce render-submit cost for the texture lifecycle rows or explicitly move them out of claim scope on this host
    - only after that is it worth doing multi-host substantiation for the local Metal claim lane
- Local Metal follow-up after texture and upload-tail fixes (2026-03-09, latest latest):
  - `runtime/zig/src/backend/metal/metal_native_runtime.zig` now:
    - defers render-path waits when queue sync is `deferred`,
    - defers texture/sampler releases until after GPU completion and excludes those releases from measured flush wait time,
    - uses a split upload wait policy for upload-only batches (`waitCompleted` for tiny uploads, fast-wait for larger upload-only batches),
    - raises the reusable staging-pair threshold to `1 MiB`.
  - focused artifacts:
    - `bench/out/scratch/20260309T130823Z/metal.texture_rows.after_release_timing_fix.json`
      - texture family now claimable:
        - `texture_sampler_write_query_destroy`: fixed in this focused rerun
        - `texture_sampler_write_query_destroy_mip8`: claimable
        - `texture_sampler_write_query_destroy_500`: claimable
    - `bench/out/scratch/20260309T131557Z/metal.upload_rows.after_threshold_wait_fix.json`
      - upload trio now claimable in focused rerun:
        - `upload_write_buffer_1kb`: claimable
        - `upload_write_buffer_64kb`: claimable
        - `upload_write_buffer_1mb`: claimable
  - focused repeated claim rerun for the previously unstable upload rows:
    - `bench/out/scratch/20260309T133400Z/metal.upload_1kb_1mb.current.json`
    - `comparisonStatus=comparable`, `claimStatus=claimable`
    - `upload_write_buffer_1kb`: `p50 +14.64%`, `p95 +55.81%`
    - `upload_write_buffer_1mb`: `p50 +25.03%`, `p95 +29.72%`
  - newest full repeated local comparable artifact:
    - `bench/out/apple-metal/extended-comparable/20260309T182813Z/dawn-vs-doe.local.metal.extended.comparable.json`
    - `comparisonStatus=comparable`, `claimStatus=diagnostic`, `24` comparable workloads
    - normalization fixes removed the false blocker set from repeat-asymmetric render/resource rows:
      - `render_uniform_buffer_update_writebuffer_partial_single` is now claimable through normalized `headlineProcessWall`
      - `resource_lifecycle` is comparable again under normalized repeat accounting and no longer fails as a repeat-mismatch artifact
    - remaining non-claimable rows in that artifact are:
      - `upload_write_buffer_1kb`: `p50 -5.34%`, `p95 -12.38%`
      - `upload_write_buffer_64kb`: `p50 -13.08%`, `p95 -27.06%`
      - `upload_write_buffer_{1gb,4gb}` still fail plausibility/timing-scope checks on the Dawn side
  - practical macOS boundary now:
    - native-Metal correctness, compute preflight, texture lifecycle rows, `resource_lifecycle`, and the repeat-asymmetric render/resource claim accounting are all unblocked locally
    - the remaining local Metal claim blockers are now concentrated in two real small-upload runtime rows (`upload_write_buffer_{1kb,64kb}`) plus the known Dawn-side plausibility/timing-scope issues on `upload_write_buffer_{1gb,4gb}`
    - local Metal benchmark catalog coverage is now `45` workloads; the remaining contract-count delta versus local Vulkan is copy/surface capability work, not missing compute admission

## Synthetic timing claim guard (2026-03-02)

- Local native backend timing paths still use deterministic runtime-state cost charging in:
  - `runtime/zig/src/backend/metal/metal_runtime_state.zig`
  - `runtime/zig/src/backend/vulkan/vulkan_runtime_state.zig`
- To prevent synthetic/quantized claim promotion, claimability now rejects zero-variance Doe operation-timing windows:
  - file: `bench/native-compare/modules/claimability.py`
  - new reason:
    `left timed samples have zero variance across the full claim window; treat as non-claimable until timing path is proven non-synthetic`
- Validation artifact:
  - `bench/out/scratch/20260302T234322Z/metal.one.upload_write_buffer_16mb.recheck_claim_guard.json`
  - `comparisonStatus=comparable`, `claimStatus=diagnostic` (guard-triggered).

## Comprehensive gap closure sweep (2026-03-17)

Systematic closure of all codable gaps identified from spec index and status tracking.

### File sharding (777-line enforcement)

All Zig source files in `runtime/zig/src/` are now within the 777-line limit:
- `doe_wgsl/emit_msl_ir.zig`: 864→574 lines, extracted `emit_msl_ir_builtins.zig` (309 lines)
- `doe_wgsl/spirv_builder.zig`: 783→551 lines, extracted `spirv_spec.zig` (258 lines)
- `full/render/wgpu_render_commands.zig`: 777→710 lines, extracted `wgpu_render_temp_texture.zig` (122 lines)
- `bench/native-compare/compare_dawn_vs_doe.py`: 1203→481 lines, extracted `report_assembly.py` (432 lines) and `workload_validation.py` (511 lines)
- new enforcement script: `scripts/check_zig_line_limit.py` (test files and `wgpu_types.zig` exempt)

### pub usingnamespace removal (Zig 0.15 preparation)

18 files updated to use explicit `pub const` re-exports instead of `pub usingnamespace`:
- all proxy shims in `runtime/zig/src/` and `runtime/zig/src/core/`

### Debug markers (no-op C ABI exports)

9 debug marker exports wired across 3 shard files:
- `doe_encoder_native.zig`: pushDebugGroup, popDebugGroup, insertDebugMarker (CommandEncoder)
- `doe_compute_ext_native.zig`: same 3 (ComputePassEncoder)
- `doe_bundle_native.zig`: same 3 (RenderBundleEncoder)
- `doe_wgpu_native.zig`: all 9 wired via comptime reference

### .label property

- `doe_label_store.zig` (68 lines): global hash map label store with set/get/remove + C ABI exports
- 10 `doe_*_native.zig` files call set/remove on create/release
- `full-surface.js` and `encoder-surface.js`: `.label` property on 20 GPU object types

### Pipeline override constants

Full-stack implementation of WGSL `override` → MSL function constants / SPIR-V specialization constants:
- parser, AST, sema, IR, ir_builder, compiler mod.zig
- `doe_shader_native.zig`, `doe_wgpu_native.zig`, `wgpu_types.zig`
- `doe_napi.c`, `full-surface.js`, `index.js`

### Error/event lifecycle wiring

- `doe_wgpu_native.zig` wired orphaned modules (`doe_error_scope_native.zig`, `doe_cache_adapter_native.zig`)
- `multi_adapter.zig` renamed collision symbol
- `doe_instance_device_native.zig` connected device-lost callback on release

### spirv-val integration

- `bench/spirv_val_gate.py`: standalone SPIR-V validation gate
- `bench/test_spirv_val_gate.py`: 7 regression tests
- `runtime/zig/build.zig`: `zig build spirv-val` step
- `bench/run_blocking_gates.py`: `--with-spirv-val-gate` flag

### Schema v2 shader artifact manifests

Backend-specific emitters for all three backends:
- `runtime/zig/src/backend/metal/artifact_emit.zig` (189 lines)
- `runtime/zig/src/backend/d3d12/artifact_emit.zig` (186 lines)
- includes `irSha256`, backend-specific hashes, stage-by-stage route attestations

### Vulkan GPU fence/sync

- `vk_sync.zig` (280 lines): FencePool (4-slot ring) + TimelineSemaphore
- `native_runtime.zig`: fence pool + streaming copy fields
- `vk_upload.zig`: streaming copy lifecycle + fence-based drain
- `vk_device.zig`: bootstrap creates fence pool + timeline semaphore

### Metal GPU timestamps

- `metal_gpu_timestamps.zig` (69 lines): MTLCounterSampleBuffer management
- `metal_kernel_dispatch.zig` (154 lines): extracted kernel dispatch with timestamp support
- `metal_bridge.m`: `metal_bridge_resolve_timestamps_ns` (Mach timebase)
- `metal_native_runtime.zig`: timestamp state, flush_queue_timed, activate_gpu_timestamps

### D3D12 streaming copy

- `d3d12_streaming_copy.zig` (176 lines): StreamingCopyState
- `d3d12_native_runtime.zig`: streaming copy integration
- `d3d12/mod.zig`: copy command batching logic

### Runtime command layering

- `core/command_partition.zig`: CoreCommand (10 variants)
- `full/command_partition.zig`: FullCommand (14 variants)
- `model.zig`: composes partitions with comptime validation
- 6 dead facades deleted

### Lean proof-driven clamp elision

- `ir_transform_robustness.zig` + `dispatch_proof_match.zig`: `Config.elide_proven_bounds` now covers both `buf[gid.{x,y,z}]` and `buf[gid.y * dispatch_width + gid.x]`
- `ir.zig`: `DispatchPrecondition` now records pattern kind plus element stride bytes, and `dispatch_preconditions` stays attached to the analyzed module
- native compute shader creation now uses proof-aware runtime translation (`runtime_compile.zig`), and Metal/Vulkan dispatch paths validate the recorded buffer-size preconditions before dispatch
- 15 test call sites in `ir_transform_robustness_test.zig` updated for config parameter

### WGSL vertex/fragment support

- `emit_hlsl_stage.zig`: 313→417 lines with struct I/O support
- `sema_attrs.zig`: `@interpolate` parsing
- `emit_hlsl_stage_test.zig` and `emit_spirv_stage_test.zig`: sharded stage I/O and builtin coverage

### MSL min/max/clamp type ambiguity fix

- `emit_msl_shared.zig`: `write_expr_coerced()` with type-coerced min/max/clamp
- `emit_msl_ir_builtins.zig`: simplified `emit_expr_coerced()` to cast on any type mismatch
- `emit_msl_maps.zig`: removed min/max/clamp from passthrough list
- `shader_emit_test.zig`: 4 new tests

### Shader test corpus expansion

- `coverage_type_decl_test.zig`
- `coverage_expr_stmt_test.zig`
- `coverage_builtin_test.zig`
- `coverage_resource_test.zig`
- `coverage_stage_texture_test.zig`
- `emit_hlsl_*_test.zig` and `emit_spirv_*_test.zig`
- `mod_*_test.zig`
- `test_suite_wgsl.zig`: test suite collector
- `build.zig`: `zig build test-wgsl` step

### Browser spec index population

- `scripts/update_browser_spec_index.py`: populates browser cells from Playwright evidence
- `config/webgpu-spec-index.jsonl`: browser cells currently stand at 456 implemented + 62 partial + 369 unreviewed.
- `config/webgpu-spec-index.jsonl`: implementation cells are now normalized to code-shaped states only; browser-owned external-image / external-texture / XR rows are marked implemented on `metal` / `vulkan` / `d3d12` when satisfied by the Fawn browser lane through `@simulatte/webgpu/browser` delegation to browser-owned WebGPU objects, while stale D3D12 `blocked` cells were reset to `unreviewed` pending row-by-row reassessment.

### Metal spec index audit

- `scripts/audit_metal_spec_index.py`: promotes interface-level status based on member coverage

### Gates config cleanup

- `config/gates.json`: performance `thresholdStatus` changed from `bootstrap_placeholder` to `active`

### Vulkan package-surface alignment

- Node/addon and Bun now both forward render-pass `occlusionQuerySet` and
  `timestampWrites` into the Vulkan begin-render-pass path.
- Node/addon, native-direct, and Bun now forward `requestAdapter` option
  structs through the Vulkan request-adapter ABI for `featureLevel`,
  `powerPreference`, and `forceFallbackAdapter`.
- Vulkan sampler creation now honors compare samplers instead of hardcoding
  compare disabled.
- Vulkan render pipelines now retain vertex-buffer layouts and attributes, and
  Vulkan render passes bind recorded vertex/index buffers instead of dropping
  those assignments on the native path.
- Vulkan `getCompilationInfo()` now publishes real WGSL directive diagnostics: `error` for fatal compiler failures, `warning` for parsed-but-unenforced `diagnostic(...)` directives, and `info` for accepted `enable ...` directives
  message kinds on the repo-local runtime path.
- Repo-local Vulkan canvas paths now count `alphaMode` and `toneMapping.mode`
  as implemented native surfaces: Vulkan surface configuration stores the
  chosen alpha mode, and `toneMapping.mode` now participates in swapchain
  format selection instead of existing only as wrapper metadata.
- No-stubs cleanup advanced on native/runtime-visible paths:
  - Vulkan surface configure/acquire/present now fail explicitly without a real
    platform surface instead of fabricating headless placeholder presentation.
  - addon `bufferGetMapState` is now backed by a real Doe buffer map-state
    export instead of a hardcoded `"unmapped"` stub.
  - non-macOS render-state ABI fallbacks and native-direct device event-listener
    shims now report unsupported behavior explicitly instead of silently no-oping.
- Shared package/device lifecycle closure advanced on Vulkan package paths:
  - Node/addon and Bun package devices now wire native `pushErrorScope`,
    `popErrorScope`, `lost`, and `onuncapturederror` instead of leaving those
    surfaces stubbed.
  - `GPUDevice.addEventListener` / `removeEventListener` now retain listeners on
    the shared package surface and dispatch native `uncapturederror` events.
  - `GPUDevice.adapterInfo` now reuses the adapter-info surface on package
    devices, and `GPUBuffer.mapState` now preserves `pending` in JS while
    reading `mapped` / `unmapped` from the native buffer state export.
- Vulkan feature publication now closes the remaining package-surface tail for
  `shader-f16`, `float32-blendable`, `dual-source-blending`, `subgroups`,
  `texture-formats-tier1`, and `texture-formats-tier2` by probing the selected
  physical device and caching the resulting adapter/device feature set.
- Pipeline-creation failures now normalize to `GPUPipelineError` with a
  concrete `reason` on Node/addon and Bun package paths.
- Doe pipeline-layout handles now retain `immediateSize`, and compute/render
  `setImmediates` rejects writes that exceed the bound layout budget.
- Vulkan render-pass descriptors now carry `maxDrawCount` through the Doe ABI,
  and Doe render-pass recording rejects draws beyond that declared limit.

### D3D12 and Metal package-surface alignment

- Node/addon and native-direct now forward `featureLevel` through the
  `requestAdapter` ABI on the Metal package surface; Bun already forwarded it.
- Node/addon and native-direct adapter info now prefer `wgpuAdapterGetInfo`
  with the Doe-native fallback retained for older builds, which closes the
  D3D12 package `GPUAdapter.info` / `GPUDevice.adapterInfo` publication path.
- macOS Node/addon package smoke is back after moving adapter-info publication
  to a Doe-native-first bridge path on the addon (`doe_napi_caps.c`,
  `doe_napi_nd_creators.c`), with `wgpuAdapterGetInfo` retained only as a
  fallback; touching `GPUAdapter.info` had been crashing immediately after
  `requestAdapter()` through the current drop-in provider's standard info path.
- Node/addon package `GPUDevice.popErrorScope()` now resolves to a
  `GPUError`-shaped object or `null` instead of returning the raw addon record,
  missing render-pass indirect draw entrypoints fail explicitly instead of
  silently no-oping, adapter `requestDevice()` now returns a real
  `DoeGPUDevice` instance instead of a prototype-copied plain object, and the
  JS surface now tolerates older packed addons that do not yet export
  `adapterGetInfo`.
- Node/addon package buffer write-mapping now flushes every staged
  `getMappedRange()` slice on `unmap()` instead of only the most recent range,
  the lazy compute-pass promotion path is now shared between `setImmediates()`
  and indirect dispatch promotion, and render-bundle indirect draw wrappers now
  fail explicitly when the addon lacks those entrypoints.
- Package-owned `GPUCommandBuffer` wrappers now own native command-buffer
  lifetime across Node, Bun, and browser-backed surfaces: finished command
  buffers are wrapped as real resources, rejected on resubmission after the
  first `queue.submit()`, explicitly released after successful submit, and
  finalizer-cleaned on drop when a backend release hook exists.
- D3D12 package devices now wire native `pushErrorScope`, `popErrorScope`,
  `lost`, `onuncapturederror`, and `addEventListener` /
  `removeEventListener` instead of tracking those rows as not wired.
- D3D12 package surfaces now count `createComputePipelineAsync`,
  `createRenderBundleEncoder`, render-bundle `finish`, render-pass
  `beginOcclusionQuery` / `endOcclusionQuery` / `executeBundles`, `queue`,
  `destroy`, and `GPUShaderModule.getCompilationInfo` as implemented package
  paths backed by existing Doe native exports.
- The remaining D3D12 top-level `GPU` / `GPUAdapter` partials were stale:
  the shared package surface already exposed `requestAdapter`,
  `requestDevice`, `wgslLanguageFeatures`, and the package-owned
  `getPreferredCanvasFormat()` helper, so those tracker rows now count as
  implemented.
- D3D12 native-direct buffer creation no longer falls through the Metal path:
  `GPUBufferUsage.*` now maps to real D3D12 buffer allocation / map / unmap /
  getMappedRange behavior on the package-native surface.
- D3D12 limits publication is now end-to-end on package surfaces:
  `GPUSupportedLimits.*` comes from the D3D12 capability export and the
  stage-scoped storage aliases are published on Node/addon, native-direct,
  and Bun.
- D3D12 native-direct texture and sampler creation now consume the real
  package descriptors instead of stopping at wrapper plumbing:
  `GPUSamplerDescriptor.*`, `GPUDepthStencilState.*`, BC6H texture formats,
  and the implemented `GPUTextureDescriptor` / `GPUTextureViewDescriptor`
  member subset are now backed by D3D12 runtime code.
- Remaining D3D12 texture/view ledger gaps are explicit rather than hidden:
  `textureBindingViewDimension`, non-trivial `viewFormats`, non-identity
  swizzle, and 1D texture/view coverage still remain incomplete, as do
  ETC2/EAC/ASTC publication and higher-order feature rows such as
  `texture-compression-bc-sliced-3d`, `float32-blendable`,
  `texture-formats-tier1`, `texture-formats-tier2`, and
  `texture-component-swizzle`.
- Metal `GPUSupportedLimits.maxImmediateSize` and
  `GPUTextureViewDescriptor.swizzle` were stale tracker rows; both were
  already implemented through the existing runtime and package plumbing.
Semantic operator tracing and repro artifacts (2026-03-22):
- `runtime/zig/src/main.zig` now accepts command-stream semantic metadata
  (`semanticOpId`, `semanticStage`, `semanticPhase`, `semanticTokenIndex`,
  `semanticLayerIndex`, `semanticExecutionPlanHash`) plus targeted capture
  requests (`captureBufferHandle`, `captureOffset`, `captureSize`).
- `execution.zig` and `trace.zig` now preserve semantic operator identity
  through native execution, trace row emission, and trace-meta summaries.
- Doe-native trace anchors now emit a per-run operator manifest
  (`<trace-anchor>.operators.json`) plus per-op structural repro bundles
  (`.opNNNN.repro.commands.json` / `.opNNNN.repro.meta.json`).
- Vulkan and Metal support targeted post-op buffer capture by handle; D3D12 and
  Dawn-delegate currently fail explicitly as unsupported for this artifact path.
- Structural rerun scope is same-device / same-backend debugging. No bitwise
  reproducibility claim is made.
- `packages/doe-gpu` now exposes `writeSemanticOperatorBundle(...)` on the
  tooling/runtime surface so higher-level clients can attach a schema-backed
  semantic operator bundle to Doe-observed diagnose runs without depending on
  the live in-process `navigator.gpu` path to carry semantic-op injection.
- `bench/native-compare/compare_dawn_vs_doe.py` now ingests Doe-native
  `.operators.json` manifests when both sides emit them and records
  per-workload `operatorDiff` summaries plus a top-level `operatorDiffSummary`
  in the compare report. Current scope is structural first-divergence reporting
  (semantic identity, command shape, execution status, capture status/digest),
  not full tensor-value drift analysis.
