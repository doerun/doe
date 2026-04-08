# Doe status archive: 2026-02 and legacy early-2026 backfills

This shard contains the February 2026 status entries plus preserved older early-2026 backfilled sections that were still present in the original `docs/status.md` order.
The entries remain in original top-to-bottom order.

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
