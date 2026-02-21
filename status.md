# Fawn Status

## Snapshot

Date: 2026-02-21

Fawn is in active implementation phase. Runtime behavior is operational for dispatch decisions and replay-aware tracing, but several product and release-flow gaps remain before v1-grade stability claims.
The execution platform strategy is now explicitly: full native Zig+WebGPU/FFI runtime path, estimated at 2,800+ LOC for non-prototype delivery.
Current `fawn/zig/src` size is 2,750 LOC and now includes native queue-submitted execution for upload, copy, barrier, and dispatch-family lowering.
AMD Vulkan comparison presets now include claimable comparable slices (local + release policies) and explicit non-claimable directional slices.

## Product implementation state (runtime outcomes)

### Implemented

1. v0 runtime prototype in `fawn/zig/src`:
- typed model and JSON ingestion
- deterministic matcher + selector + action application
- runnable `fawn-zig-runtime` entry path
- dispatch/trace/replay now work; execution remains simulator-oriented
2. Lean contract sources in `fawn/lean/Fawn` (`Model.lean`, `Dispatch.lean`).
- runtime command stream parser in `fawn/zig/src/command_json.zig`
- lean runtime selection module in `fawn/lean/Fawn/Runtime.lean`.
3. Lean bridge gate evaluator in `fawn/lean/Fawn/Bridge.lean`.
4. Zig runtime dispatch now includes explicit Lean obligation metadata (`requiresLean`, `isBlocking`, `verification_mode`, `proof_level`) in trace output.
5. Zig parser/dispatch runtime now includes:
- command aliases for replay input and kernel name alias handling
- case-insensitive command/quirk parsing for stable config use
- fail-fast action payload validation for toggle/use-temporary-buffer fields
- trace enrichment with matched `scope`, `safetyClass`, and toggle payload for matched quirks.
6. Lean runtime dispatch now includes driver-range matching, proof-priority tie-break support, and `Runtime.DispatchDecision` to mirror Zig trace metadata.
7. Trace contract hardened with deterministic row hash-chain fields (`traceVersion`, `module`, `opCode`, `hash`, `previousHash`) and a companion parity comparator.
8. Run-level Zig trace summary emission implemented via `--trace-meta`, including deterministic session-level `seqMax`, row counts, and terminal hash-chain anchors for fast replay validation.
9. Release replay hard-gate now exists as `fawn/bench/trace_gate.py`, validating `trace-meta` + `trace-jsonl` from comparison report samples.

### Missing for full product confidence (runtime + validation quality)

1. Full semantic replay parity between runtime implementations (e.g., Zig vs Lean oracle) is still not implemented end-to-end.
2. Replay validation path is implemented in `trace_gate.py`, but Rust/CI-native parity checker integration remains pending.
3. Real measured GPU benchmark timing path is partially operational for `compare_dawn_vs_fawn.py`; full matrix/substantiation and trend reporting remain open.
4. Baseline dataset generation for Dawn/wgpu comparisons.
5. Comprehensive quirk coverage from upstream mining for full production confidence.
6. Real backend execution against GPU devices (current path includes queue-submission for upload/copy/barrier and dispatch-family compute lowering in `src/webgpu_ffi.zig`).
- `fawn/zig/src` now has queue-submission execution for all implemented command classes in `src/webgpu_ffi.zig`.
- Dispatch/kernel routes now use native compute pipeline lowering with fallback WGSL for missing kernel payloads.
- Planned full native execution path (non-prototype): estimated 2,800+ LOC across command adapter, resource scheduling, IR lowering, and deterministic retry policy.

### Non-prototype execution backlog (full native)

Acceptance required before production claims:
- confirm dispatch/kernel lowering path is deterministic for native kernel payloads
- backend selection and submission failures are deterministic and actionable
- deterministic execution timing captured from real backend execution spans

Planned implementation slices:
1. `src/webgpu_ffi.zig` loader contract and typed handle wrappers.
2. `src/webgpu_runtime.zig` (new) for instance, adapter, device, and queue lifecycle.
3. `src/command_ir.zig` (new) for canonical IR and replayable command serialization.
4. `src/resource_pool.zig` (new) for buffers, textures, pipelines, and staging aliases.
5. `src/command_encoder.zig` (new) for upload/copy/barrier/dispatch translation.
6. `src/execution.zig` native scheduler integration and status taxonomy.
7. `src/main.zig` release execution defaults and replay-linked hard failure mode.
8. parity harness updates for execution results and benchmark artifacts.

Estimated remaining effort: 2,800+ LOC before performance hardening.

## Developer flow state (engineering, governance, and release pipeline)

### Implemented

