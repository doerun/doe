# Config Migration Notes

## 2026-03-06

### Benchmark cube reporting contracts

- Added benchmark cube reporting contracts for cross-surface evidence aggregation:
  - `config/benchmark-cube-policy.schema.json` + `config/benchmark-cube-policy.json`
  - `config/benchmark-cube-row.schema.json`
  - `config/benchmark-cube.schema.json`
- `config/schema-targets.json` now validates `config/benchmark-cube-policy.json`
  through schema gate like other canonical config contracts.
- The benchmark cube introduces explicit cross-surface reporting dimensions:
  - host profile
  - surface (`backend_native`, `node_package`, `bun_package`)
  - provider pair
  - workload set
  - maturity / missing-cell status
- Initial policy position is explicit:
  - backend compare reports remain the canonical claim lane
  - Node is the primary supported package surface
  - Bun remains prototype until a real compare lane populates those cells
- Initial artifact builder is `bench/build_benchmark_cube.py`, which emits:
  - `bench/out/cube/<timestamp>/cube.rows.json`
  - `bench/out/cube/<timestamp>/cube.summary.json`
  - `bench/out/cube/<timestamp>/cube.matrix.md`
  - `bench/out/cube/<timestamp>/cube.dashboard.html`
  - stable latest mirrors under `bench/out/cube/latest/`
- Existing historical backend reports are now merged into cube rows even when they
  no longer satisfy current conformance contracts:
  - such rows are tagged `sourceConformance=legacy_nonconformant`
  - cube cells degrade them to `diagnostic` instead of dropping them or treating
    them as canonical claim evidence

## 2026-03-05

### Quirk-mining manifest: toggleContext and toggleContextCounts

- `config/quirk-mining-manifest.schema.json` adds two new optional fields:
  - `toggleContextCounts` (top-level): object mapping context token → hit count.
  - `toggleHits[].toggleContext` (per-hit): context token for how the toggle was observed.
- Toggle context tokens: `reference`, `default_on`, `default_off`, `force_on`, `force_off`.
- `agent/mine_upstream_quirks.py` now recognizes context-aware patterns:
  - `->Default(Toggle::X, true/false)` → `default_on` / `default_off`
  - `->ForceSet(Toggle::X, true/false)` → `force_on` / `force_off`
  - `->ForceEnable(Toggle::X)` → `force_on`
  - `->ForceDisable(Toggle::X)` → `force_off`
  - bare `Toggle::X` references not matched by the above → `reference`
- Quirk records themselves are unchanged; context metadata lives in the manifest only.
- Updated `examples/quirk-mining.manifest.sample.json` to include `toggleContextCounts`
  and `toggleContext` in sample `toggleHits` entries.

### Lean model: String.trim compatibility fix

- `lean/Fawn/Model.lean`: replaced `text.trimAscii.toString` with `text.trim` for
  compatibility with the pinned Lean toolchain (4.16.0), where `String.trimAscii`
  is not available. Semantic behavior is identical for version-string parsing.

### Lean fixtures: Doe-vs-Doe parity obligation fields

- `lean/Fawn/ComparabilityFixtures.lean`: added missing `ComparabilityFacts` fields
  introduced in 2026-02-26 (Doe-vs-Doe timing-scope parity obligations):
  - `traceMetaSourceMatchApplies` / `leftRightTraceMetaSourceMatch`
  - `timingSelectionPolicyMatchApplies` / `leftRightTimingSelectionPolicyMatch`
  - `queueSyncModeMatchApplies` / `leftRightQueueSyncModeMatch`
  - `executionShapeMatchApplies` / `leftRightExecutionShapeMatch`
- `lean/check.sh` now passes cleanly with the pinned 4.16.0 toolchain.

### Apple Metal quirks and CI

- Added `examples/quirks/apple_m3_noop_list.json`: empty quirk list for Apple M3 Metal
  benchmark runs (analogous to `amd_radv_noop_list.json` for Vulkan).
- Updated `bench/workloads.local.metal.extended.json`: all 43 workload quirksPath entries
  changed from `amd_radv_noop_list.json` to `apple_m3_noop_list.json`.
- Added `.github/workflows/lean-check.yml`: CI workflow that installs elan and runs
  `lean/check.sh` on every push/PR, making Lean typecheck a CI gate on macOS runners.

### Metal benchmark — third run (2026-03-05)

- Third comparable run with updated config (iterations=20, minTimedSamples=19): 3/23 claimable.
- Claimable: `upload_write_buffer_4mb` (+4.20% p50, up from +0.68% in Run 2), `render_draw_redundant_pipeline_bindings` (+0.25% p50, stable), `compute_concurrent_execution_single` (+0.18% p50).
- Render workload characterization confirmed: all render encode timings cluster at 60–61µs for 2000 draws. The reported −1.5% to −3% is a 1µs CPU timer quantization artifact. Both sides call Dawn's `wgpuRenderPassEncoderDraw`; sub-quantization difference is system-state noise.
- Blend/stencil setup optimization (`wgpu_render_commands.zig`: skip `set_blend_constant` when (0,0,0,0), skip `set_stencil_reference` when 0) is in the setup phase — outside the encode timing window — so it has no measurable effect on reported encode time.
- Upload outliers (1MB occasional 0.352ms, render_uniform_buffer occasional 0.614ms) are GPU scheduling latency events, not Doe code regressions.
- Config change: iterations 12→20, minTimedSamples 11→19.

### Metal benchmark — second run (2026-03-05)

- Second full comparable run with current config: 6/23 claimable (up from 5/23 in Run 1).
- New claimable in Run 2: `upload_write_buffer_1kb` (+0.85% p50), `upload_write_buffer_64kb`
  (+0.40% p50), `upload_write_buffer_1gb` (+2.27% p50), `render_draw_redundant_pipeline_bindings`
  (+0.25% p50), `render_bundle_dynamic_pipeline_bindings` (+0.88% p50).
- Per-operation timing analysis for 1KB/64KB: ~97.5% of execution time is Metal
  command-buffer submit+wait. Doe Metal has tighter latency distribution (spread=0.005ms)
  than the Dawn Metal delegate (spread=0.029ms at 64KB); p50 near parity, p95 consistently
  positive. Sign flips between runs are system-state noise, not a methodology gap.
- No schema changes in this run; artifact contracts and workload contract unchanged.

## 2026-03-04

### Render-domain timing policy alignment

- Strict Dawn-vs-Doe render-family timing policy now treats render encoding as the comparable operation scope for both `render` and `render-bundle` domains.
- `config/backend-timing-policy.json` changes:
  - `domains.render.allowedTimingSources` now includes `doe-execution-encode-ns`.
  - new `domains.render-bundle` policy was added (same required timing class/sync model and source allowlist structure as `render`).
- Compare-harness policy alignment:
  - strict comparability expects Doe-side `doe-execution-encode-ns` with `timingSelectionPolicy=render-encode-preferred` for `render`/`render-bundle`.
  - upload row-total policy remains unchanged.

## 2026-03-03

### Drop-in strict ownership contract simplification

- Migrated drop-in symbol ownership contract to schema version `2`:
  - removed `requiredInStrict` from symbol entries.
  - strict no-fallback is now policy-wide and does not depend on per-symbol strict flags.
  - optional compatibility mode remains explicit through `dropin-abi-behavior.json` (`strictFallbackForbidden=false`).
- Updated files:
  - `config/dropin-symbol-ownership.schema.json`
  - `config/dropin-symbol-ownership.json`
  - `zig/src/config/dropin-symbol-ownership.json`
- Runtime parser now enforces `schemaVersion == 2` in:
  - `zig/src/dropin/dropin_symbol_ownership.zig`

### No-op execution placeholder retirement

- Removed embedded no-op kernel fallback routing from active WebGPU command execution paths.
- `dispatch`/`dispatch_indirect` now fail explicitly unless executed through explicit `kernel_dispatch` contracts.
- Vulkan native dispatch no longer auto-builds a default no-op compute pipeline; dispatch now requires an explicit loaded kernel pipeline.

### Backend lane fallback policy clarification

- Backend lane selection remains strict-only by contract:
  - `allowFallback` is schema-constrained to `false`.
  - `strictNoFallback` is schema-constrained to `true`.
- Runtime backend init continues to fail fast without delegate fallback branches in active backend routing.

## 2026-03-02

### Strict Dawn-vs-Doe normalization contract hardening

- Comparable workload timing divisors were migrated to direct operation timing for Dawn-vs-Doe strict runs:
  - `leftTimingDivisor=1.0`
  - `rightTimingDivisor=1.0`
- Updated workload catalogs under `bench/workloads*.json` accordingly for comparable workloads.
- `bench/compare_dawn_vs_doe.py` now fails fast in strict operation mode if a comparable
  Dawn-vs-Doe workload config attempts side-specific divisor scaling.

### Benchmark workload ID contract migration (status-free IDs)

- Migrated benchmark workload IDs away from lifecycle/status prefixes (`par_`, `exp_`, `ctr_`)
  and maturity tokens (`contract`, `proxy`, `macro`).
- New benchmark ID contract is now stable, domain-first, and shape-oriented:
  `domain_subject_shape_variant`.
- Workload IDs are immutable contract keys:
  - do not rename IDs when promoting directional workloads to comparable/claim lanes.
  - encode comparability/claim methodology in workload metadata (`comparable`, `benchmarkClass`,
    `comparabilityCandidate`, normalization fields), not in ID text.
- Updated all benchmark workload references and maps to the new ID set across:
  - `bench/workloads*.json`
  - Dawn workload maps/autodiscovery
  - compare configs and claim-cycle contracts
  - benchmark/docs/status references

### Runtime command contract expansion for benchmark semantics

- Added first-class runtime command kinds for explicit workload semantics:
  - `dispatch_indirect`
  - `draw_indirect`
  - `draw_indexed_indirect`
  - `render_pass`
- Updated Zig model/parser/runtime/backend routing to treat these as explicit command
  kinds rather than alias-only labels.
- Updated benchmark command fixtures for indirect/RenderPass-named workloads to use
  matching command kinds directly.

### D3D12 backend lane and contract expansion

- Added first-class Doe D3D12 backend identity `doe_d3d12` to backend contract schemas and policy surfaces:
  - `config/backend-runtime-policy.schema.json`
  - `config/backend-cutover-policy.schema.json`
  - `config/backend-capability-policy.schema.json`
  - `config/backend-lane-map.schema.json`
  - `config/shader-artifact.schema.json`
- Added D3D12 runtime lanes to `config/backend-runtime-policy.json`:
  - `d3d12_doe_app`
  - `d3d12_doe_directional`
  - `d3d12_doe_comparable`
  - `d3d12_doe_release`
  - `d3d12_dawn_release`
- Updated generated lane map artifact `config/backend-lane-map.json` to include D3D12 lane-to-backend and backend-to-lane mappings.
- Added D3D12 backend capability policy entry in `config/backend-capability-policy.json`.
- Extended drop-in behavior contracts to understand strict D3D12 ownership mode and D3D12 lane routing:
  - `config/dropin-abi-behavior.schema.json`
  - `config/dropin-abi-behavior.json`
  - `config/dropin-symbol-ownership.schema.json`

## 2026-02-26

### Metal execution lane control and trace telemetry

- `doe-zig-runtime` now supports explicit backend-lane selection via `--backend-lane`:
  - `vulkan_dawn_release`
  - `vulkan_doe_app`
  - `metal_doe_directional`
  - `metal_doe_comparable`
  - `metal_doe_release`
  - `vulkan_dawn_directional`
  - `vulkan_doe_comparable`
  - `vulkan_doe_release`
  - `metal_doe_app`