1. Canonical docs (`thesis`, `architecture`, `process`, `upgrade-policy`).
2. Config surface in `fawn/config/`.
3. Module scaffolds in:
- `fawn/agent/`
- `fawn/lean/`
- `fawn/zig/`
- `fawn/bench/`
- `fawn/trace/`
4. End-to-end worked example in `fawn/examples/`.
5. Baseline benchmark policy and run-metadata contract.
6. Self-contained scaffold scripts:
- `fawn/bench/run_bench.py`
- `fawn/bench/check_correctness.py`
- `fawn/trace/replay.py`
7. Added Dawn/Fawn benchmark orchestration scaffolding via `fawn/bench/compare_dawn_vs_fawn.py` and `fawn/bench/workloads.json` for repeatable shared-workload runtime comparisons.
8. Added Zig replay comparison mode in `zig/src/main.zig` (`--replay`) that now enforces `seq`, `command`, optional `kernel`, module/op-code, and hash-chain alignment.
9. Added hard release gate command path in docs/process via `fawn/bench/trace_gate.py` for replay artifact validation.
10. Release gating is explicit in process/docs and enforced in `.github/workflows/release-gates.yml`.
11. Strict Dawn-vs-Fawn upload comparability preflight is now enforced in `fawn/bench/compare_dawn_vs_fawn.py`:
- fail fast if executed `fawn-zig-runtime` does not expose upload knobs (`--upload-buffer-usage`, `--upload-submit-every`)
- fail fast if upload knob validation probes are not recognized
- fail fast if runtime binary appears older than key upload/runtime Zig sources (`zig/src/main.zig`, `zig/src/execution.zig`, `zig/src/wgpu_commands.zig`, `zig/src/webgpu_ffi.zig`)
12. AMD Vulkan upload workloads in `fawn/bench/workloads.amd.vulkan.json` now use explicit size-tuned `leftUploadSubmitEvery` values (instead of a single shared cadence) to keep methodology explicit while reducing upload backpressure artifacts.
13. Comparison delta sign convention is now left-runtime perspective with right baseline (`((rightMs-leftMs)/rightMs)*100`), so positive means left faster and negative means left slower (`compare_dawn_vs_fawn.py` and `compare_runtimes.py`, report `deltaPercentConvention`).
14. Comparison report schema is now `schemaVersion: 3` with percentile summaries centered on p5/p50/p95/p99 (`p5Ms`, `p5Percent`, and overall `p5Approx`/`p50Approx`/`p95Approx`/`p99Approx`).
15. Post-benchmark visualization pipeline step is now available via `fawn/bench/visualize_dawn_vs_fawn.py`, producing a self-contained HTML report and optional analysis JSON from Dawn-vs-Fawn comparison artifacts.
16. Visualization/distribution diagnostics now include ECDF overlays, workload×percentile heatmap, KS statistic with asymptotic p-value, Wasserstein distance, probability of superiority (`P(left<right)`), and bootstrap CI summaries for delta `p50`/`p95`/`p99`.
17. Claimability reliability mode is now implemented in `fawn/bench/compare_dawn_vs_fawn.py`:
- `--claimability local|release` enforces sample-floor and positive-tail checks
- report now includes workload-level `claimability`, top-level `claimabilityPolicy`, `claimabilitySummary`, and `claimStatus`
- claimability failures exit non-zero (`rc=3`) so CI/pipelines can gate on claimable speed
18. Upload ignore-first timing source is now explicit and scope-consistent in reports (`fawn-execution-row-total-ns+ignore-first-ops`) instead of inheriting incompatible base sources.
19. Runtime upload prewarm path is now wired in Zig native execution (`maxUploadBytes` prewarm before timed command loop) to reduce first-upload setup spikes.
20. AMD Vulkan 64KB upload workload now uses size-specific repeat normalization (`leftCommandRepeat=500`, `leftTimingDivisor=500`, `leftIgnoreFirstOps=0`) for more stable per-op claim diagnostics.
21. Comparability assessment now enforces workload contract comparability flags (`workload.comparable`); workloads marked non-comparable are always reported as non-comparable and strict mode fails fast when they are selected.
22. `shader_compile_pipeline_stress` has been promoted to a comparable contract for AMD Vulkan using a fixed `ShaderRobustnessPerf` filter plus explicit 50-dispatch normalization (`leftTimingDivisor=50`) and Dawn-aligned kernel command shape.
23. Directional render/texture workloads now use explicit per-iteration normalization controls (`leftTimingDivisor`/`leftCommandRepeat`) to reduce unit mismatches during diagnostic runs while remaining non-claimable.
24. AMD Vulkan matrix coverage now has config-first presets for release claims, extended comparable runs, and directional diagnostics:
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json`
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json`
- `bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json`
- `bench/workloads.amd.vulkan.extended.json`
- `bench/dawn_workload_map.amd.extended.json`
25. Native render-pass draw coverage now exists in Zig runtime via `render_draw` command:
- command parser + model + runtime dispatch now accept `render_draw|draw|draw_call`
- native backend lowers `render_draw` into real render-pass draw submission (not compute proxy)
- benchmark draw workload command seed now uses `examples/draw_call_proxy_commands.json` `render_draw` contract
26. Directional render workload config/docs were updated to reflect native draw-path semantics while remaining non-claimable by contract.
27. Directional texture/raster command seed now uses real compute texture sampling plus a simplified native `render_draw` pass (instead of `dispatch_workgroups` raster proxy), while staying non-comparable by contract.
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
- `.github/workflows/release-gates.yml` now runs both `bench/trace_gate.py` and `bench/claim_gate.py` as blocking gates on the report artifact.
36. Native runtime now exposes explicit queue wait behavior control:
- `--queue-wait-mode process-events|wait-any` in `fawn-zig-runtime`
- default remains `process-events`; `wait-any` is available for targeted wait-path diagnostics/tuning and auto-falls back to `process-events` when timeout-based wait-any is unsupported by the backend.
37. AMD Vulkan 64KB upload workload cadence is retuned from `leftUploadSubmitEvery=50` to `leftUploadSubmitEvery=100` (with `leftCommandRepeat=500`, `leftTimingDivisor=500`) in:
- `bench/workloads.amd.vulkan.json`
- `bench/workloads.amd.vulkan.extended.json`
- local operation-scope A/B artifact: `bench/out/upload_64kb_submit_wait_100_vs_50.local.json` (`executionSubmitWaitTotalNs`, `n=30` per side): `submit100` faster at `p50 +19.52%`, `p95 +14.21%`.