- Native execution uses the backend runtime selection pipeline through lane resolution; this metadata is now emitted through execution summaries and trace metadata when `--trace-meta` is requested.
  - `backendLane`
  - `backendSelectionReason`
  - `fallbackUsed`
  - `selectionPolicyHash`
  - `shaderArtifactManifestPath`
  - `shaderArtifactManifestHash`
- `zig/src/backend/backend_runtime.zig` now loads lane policy from `config/backend-runtime-policy.json` at runtime (`schemaVersion=1`, `selectionPolicyHashSeed`, lane `defaultBackend`/`allowFallback`/`strictNoFallback`).
  - missing/invalid policy contract entries now fail fast during runtime initialization (no implicit compile-time lane fallback in this path).
- `bench/schema_gate.py` is now driven from `config/schema-targets.json` instead of a hardcoded target list.
- Added local Metal compare preset configs to run comparable, directional, and release lanes against Dawn via Metal autodescovery:
  - `bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json`
  - `bench/compare_dawn_vs_doe.config.local.metal.directional.json`
  - `bench/compare_dawn_vs_doe.config.local.metal.release.json`

### Metal app-lane cutover closure

- `config/backend-cutover-policy.json` now sets `targetLane` to `metal_doe_app` and `defaultBackend` to `doe_metal` for the app lane cutover path.
- `config/backend-runtime-policy.json` keeps `metal_doe_app` as strict (`allowFallback=false`, `strictNoFallback=true`) and now enforces strict no-fallback across every lane.
- `zig/src/execution.zig` now routes implicit Metal profile lane selection to `metal_doe_app` by default.
- Metal strict gate execution now supports cutover validation by passing `metal_doe_app` as `--local-metal-lane` where required and using release-cycle enforcement (`cycle_gate.py` with rollback criteria enabled).
- rollback switching is retired from runtime backend selection; incident response uses explicit lane policy/config changes with auditable artifacts.

### Backend/runtime contract expansion and strict-lane hardening

- Added backend contracts:
  - `config/backend-runtime-policy.schema.json` + `config/backend-runtime-policy.json`
  - `config/backend-capability-policy.schema.json` + `config/backend-capability-policy.json`
  - `config/backend-timing-policy.schema.json` + `config/backend-timing-policy.json`
  - `config/backend-cutover-policy.schema.json` + `config/backend-cutover-policy.json`
- Added shader contracts:
  - `config/shader-toolchain.schema.json` + `config/shader-toolchain.json`
  - `config/shader-error-taxonomy.schema.json` + `config/shader-error-taxonomy.json`
  - `config/shader-artifact.schema.json`
- Added drop-in ownership contracts:
  - `config/dropin-abi-behavior.schema.json` + `config/dropin-abi-behavior.json`
  - `config/dropin-symbol-ownership.schema.json` + `config/dropin-symbol-ownership.json`
- Added local-Metal hardening gates and helper modules:
  - `bench/backend_selection_gate.py`
  - `bench/shader_artifact_gate.py`
  - `bench/metal_sync_conformance.py`
  - `bench/metal_timing_policy_gate.py`
  - `bench/preflight_metal_host.py`
  - `bench/dropin_proc_resolution_tests.py`
  - `bench/compare_dawn_vs_doe_modules/backend_contract.py`
  - `bench/compare_dawn_vs_doe_modules/shader_contract.py`
  - `bench/compare_dawn_vs_doe_modules/metal_sync_contract.py`
- `config/benchmark-methodology-thresholds.schema.json` + `config/benchmark-methodology-thresholds.json` now include reliability policy fields:
  - positive-tail percentile sets for local/release lanes
  - flake budget
  - retry policy taxonomy
- `config/toolchains.json` now records shader toolchain contract identity (`toolchains["shaderMetal"].contract`).

## 2026-02-25

### Indexed P0 render comparability promotion

- `bench/vendor/dawn/src/dawn/tests/perf_tests/DrawCallPerf.cpp` now includes an
  indexed draw variant (`DynamicVertexBuffer_DrawIndexed`) in Dawn perf coverage.
- `bench/workloads.amd.vulkan.extended.json` restores
  `render_multidraw_indexed` to strict comparable:
  - `comparable=true`
  - `benchmarkClass=comparable`
  - `applesToApplesVetted=true`
- Dawn filter contracts now map indexed workloads to the indexed variant:
  - `bench/dawn_workload_map.amd.extended.json`
  - `bench/dawn_benchmark_adapter.py` autodiscovery patterns (`DynamicVertexBuffer_DrawIndexed`)
- strict apples-to-apples lanes now run indexed-vs-indexed for this contract.

### Directional comparability-candidate cohort contract

- `bench/workloads.amd.vulkan.extended.json` now supports optional workload field
  `comparabilityCandidate`:
  - `enabled` (bool)
  - `tier` (string)
  - `notes` (string)
- this field marks directional workloads that are isolated as likely parity-promotion
  targets; it does not change strict comparability status by itself.
- `bench/compare_dawn_vs_doe.py` now supports:
  - CLI: `--workload-cohort all|comparability-candidates`
  - config: `run.workloadCohort`
- cohort `comparability-candidates` is fail-fast gated to directional lanes and
  requires `includeNoncomparableWorkloads=true`.
- reports now record both:
  - top-level `comparabilityPolicy.workloadCohort`
  - per-workload `comparabilityCandidate` metadata.
- added directional preset for the current 8 candidate workloads:
  `bench/compare_dawn_vs_doe.config.amd.vulkan.comparability-candidates.directional.json`.

### Doe backend identity cutover (phase 1-3 completed)

- Backend runtime identity is now Doe-only across runtime-visible surfaces.
- Canonical artifacts are:
  - runtime binary: `doe-zig-runtime`
  - drop-in shared library: `libdoe_webgpu.so`
- Chromium Track-A runtime controls now use Doe names only:
  - selector value: `--use-webgpu-runtime=doe`
  - kill switch: `--disable-webgpu-doe`
  - runtime library path: `--doe-webgpu-library-path=<path>`
- Chromium GPU preference fields and mojom wiring were renamed to Doe equivalents:
  - `disable_webgpu_doe`
  - `doe_webgpu_library_path`
  - enum/runtime variants `kDoe`
- Legacy backend aliases (`fawn` runtime selector/backend library flag names) were removed.
- Doe-specific compare/report families now use `dawn-vs-doe` naming.

### Doe backend identity cleanup (phase 4 completed)

- Drop-in diagnostic helper exports are now Doe-named:
  - `doeWgpuDropinLastErrorCode()`
  - `doeWgpuDropinClearLastError()`
- Drop-in panic/error text now reports `doe drop-in ...` taxonomy.
- Runtime timestamp debug env flag is now Doe-named:
  - `DOE_WGPU_TIMESTAMP_DEBUG=1`
- Trace gate semantic-parity eligibility now matches Doe runtime module identity (`module` starts with `doe-`) and rejects non-Doe runtime module pairs in `required` mode.

### Package naming split (`@simulatte/*` public scope)

- Public npm/package scope now uses `@simulatte/*`.
- Canonical runtime/headless package is now `@simulatte/webgpu`.
- Canonical `@simulatte/webgpu` package root now lives entirely under `nursery/webgpu/`.
- Browser package naming is reserved as `@simulatte/fawn-browser`.
- Doe remains the backend/runtime family name for:
  - backend IDs (`doe_vulkan`, `doe_metal`, `doe_d3d12`)
  - compare/report families (`doe-vs-dawn`)
  - runtime artifacts (`doe-zig-runtime`, `libdoe_webgpu.so`)
- Legacy package names are retained only as compatibility history:
  - `@doe/webgpu-core`
  - `@doe/webgpu`

## 2026-02-22

### `benchmark-methodology-thresholds` contract enforcement

- `config/benchmark-methodology-thresholds.schema.json` and
  `config/benchmark-methodology-thresholds.json` are now enforced inputs for
  benchmark comparability/claimability threshold selection.
- `bench/compare_dawn_vs_doe.py` now reads:
  - `timingSelection.minDispatchWindowNsWithoutEncode`
  - `timingSelection.minDispatchWindowCoveragePercentWithoutEncode`
  - `claimabilityDefaults.localMinTimedSamples`
  - `claimabilityDefaults.releaseMinTimedSamples`
- These replace hardcoded benchmark thresholds in code.

### `modules.json` status semantics refreshed

- Bumped `config/modules.json` `schemaVersion` from `2` to `3`.
- Updated module status values from `scaffolded` to `active` for current runtime posture.

### `quirks.schema` action contract tightened

- Bumped `config/quirks.schema.json` quirk `schemaVersion` from `1` to `2`.
- Tightened `action` from open object to a strict discriminated contract:
  - `use_temporary_buffer` requires `params.bufferAlignmentBytes` (`>= 1`)
  - `toggle` requires `params.toggle`
  - `no_op` requires only `kind` and rejects extra fields
- Parser/runtime now enforce the same strictness:
  - unknown quirk fields are rejected during JSON parse
  - legacy action aliases (`noop`, `alignmentBytes`, `alignment`, `name`, `toggle_name`) are no longer accepted
  - implicit fallback alignment is removed; alignment must be explicit in the quirk record
- Updated first-party quirk examples to `schemaVersion: 2`.

## 2026-02-23

### `webgpu-spec-coverage` status semantics expanded

- Updated `config/webgpu-spec-coverage.schema.json` to add `status: "tracked"`.
- `tracked` is used for spec-universe feature inventory entries that are explicitly covered as config/audit inventory contracts, but are not yet runtime-semantic implementations.
- Migrated Dawn feature-inventory rows in `config/webgpu-spec-coverage.json` from `planned` to `tracked` for entries sourced from `bench/vendor/dawn/src/dawn/dawn.json` feature inventory.

### `webgpu-spec-coverage` tracked inventory closure

- Closed remaining tracked/blocked feature inventory rows by promoting all `feature_*` entries to explicit implemented inventory contracts.
- Feature inventory implementation contract now requires:
  - Dawn feature-enum source (`bench/vendor/dawn/src/dawn/dawn.json` `feature name` values).
  - Zig runtime capability introspection path (`wgpuAdapterGetFeatures` / `wgpuDeviceGetFeatures` via `zig/src/wgpu_capability_runtime.zig`).
  - benchmark mapping contract via capability introspection workloads (`capability_introspection`, `capability_introspection_500`).
- Current closure totals in `config/webgpu-spec-coverage.json`:
  - `implemented=103`
  - `blocked=0`
  - `tracked=0`
  - `planned=0`

### Dawn autodiscovery map coverage for extended comparable matrix

- Extended `bench/dawn_benchmark_adapter.py` `AUTODISCOVER_WORKLOAD_PATTERNS` to cover all workload IDs in `bench/workloads.amd.vulkan.extended.json` (including `p0_*`, `p1_*`, `p2_*`, macro contracts, and added Dawn suites).
- This removes local strict-run failures caused by missing autodiscovery patterns for full39 execution passes.

### `substantiation-policy` contract introduced

- Added `config/substantiation-policy.schema.json` and `config/substantiation-policy.json`.
- The policy defines machine-checked release evidence minimums:
  - `minReports`
  - `minClaimableComparableReports`
  - `requiredComparisonStatus`
  - `requiredClaimStatus`
  - `minUniqueLeftProfiles`
  - optional `targetUniqueLeftProfiles`
- `bench/substantiation_gate.py` consumes this policy for repeated-window/report substantiation checks.
- `bench/schema_gate.py` now validates the substantiation policy contract as part of blocking schema checks.

## 2026-02-24

### Dispatch-window timing selection hardening