### Missing in progress

1. Full upstream quirk mining automation.
2. Lean theorem packs with CI proof execution.
3. External CI workflow wiring for mandatory release gate invocation.
4. Full benchmark harness with measured GPU timings tied to native execution spans.
5. Baseline dataset generation and end-to-end comparison automation against Dawn/wgpu incumbents.
6. Native Zig/WebGPU/FFI execution backend in Zig (estimated 2,800+ LOC, hard runtime milestone).
7. Repeated strict release claim-mode rechecks for 64KB cadence retune are pending on an AMD Vulkan host (current host currently exposes CPU adapters only for Dawn adapter preflight).
8. Render/texture domains remain directional: native `render_draw` command coverage is now present (including texture workload render-step usage), but workload methodology is still simplified versus Dawn benchmark semantics.

## Performance Reliability Investigation (2026-02-21)

Scope:
- AMD Vulkan upload workloads, with focus on `buffer_upload_64kb`.
- strict comparability mode remained green during these checks.

Findings:
1. `buffer_upload_64kb` is highly sensitive to methodology knobs (`leftIgnoreFirstOps`, `leftUploadSubmitEvery`, `leftCommandRepeat`) even when comparability checks pass.
2. Mixed timing semantics can produce misleading conclusions:
- dispatch-window timing excludes setup cost
- ignore-first adjustment based on per-row durations includes setup for included rows
- this combination can materially change sign and tails (now guarded by explicit row-total ignore-first timing source in harness output).
3. Diagnostic sweep showed that increasing `leftCommandRepeat` (with explicit per-op normalization) substantially improved 64KB tail behavior and median delta, indicating batching/setup sensitivity dominates this case.

Implication:
- 64KB methodology hardening is now enforced in harness claim mode; runtime smoothing is still needed before robustly claimable "reliably faster" status.

Next required changes:
1. Re-run strict release claim-mode windows on AMD Vulkan host for `buffer_upload_64kb` with the updated `leftUploadSubmitEvery=100` contract.
2. Keep queue wait path tuning explicit (`--queue-wait-mode`) and only promote non-default mode into workload contracts after adapter-backed reliability evidence.
3. Re-freeze workload config defaults only after invariants hold in repeated strict claim-mode runs.

## Render parity benchmark note (2026-02-21)

Local directional benchmark (same host runtime, no Dawn adapter dependency):

- report: `bench/out/render_draw_vs_compute_proxy.local.json`
- tool: `python3 bench/compare_runtimes.py`
- comparison: `left=fawn_render_draw` vs `right=fawn_compute_proxy` (`2000` operations normalized per run)
- result: `p50DeltaPercent=-129.93%` (native render path remains slower than prior compute draw proxy in this environment after adding Dawn-like vertex-buffer + static uniform bind-group parity)

Interpretation:
- this is an expected early parity milestone signal, not a claim benchmark.
- setup amortization still exists for multi-command runs (pipeline + view caches + vertex buffer + bind-group reuse), but render-vs-proxy single-command runs remain dominated by render submit cost.
- latest run shows directional tail improvement (p95 delta from `-143.43%` to `-112.85%`) while remaining non-claim diagnostic.