- `bench/compare_dawn_vs_doe_modules/timing_selection.py` now applies tiny dispatch-window rejection globally (not only submit-only/no-dispatch traces) when both are true:
  - dispatch window `< timingSelection.minDispatchWindowNsWithoutEncode`
  - dispatch-window coverage `< timingSelection.minDispatchWindowCoveragePercentWithoutEncode` of `executionTotalNs`
- when rejected, timing selection falls back to `doe-execution-total-ns` and records `dispatchWindowSelectionRejected` metadata.

### AMD extended workload contract correction for concurrent execution

- `bench/workloads.amd.vulkan.extended.json` was updated to keep strict claim lanes apples-to-apples:
  - `surface_presentation` is now directional-only (`comparable=false`)
  - added `compute_concurrent_execution_single` as the strict comparable mapping for Dawn `ConcurrentExecutionTest ... RunSingle`
- new command/kernel artifacts were added for the replacement comparable contract:
  - `examples/concurrent_execution_single_commands.json`
  - `bench/kernels/concurrent_execution_runsingle_u32.wgsl`
- `bench/dawn_workload_map.amd.extended.json` now includes filter mapping for `compute_concurrent_execution_single`.

### Apples-to-apples enforcement hardening

- `bench/workloads.amd.vulkan.extended.json` now reclassifies directional/proxy mappings as non-comparable (`comparable=false`, `benchmarkClass=directional`) for strict claim lanes.
- `bench/compare_dawn_vs_doe.py` now rejects workload contract entries that set `comparable=true` while:
  - description is directional (`description` starts with `Directional`)
  - comparability notes explicitly declare closest-proxy mapping (`closest draw-call throughput proxy`)
- strict comparable runs now fail fast when those contract invariants are violated.

### Upload ignore-first scope enforcement

- `bench/compare_dawn_vs_doe_modules/comparability.py` and `bench/compare_dawn_vs_doe_modules/claimability.py` now enforce ignore-first timing scope consistency:
  - `uploadIgnoreFirstAdjustedTimingSource` must resolve to `doe-execution-row-total-ns`
  - base and adjusted ignore-first canonical timing sources must match
- mixed-scope derived upload timings now fail strict comparability and claimability checks.

### Machine-checkable comparability obligations

- `bench/compare_dawn_vs_doe_modules/comparability.py` now emits machine-checkable obligation artifacts per workload in report field `comparability`:
  - `obligationSchemaVersion`
  - `obligations[]` entries (`id`, `blocking`, `applicable`, `passes`, `details`)
  - `blockingFailedObligations` / `advisoryFailedObligations`
- workload comparability is now computed from blocking-obligation failures (`blockingFailedObligations`), preserving legacy `reasons` as human-readable diagnostics.
- `bench/claim_gate.py` and `bench/check_full39_claim_readiness.py` now require valid comparability obligation artifacts and fail when blocking obligations fail in claim/comparable lanes.

### Comparability obligation contract + parity fixtures

- Added canonical obligation-ID contract:
  - `config/comparability-obligations.schema.json`
  - `config/comparability-obligations.json`
- Added comparability parity fixture contract and data:
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/comparability_obligation_fixtures.json`
- `bench/schema_gate.py` now validates both contracts as part of blocking schema checks.
- Added verification-lane parity gate:
  - `bench/comparability_obligation_parity_gate.py`
  - validates Python fixture evaluation (`evaluate_comparability_from_facts`) and Lean/Python obligation ID alignment.
- Added Lean parity fixture proofs:
  - `lean/Fawn/ComparabilityFixtures.lean`
  - compiled by `lean/check.sh`.
- `bench/claim_gate.py` now validates report obligation IDs against `config/comparability-obligations.json` (canonical ID contract) in addition to schema-version checks.
- `bench/run_blocking_gates.py` and release orchestrators now support `--with-comparability-parity-gate` to wire this verification step into automated gate runs.

### Report anti-staleness metadata

- `bench/compare_dawn_vs_doe.py` now emits workload contract metadata in reports:
  - `workloadContract.path`
  - `workloadContract["sha256"]`
- `bench/check_full39_claim_readiness.py` now verifies:
  - exact comparable workload ID set against current workload contract
  - workload contract hash match when report metadata is present

### Dawn filter-map fallback removal

- `bench/dawn_benchmark_adapter.py` no longer accepts implicit/default workload
  map fallback resolution for Dawn gtest filters.
- `--dawn-filter-map` now resolves only explicit `filters.<workload>` entries or
  explicit `--dawn-filter`; unresolved workloads fail fast.
- `bench/dawn_workload_map*.json` contract files were updated to remove
  `filters.default` fallback entries.

### Report conformance + workload-hash enforcement hardening

- `bench/claim_gate.py` now enforces canonical obligation contract IDs from
  `config/comparability-obligations.json` plus optional strict
  workload-contract hash/path and comparable workload ID-set checks.
- `bench/run_release_pipeline.py` and `bench/run_blocking_gates.py` now pass
  strict workload contract hash/ID requirements into claim-gate release lanes.
- `bench/build_baseline_dataset.py` and
  `bench/build_test_inventory_dashboard.py` now include only conformant compare
  reports (`schemaVersion=4`, canonical comparability obligations, and
  workload-contract hash/path consistency).
- `bench/report_conformance.py` was added as the shared conformance/hash
  validation module for report-ingestion tooling.

### Track B claim-row hash-link and rehearsal artifact enforcement

- `bench/compare_dawn_vs_doe.py` claim-row linkage fields are now validated by
  gate logic, not report-emission only:
  - per-workload `claimRowHash`
  - report-level `claimRowHashChain`
- `bench/report_conformance.py` now includes claim-row hash-link validation helpers:
  - validates chain continuity (`previousHash` -> `hash`)
  - recomputes row hashes deterministically from canonical JSON context
  - verifies context linkage to:
    - `workloadContract["sha256"]`
    - `configContract["sha256"]`
    - `benchmarkPolicy["sha256"]`
    - workload `traceMetaHashes` (`left`/`right`)
- `bench/claim_gate.py` now enforces those hash-link invariants and fails
  claim lanes when linkage is missing/invalid.
- `bench/claim_gate.py` now independently validates claim tails and floors for
  claimable release lanes:
  - per-workload timed sample floors
  - required positive deltas from policy (`p50/p95/p99` for release)
- Added `bench/build_claim_rehearsal_artifacts.py` to emit required
  machine-readable rehearsal artifacts from a compare report:
  - claim gate result
  - tail-health table
  - timing-invariant audit
  - contract-hash manifest
  - rehearsal manifest linking all artifact paths
- `bench/run_release_pipeline.py` now runs this artifact builder by default when
  `--with-claim-gate` is enabled (disable with
  `--no-with-claim-rehearsal-artifacts`).
- `bench/run_release_claim_windows.py` now forwards that release-pipeline
  rehearsal-artifact behavior per window by default.

### Claim cycle contract + rollback gate enforcement

- Added active cycle-lock contract and schema:
  - `config/claim-cycle.schema.json`
  - `config/claim-cycle.active.json`
- `bench/schema_gate.py` now validates the active cycle contract as a blocking schema target.
- Added `bench/cycle_gate.py` for claim-lane governance checks:
  - validates cycle contract hash locks against on-disk contracts
  - validates comparable/directional workload partition against active workload contract
  - validates claim report conformance and hash-link consistency
  - evaluates rollback criteria and artifact namespace policy
- `bench/run_release_pipeline.py` now runs `cycle_gate.py` by default when
  `--with-claim-gate` is enabled (disable only for diagnostics via
  `--no-with-cycle-gate`).
- `bench/run_release_claim_windows.py` now forwards cycle-gate controls per
  window by default.

### Vulkan app lane runtime routing update (2026-02-26)

- Added backend lane `vulkan_doe_app` to the backend policy contract.
- Updated implicit native Vulkan lane selection to `vulkan_doe_app` in `zig/src/execution.zig`.
- Extended `config/backend-runtime-policy.json` with `vulkan_doe_app` as `doe_vulkan` with `allowFallback=false` and `strictNoFallback=true`.
- `config/backend-cutover-policy.json` remains targeted to Metal app cutover (`metal_doe_app` -> `doe_metal`); Vulkan app routing is controlled by runtime lane policy.
- Kept `vulkan_dawn_release` as the Dawn baseline benchmark/claim lane for apples-to-apples comparative evidence.
- All Vulkan compare config command templates now pin an explicit `--backend-lane` so strict AMD Dawn-baseline reports remain on `vulkan_dawn_release` while local Vulkan presets remain on their intended local lanes.
- Vulkan backend execution no longer delegates command execution to `webgpu.WebGPUBackend.executeCommand(...)`; `zig/src/backend/vulkan/mod.zig` now runs through Vulkan module contracts and emits native execution results directly.
- Added Vulkan shader-manifest telemetry path/hash emission in `zig/src/backend/vulkan/vulkan_runtime_state.zig` and backend telemetry refresh in `zig/src/backend/backend_runtime.zig` for strict shader-artifact gate coverage.
- Retired runtime rollback switch activation in backend policy loading; backend selection no longer honors `FAWN_BACKEND_SWITCH`.

### Metal end-to-end runtime closure (2026-02-26)

- `zig/src/backend/metal/mod.zig` no longer delegates command execution to `webgpu.WebGPUBackend.executeCommand(...)`; `doe_metal` now executes through metal module contracts and returns native execution results directly.
- Removed `catch unreachable` behavior from Metal backend wrappers; queue/upload/timestamp policy knobs are now explicit backend fields.
- Metal shader manifest emission is now enforced on successful command routing paths so strict shader artifact gates can validate manifest linkage in strict lanes.
- `bench/workloads.local.metal.smoke.json` `compute_workgroup_atomic_1024.commandsPath` corrected from missing `examples/dispatch_commands.json` to `examples/workgroup_atomic_commands.json`.
- Backend selection now resolves directly from strict lane policy + profile constraints with no runtime rollback override path.

### Backend lane canonical rename (2026-02-26)

Canonical lane names are now:

- `vulkan_dawn_release` (legacy alias: `vulkan_dawn_release`)
- `vulkan_doe_app` (legacy alias: `vulkan_doe_app`)
- `vulkan_dawn_directional` (legacy alias: `vulkan_dawn_directional`)
- `vulkan_doe_comparable` (legacy alias: `vulkan_doe_comparable`)
- `vulkan_doe_release` (legacy alias: `vulkan_doe_release`)
- `metal_doe_directional` (legacy alias: `metal_doe_directional`)
- `metal_doe_comparable` (legacy alias: `metal_doe_comparable`)
- `metal_doe_release` (legacy alias: `metal_doe_release`)
- `metal_doe_app` (legacy alias: `metal_doe_app`)

Contract updates in this change:

- `config/backend-runtime-policy.json` lane keys/default lane migrated to canonical names.
- `config/backend-cutover-policy.json` target lane migrated to `metal_doe_app`.
- `config/dropin-abi-behavior.json` lane mode keys migrated to canonical names.
- Runtime telemetry now emits canonical lane names (`backendLane`).
- CLI/runtime parser retains legacy lane aliases for backward compatibility.

### Backend lane map artifact + invariants (2026-02-26)

- Added generated lane-map contract artifact + schema:
  - `config/backend-lane-map.json`
  - `config/backend-lane-map.schema.json`
- Added generator utility:
  - `bench/generate_backend_lane_map.py --policy config/backend-runtime-policy.json --out config/backend-lane-map.json`
- `bench/schema_gate.py` now enforces lane-map invariants against runtime/cutover policy:
  - `laneToBackend` must exactly match `backend-runtime-policy.json` lane defaults
  - `backendToLanes` must exactly match reverse grouping from lane defaults
  - `defaultLane` and cutover target lane must resolve to valid runtime lanes
  - cutover `defaultBackend` must match mapped backend for cutover target lane
- `config/schema-targets.json` now includes lane-map schema validation as a blocking schema target.

### Metal Dawn-baseline lane addition (2026-02-26)

- Added `metal_dawn_release` as a first-class backend lane in `config/backend-runtime-policy.json`.
- `metal_dawn_release` maps to `dawn_delegate` (`allowFallback=true`, `strictNoFallback=false`) for explicit Metal dawn/baseline runs.
- Runtime lane parsing and telemetry now recognize/emit `metal_dawn_release`:
  - Zig parser accepts `metal_dawn_release` and `metal-dawn-release`.
  - backend telemetry `backendLane` uses canonical lane strings.
- Added `metal_dawn_release` to generated lane-map artifact `config/backend-lane-map.json` (both `laneToBackend` and `backendToLanes`).
- Added `metal_dawn_release` drop-in behavior ownership mode in `config/dropin-abi-behavior.json` (`dawn_ownership`).
- Release pipeline/gates now infer `metal_dawn_release` when config paths include `.metal.dawn`, and explicit `--local-metal-lane metal_dawn_release` is supported.

### Vulkan local smoke dispatch command-path repair (2026-02-26)

- Updated `bench/workloads.local.vulkan.smoke.json` `compute_workgroup_atomic_1024.commandsPath` from missing `examples/dispatch_commands.json` to `examples/workgroup_atomic_commands.json`.
- Added compatibility command file `examples/dispatch_commands.json` (kernel-dispatch atomic workload payload) so legacy/manual invocations no longer fail with `FileNotFound`.

### Vulkan timing policy backend-specific upload source allowance (2026-02-26)

- Extended `config/backend-timing-policy.schema.json` to support optional per-backend timing source allowlists via `allowedTimingSourcesByBackendId`.
- Updated upload-domain timing policy in `config/backend-timing-policy.json` to allow `doe-execution-dispatch-window-ns` when sample `backendId` is `dawn_delegate`.
- Updated `bench/vulkan_timing_policy_gate.py` to evaluate allowed timing sources using report sample backend telemetry (`traceMeta.backendId` and fallbacks) so lane-vs-lane Dawn-baseline comparisons validate against explicit policy contract.

### Vulkan timing policy lane-vs-lane fullsuite source alignment (2026-02-26)

- Expanded upload-domain backend-specific timing source allowlist in `config/backend-timing-policy.json` so `doe_vulkan` upload samples may use `doe-execution-dispatch-window-ns` in strict lane-vs-lane reports.
- Expanded render-domain backend-specific timing source allowlist in `config/backend-timing-policy.json` so `dawn_delegate` render samples may use `doe-execution-encode-ns` in strict lane-vs-lane reports.

### Vulkan Doe-vs-Doe strict normalization parity contract (2026-02-26)

- Added a dedicated strict apples-to-apples workload contract for DOE-vs-DOE lane comparisons:
  - `bench/workloads.amd.vulkan.extended.doe-vs-doe.json`
- In that contract, right-side normalization fields are explicitly mirrored from left-side fields for comparable workloads:
  - `rightCommandRepeat`
  - `rightIgnoreFirstOps`
  - `rightUploadBufferUsage`
  - `rightUploadSubmitEvery`
  - `rightTimingDivisor`
- Added strict DOE-vs-DOE normalization symmetry enforcement in `bench/compare_dawn_vs_doe.py`:
  - when both command templates target `doe-zig-runtime` and comparability mode is `strict`, comparable workloads must satisfy left/right normalization parity or the run fails fast.
- Added lane-vs-lane full-suite preset using the DOE-vs-DOE parity workload contract:
  - `bench/compare_dawn_vs_doe.config.amd.vulkan.doe-vs-dawn.fullsuite.json`

### Strict timing-scope comparability obligations for Doe-vs-Doe lanes (2026-02-26)

- Expanded comparability contract with strict blocking obligations for timing-scope parity:
  - `left_right_trace_meta_source_match`
  - `left_right_timing_selection_policy_match`
  - `left_right_queue_sync_mode_match`
- Updated obligation sources and parity fixtures:
  - `config/comparability-obligations.json`
  - `lean/Fawn/Comparability.lean`
  - `bench/comparability_obligation_fixtures.json`
  - `bench/compare_dawn_vs_doe_modules/comparability.py`
- Strict comparable runs now fail comparability when left/right timing scope selection diverges, preventing mixed-scope rows from being treated as claimable apples-to-apples evidence.
- Updated `bench/workloads.amd.vulkan.extended.doe-vs-doe.json` to mark current timing-scope-unstable workloads as `comparable=false` (directional-only) for strict DOE-vs-DOE comparable runs until timing-scope parity is stabilized:
  - `render_draw_throughput_baseline`
  - `render_draw_state_bindings`
  - `render_draw_redundant_pipeline_bindings`
  - `render_bundle_dynamic_bindings`
  - `render_bundle_dynamic_pipeline_bindings`
  - `pipeline_async_diagnostics`
  - `resource_table_immediates_500`
  - `render_draw_throughput_200k`
  - `render_multidraw`
  - `render_multidraw_indexed`
  - `render_pixel_local_storage_barrier_500`
  - `render_uniform_buffer_update_writebuffer_partial_single`

### AMD Vulkan extended comparable normalization parity fix (2026-03-06)

- Corrected the strict AMD Vulkan extended comparable workload contract for
  `resource_table_immediates_500` in `bench/workloads.amd.vulkan.extended.json`
  by adding the missing mirrored `rightCommandRepeat=500`.
- This restores strict left/right normalization symmetry for that comparable
  workload so current Dawn-vs-Doe AMD Vulkan matrix reruns can execute instead
  of failing fast during contract validation.

### AMD Vulkan native-supported subset contract tightening (2026-03-06)

- Updated `bench/workloads.amd.vulkan.extended.native-supported.json` so the
  AMD native Vulkan subset no longer marks `resource_table_immediates_500` or
  `surface_presentation` as strict comparable workloads.
- Current native Vulkan execution reports those command classes as unsupported
  (`async_diagnostics` and `surface_lifecycle` respectively), so they remain
  directional-only until the native backend implements them.

### AMD Vulkan strict identity preflight + native-supported strict configs (2026-03-06)

- `bench/preflight_bench_host.py` now probes Doe's selected Vulkan adapter
  ordinal via `doe-zig-runtime --trace-meta`, resolves that ordinal through
  `vulkaninfo --summary`, and fails strict AMD runs unless Doe and Dawn agree on
  vendor/device identity.
- `config/trace-meta.schema.json` now allows explicit Vulkan adapter-selection
  fields for strict evidence artifacts: `adapterOrdinal`, `adapterName`,
  `vendorId`, `deviceId`, `queueFamilyIndex`, and `presentCapable`.
- `config/run-metadata.schema.json` now allows the same adapter-selection data
  under an optional `adapter` object for downstream evidence products.
- `bench/compare_dawn_vs_doe.config.amd.vulkan.extended.comparable.json` and
  `bench/compare_dawn_vs_doe.config.amd.vulkan.release.json` now point at
  `bench/workloads.amd.vulkan.extended.native-supported.json` so strict AMD
  comparable/release lanes only cite command classes that are currently native
  by contract.

### Vulkan async-diagnostics submode split (2026-03-06)

- `zig/src/backend/common/capabilities.zig` now treats `async_diagnostics` as
  explicit sub-capabilities instead of one coarse family bucket:
  `async_pipeline_diagnostics`, `async_capability_introspection`,
  `async_resource_table_immediates`, `async_lifecycle_refcount`, and
  `async_pixel_local_storage`.
- Native Vulkan now declares and executes only the honest submodes currently
  supported in `zig/src/backend/vulkan/mod.zig`:
  `capability_introspection` and `lifecycle_refcount`.
- Remaining Vulkan async-diagnostics submodes stay explicit unsupported with
  submode-specific taxonomy, so workload/config surfaces cannot overclaim family
  support from partial implementation.
- AMD Vulkan workload contracts now carry `asyncDiagnosticsMode` where relevant
  so reports/evidence preserve the specific submode rather than only the coarse
  `async_diagnostics` family label.

### Vulkan large-upload cap removal (2026-03-06)

- Removed the stale `64MB` artificial upload cap from
  `zig/src/backend/vulkan/native_runtime.zig`.
- Vulkan upload prewarm now uses the full requested upload size when no
  backend-specific cap is configured, matching the large-upload comparable
  contract promotion for `256MB`, `1GB`, and `4GB` workloads.
- Allocation/driver failure now surfaces directly from the Vulkan runtime
  instead of being preclassified as `UnsupportedFeature` by a static cap.

### Benchmark deltaPercent formula drift note (2026-02-26, superseded)

- A temporary migration moved `bench/compare_dawn_vs_doe.py` to ratio-style speedup semantics:
  - from `((rightMs - leftMs) / rightMs) * 100`
  - to `((rightMs / leftMs) - 1) * 100`
- This introduced cross-tool inconsistency with other benchmark/report tooling.

### Benchmark deltaPercent convention update (2026-03-02)

- Re-aligned benchmark/report tooling to ratio-style speedup semantics:
  - `((rightMs / leftMs) - 1) * 100`
- Updated:
  - `bench/compare_dawn_vs_doe.py`
  - `bench/visualize_dawn_vs_doe.py`
  - `bench/compare_runtimes.py`
  - `bench/benchmark-writing-guide.md`
  - `bench/README.md`
- `deltaPercentConvention` now consistently declares:
  - `baseline=left`
  - positive = left faster
  - negative = left slower
- Interpretation target:
  - `+300%` means `4x` faster

### Dawn-vs-Doe strict timing-basis clarification (2026-03-02)

- Default strict timing basis for cross-runtime Dawn-vs-Doe lanes is `operation`.
- Removed forced strict `process-wall` guard in `bench/compare_dawn_vs_doe.py`.
- Updated compare presets back to `comparability.requireTimingClass=operation`.
- Documentation now explicitly separates benchmark intents:
  - `apples-to-apples` (comparable contract lanes)
  - `doe-advantage` (directional optimized lanes)
  while keeping the same timing basis rule for fairness.

### Doe-vs-Doe timing-source parity stabilization for strict comparable runs (2026-02-26)

- Updated timing selection to prefer `doe-execution-total-ns` when execution evidence is present and GPU timestamp timing is unavailable.
- Removed render-domain encode-only timing override from `bench/compare_dawn_vs_doe.py` so left/right timing selection no longer diverges by side-specific render override policy.
- Restored the 12 previously directionalized DOE-vs-DOE Vulkan workloads in `bench/workloads.amd.vulkan.extended.doe-vs-doe.json` to `comparable=true` after timing-source parity stabilization.

### Doe-vs-Doe strict comparability hardening for execution shape + upload timing scope (2026-02-26)

- Expanded comparability contract with a new blocking execution-shape obligation:
  - `left_right_execution_shape_match`
- This obligation compares sampled `executionDispatchCount`, `executionRowCount`, and `executionSuccessCount` tuples across sides and fails strict comparability on divergence.
- Updated obligation contract and parity fixtures:
  - `config/comparability-obligations.json`
  - `lean/Fawn/Comparability.lean`
  - `bench/comparability_obligation_fixtures.json`
  - `config/comparability-obligation-fixtures.schema.json`
  - `bench/compare_dawn_vs_doe_modules/comparability.py`
- Updated DOE timing-source selection for upload workloads:
  - `bench/compare_dawn_vs_doe_modules/timing_selection.py` now prefers `doe-execution-row-total-ns` (trace row execution durations) for upload-domain operation timing when execution evidence is present.
  - This removes strict upload lane drift where `doe-execution-total-ns` could violate upload timing policy allowances and mixes setup/runtime scope in per-op upload comparisons.