## Texture directional benchmark note (2026-02-21)

Local directional benchmark comparing the updated texture/raster command seed against the prior dispatch-only raster proxy:

- report: `bench/out/texture_raster_render_step_vs_dispatch_proxy.local.json`
- tool: `python3 bench/compare_runtimes.py`
- comparison: `left=fawn_texture_raster_render_step` vs `right=fawn_texture_raster_dispatch_proxy`
- result: `p50DeltaPercent=-22.38%` (updated texture path is currently slower in this host environment)

Interpretation:
- this confirms the new texture command seed exercises real `kernel_dispatch + render_draw` behavior.
- remaining gap is expected while directional texture methodology is still simplified versus Dawn's full render-pass transitions.

## AMD Vulkan run snapshot (2026-02-21)

Executed preset reports:

1. `bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json`
- report: `bench/out/dawn-vs-fawn.amd.vulkan.extended.comparable.json`
- `comparisonStatus=comparable`, `claimStatus=claimable`
- comparable workloads: `8/8` (`nonComparableCount=0`)
- claimability mode: `local` (`minTimedSamples=7`), `nonClaimableCount=0`
- p50 deltas (left=fawn vs right=dawn): `buffer_upload_1kb +27.39%`, `buffer_upload_64kb +40.30%`, `buffer_upload_1mb +36.37%`, `buffer_upload_4mb +32.68%`, `buffer_upload_16mb +36.74%`, `workgroup_atomic_1024 +10.50%`, `workgroup_non_atomic_1024 +11.81%`, `shader_compile_pipeline_stress +8.81%`

2. `bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json`
- report: `bench/out/dawn-vs-fawn.amd.vulkan.release.json`
- `comparisonStatus=comparable`, `claimStatus=claimable`
- comparable workloads: `7/7` (`nonComparableCount=0`)
- claimability mode: `release` (`minTimedSamples=15`), `nonClaimableCount=0`
- p50 deltas (left=fawn vs right=dawn): `buffer_upload_1kb +22.76%`, `buffer_upload_64kb +45.01%`, `buffer_upload_1mb +36.42%`, `buffer_upload_4mb +35.17%`, `buffer_upload_16mb +36.93%`, `workgroup_atomic_1024 +11.57%`, `workgroup_non_atomic_1024 +11.56%`

3. `bench/compare_dawn_vs_fawn.config.amd.vulkan.directional.json`
- report: `bench/out/dawn-vs-fawn.amd.vulkan.directional.json`
- `comparisonStatus=unreliable`, `claimStatus=not-evaluated`
- non-comparable workloads: `2/2` by contract (`render_draw_throughput_proxy`, `texture_sampling_raster_proxy`)

Replay gate verification:
- `python3 bench/trace_gate.py --report bench/out/dawn-vs-fawn.amd.vulkan.extended.comparable.json` -> `PASS` (`112` trace samples)
- `python3 bench/trace_gate.py --report bench/out/dawn-vs-fawn.amd.vulkan.release.json` -> `PASS` (`210` trace samples)
- `python3 bench/trace_gate.py --report bench/out/dawn-vs-fawn.amd.vulkan.directional.json` -> `PASS` (`28` trace samples)

## Native execution milestone (non-prototype)

Scope:
- chosen path is full native Zig+WebGPU/FFI implementation from scratch.
- expected size is 2,800+ LOC before performance/perf-hardening work.
- current codebase status: trace/replay/matching complete, with queue-submit execution coverage for upload/copy/barrier and dispatch-family compute routing.

Execution gap list:
- typed discovery and adapter/device queue selection are implemented in WebGPU FFI bootstrap.
- full dispatch/kernel lowering with shader/module/pipeline resolution for a complete kernel payload format and artifact-backed verification.
- texture copy/materialization command modeling and lowering.
- no deterministic GPU timing capture in the execution path.
- robust retry/failure policy for GPU submission errors and mapped GPU status.
- no release-ready benchmark baseline generated against native GPU backend.

### Explicit distinction

- “Not implemented” in developer flow does not mean the runtime is unusable.
- It means release confidence, automation, and proof-binary reproducibility are not yet at stable v1-grade completeness.

## v0 Reality

Blocking gates: schema, correctness, trace.
Advisory gates: verification, performance.

This matches speed-first priorities while keeping deterministic foundations.

Current comparison claim state: `directional`.

Meaning:
1. measured, replay-validated AMD Vulkan comparable reports now include claimable local/release slices
2. directional render/texture slices remain explicitly non-comparable and non-claimable by contract
3. no broad substantiated "beats Dawn/wgpu" claim is allowed yet without wider baseline coverage and trend windows
