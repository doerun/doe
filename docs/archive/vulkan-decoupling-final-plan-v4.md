# Archived Plan Notice

Status: completed and archived on 2026-02-26.

Drift update (lane naming canonicalization):
- vulkan_oracle (legacy alias: amd_vulkan_release)
- vulkan_app (legacy alias: amd_vulkan_app)
- vulkan_local_directional/comparable/release (legacy aliases: local_vulkan_*)
- metal_app (legacy alias: macos_app)
- metal_local_directional/comparable/release (legacy aliases: local_metal_*)
- metal_oracle (new explicit oracle lane)

Legacy lane names may still appear below in historical evidence snippets/artifact paths; runtime parsing retains backward-compatible aliases.

# Final Plan (v4): Zig Vulkan Backend + Decoupling + Controlled Cutover

Assumption: Metal plan is complete/standalone; this document is the Vulkan-only continuation with no overlap in implementation scope.

## 1) Program invariants (must hold in every phase)

1. Runtime-visible changes require config/schema/migration/docs in the same PR.
2. No hidden fallback in strict lanes.
3. Stage order is enforced: Mine -> Normalize -> Verify -> Bind -> Gate -> Benchmark -> Release.
4. AMD Vulkan claim lanes remain default and unchanged until explicit cutover.
5. Comparability/timing policy is config-driven and fail-fast on mismatch.
6. Rollback is one config switch, predeclared, tested, and audited in artifacts.

## 2) Final file structure (planned)

```text
config/
  schema-targets.json
  schema-targets.schema.json
  backend-runtime-policy.json
  backend-runtime-policy.schema.json
  backend-capability-policy.json
  backend-capability-policy.schema.json
  backend-timing-policy.json
  backend-timing-policy.schema.json
  backend-cutover-policy.json
  backend-cutover-policy.schema.json
  shader-toolchain.json
  shader-toolchain.schema.json
  shader-error-taxonomy.json
  shader-error-taxonomy.schema.json
  shader-artifact.schema.json
  dropin-abi-behavior.json
  dropin-abi-behavior.schema.json
  dropin-symbol-ownership.json
  dropin-symbol-ownership.schema.json

zig/src/backend/
  backend_ids.zig
  backend_errors.zig
  backend_iface.zig
  backend_registry.zig
  backend_policy.zig
  backend_selection.zig
  backend_runtime.zig
  backend_telemetry.zig
  dawn_oracle_backend.zig
  vulkan/
    mod.zig
    vulkan_errors.zig
    vulkan_instance.zig
    vulkan_adapter.zig
    vulkan_device.zig
    vulkan_queue.zig
    vulkan_sync.zig
    vulkan_timing.zig
    upload/
      upload_path.zig
      staging_ring.zig
    resources/
      buffer.zig
      texture.zig
      sampler.zig
      bind_group.zig
      resource_table.zig
    commands/
      copy_encode.zig
      compute_encode.zig
      render_encode.zig
    pipeline/
      wgsl_ingest.zig
      wgsl_to_spirv_runner.zig
      spirv_opt_runner.zig
      pipeline_cache.zig
      shader_artifact_manifest.zig
    surface/
      surface_create.zig
      surface_configure.zig
      present.zig
    procs/
      proc_table.zig
      proc_export.zig

zig/src/dropin/
  dropin_behavior_policy.zig
  dropin_symbol_ownership.zig
  dropin_router.zig
  dropin_diagnostics.zig

bench/
  preflight_vulkan_host.py
  shader_artifact_gate.py
  vulkan_sync_conformance.py
  vulkan_timing_policy_gate.py
  backend_selection_gate.py
  dropin_proc_resolution_tests.py
  compare_dawn_vs_doe.config.local.vulkan.directional.json
  compare_dawn_vs_doe.config.local.vulkan.comparable.json
  compare_dawn_vs_doe.config.local.vulkan.release.json
  dawn_workload_map.local.vulkan.json
  workloads.local.vulkan.smoke.json
  compare_dawn_vs_doe_modules/backend_contract.py
  compare_dawn_vs_doe_modules/shader_contract.py
  compare_dawn_vs_doe_modules/vulkan_sync_contract.py

zig/tests/backend/
  backend_registry_test.zig
  backend_selection_policy_test.zig
  backend_runtime_policy_test.zig
  backend_telemetry_test.zig

zig/tests/dropin/
  dropin_behavior_policy_test.zig
  dropin_symbol_ownership_test.zig
  dropin_router_test.zig

zig/tests/vulkan/
  vulkan_instance_test.zig
  vulkan_device_queue_test.zig
  vulkan_upload_path_test.zig
  vulkan_copy_encode_test.zig
  vulkan_compute_encode_test.zig
  vulkan_pipeline_cache_test.zig
  vulkan_shader_artifact_manifest_test.zig
  vulkan_sync_semantics_test.zig
  vulkan_timing_semantics_test.zig
  vulkan_surface_present_test.zig
```

## 3) Existing files to modify (core set)

- `bench/schema_gate.py`
- `config/migration-notes.md`
- `config/toolchains.json`
- `config/trace-meta.schema.json`
- `config/comparability-obligations.json`
- `config/benchmark-methodology-thresholds.json`
- `bench/comparability_obligation_fixtures.json`
- `bench/run_blocking_gates.py`
- `bench/run_release_pipeline.py`
- `bench/compare_dawn_vs_doe_modules/comparability.py`
- `bench/compare_dawn_vs_doe_modules/timing_selection.py`
- `bench/claim_gate.py`
- `bench/cycle_gate.py`
- `bench/trace_gate.py`
- `bench/dropin_symbol_gate.py`
- `bench/dropin_gate.py`
- `bench/workloads.local.vulkan.extended.json`
- `zig/src/execution.zig`
- `zig/src/webgpu_ffi.zig`
- `zig/src/wgpu_loader.zig`
- `zig/src/wgpu_dropin_lib.zig`
- `zig/src/main.zig`
- `process.md`
- `status.md`
- `architecture.md`
- `zig/README.md`
- `bench/README.md`

## 4) Phase plan (detailed)

## 4a) Vulkan concrete baseline defaults (derived from existing AMD Vulkan benchmark contract)

1. Keep runtime command template aligned to `bench/compare_dawn_vs_doe.config.amd.vulkan.release.json` style:
   - Doe: `zig/zig-out/bin/doe-zig-runtime --commands {commands} --quirks {quirks} --vendor {vendor} --api {api} --family {family} --driver {driver} --backend native --execute --trace --trace-jsonl {trace_jsonl} --trace-meta {trace_meta} {extra_args}`
   - Dawn: `python3 bench/dawn_benchmark_adapter.py --dawn-state bench/dawn_runtime_state.json --dawn-filter-map <dawn_map> --workload {workload}`
2. Add explicit workload semantics checks already used in `bench/workloads.amd.vulkan.extended.json`:
   - `vendor`, `api`, `family`, `driver` in each workload row must map Doe and Dawn shapes.
   - `leftCommandRepeat` and `leftTimingDivisor` must reflect per-op normalization contract for upload/compute domains.
   - Upload lanes must set `leftUploadBufferUsage=copy-dst` for strict mode and `leftUploadSubmitEvery > 0`.
3. Bake timing mode defaults into local-vulkan presets:
   - `comparability.mode=strict`
   - `comparability.requireTimingClass=operation`
   - `claimability.mode=local` with `minTimedSamples>=7` for local; `release` with `minTimedSamples>=15`.
4. Preserve runtime argument parity from existing presets:
   - `--queue-sync-mode` (`per-command|deferred`)
   - `--gpu-timestamp-mode` (`auto|off`)
   - `--queue-wait-mode` (`process-events|wait-any`)
   - `--kernel-root` when kernel-dispatch workloads exist

## 4b) Vulkan timing/source hard requirements

1. Require operation timing source selection policy by domain:
   - upload strict lanes use `doe-execution-row-total-ns` when `leftIgnoreFirstOps > 0` and emit row-level metadata.
   - compute/render lanes require non-unknown operation source (`execution*` timing family) and reject wall-time fallback in strict comparability.
   - encode-only render lanes may choose `doe-execution-encode-ns` when matching Dawn `DrawCallPerf` semantics.
2. Add explicit mixed-scope guard for upload ignore-first:
   - only valid when the same operation-level source is used for pre/post adjustment.
3. Add command/timing metadata fields to trace contracts for reproducibility (`executionTotalNs`, `executionEncodeTotalNs`, `executionSubmitWaitTotalNs`, `executionRowCount`, `timingSource`, `timingClass`, `queueSyncMode`).

### Phase 0: Contract foundation

1. Add all new config+schema files listed above.
2. Add `config/schema-targets.json` so schema gate is data-driven (no hardcoded target drift).
3. Extend trace-meta contract for backend identity and shader artifact references.
4. Add migration entries for every new field/contract.
5. Update process/status docs with new lane names and strict/advisory policy.
6. Exit: `schema_gate.py` validates all new targets; migration/docs updated.

### Phase 1: Backend interface decoupling (no behavior change)

1. Introduce backend interface and registry (`backend_iface`, `backend_registry`, `backend_runtime`).
2. Keep Dawn-backed runtime behavior unchanged through `dawn_oracle_backend.zig`.
3. Move selection logic to policy-driven resolver (`backend_selection.zig` + config contract).
4. Add telemetry fields: `backendId`, `backendSelectionReason`, `fallbackUsed`, `selectionPolicyHash`.
5. Exit: current AMD Vulkan runs identical, no performance claim regressions.

### Phase 2: Drop-in ABI contract + staged ownership routing

1. Define ABI behavior policy (`dropin-abi-behavior`) and symbol ownership map (`dropin-symbol-ownership`).
2. Stage A: keep Dawn ownership, add diagnostics and explicit behavior-mode contract.
3. Stage B: route selected symbols to Zig Vulkan via ownership map.
4. Stage C: strict lanes forbid fallback for required symbol owners.
5. Add proc-resolution tests and gate checks beyond symbol existence.
6. Exit: symbol gate + behavior gate + proc-resolution matrix all pass.

### Phase 3: Shader determinism + artifact chain

1. Implement deterministic WGSL->SPIR-V and SPIR-V post-pass runners with pinned toolchain identity.
2. Emit artifact manifest per pipeline build with required hashes and taxonomy code.
3. Add gate (`shader_artifact_gate.py`) and wire into release/blocking flow for strict Vulkan lanes.
4. Extend claim/cycle checks to require shader artifact chain for claimable Vulkan pipeline workloads.
5. Exit: reproducible manifests present and validated; failure taxonomy-only outputs.

### Phase 4: Zig Vulkan backend bring-up (vertical slices)

1. Slice 1: instance/adapter/device/queue.
2. Slice 2: upload/copy path + staging ring.
3. Slice 3: compute encode/dispatch.
4. Slice 4: pipeline cache + shader artifact emission.
5. Slice 5: render + surface/present.
6. Slice 6: proc table export integration.
7. Every unsupported path must return explicit taxonomy errors.
8. Exit per slice: unit + integration tests green, trace provenance complete.

### Phase 5: Vulkan-native sync + timing policy

1. Implement command-buffer completion semantics (queue submit + fence/semaphore strategy).
2. Enforce timing-source policy by workload domain/backend through config.
3. Add comparability obligations for timing-class/sync-model conformance.
4. Fail strict runs on mixed-scope timing or invalid ignore-first adjustments.
5. Exit: conformance tests + timing policy gate green.

### Phase 6: Strict Vulkan bench/gate integration

1. Add local Vulkan compare configs and workload maps.
2. Add Vulkan preflight script and pipeline flags.
3. Keep AMD Vulkan strict as default; Vulkan runs are additive.
4. Wire strict Vulkan through same comparability + claimability path.
5. Exit: Vulkan comparable lanes run end-to-end without weakening AMD lanes.

### Phase 7: Test matrix expansion + reliability thresholds

1. Expand to full matrix: backend selection, drop-in ABI/proc, shader chain, sync/timing, compute/upload/render/surface.
2. Put sample floors, p95/p99 requirements, flake budget, retry policy in config.
3. Add stress tests for long-run command buffer completion and pipeline cache churn.
4. Exit: thresholds pass and stability window satisfied.

### Phase 8: Dawn drawdown + controlled cutover

1. Require objective cutover conditions from `backend-cutover-policy`.
2. Flip default backend to `zig_vulkan` for AMD Vulkan app lane only.
3. Keep Dawn backend as oracle benchmark lane.
4. Validate rollback switch in CI before and after cutover.
5. Exit: Fawn.app defaults to Zig Vulkan with proven rollback path.

## 5) First production milestone (smallest safe)

1. Complete Phases 0-2 fully.
2. Implement Vulkan vertical slice for upload + compute + timing + artifact chain.
3. Run strict comparable local Vulkan lane.
4. Prove no regression in existing strict AMD Vulkan release lane.

## 6) Revised footprint

1. New files: ~120.
2. Modified files: ~28.
3. Milestone-1 target: strict-comparable headless Vulkan upload+compute.
4. Final target: Fawn.app defaults to Zig Vulkan; Dawn retained for oracle benchmarking.

## 7) PR-ready checklist per phase

### Phase 0 checklist

- [x] All new config files added and schema-backed.
- [x] `schema-targets.json` drives schema gate target list.
- [x] Trace-meta schema contains backend and shader artifact identity fields.
- [x] `config/migration-notes.md` includes all new fields and behavior changes.
- [x] `process.md` and `status.md` updated for lane/gate policy.
- [x] Exit criteria evidence attached in PR description.

### Phase 1 checklist

- [x] Backend interface/registry/runtime modules merged with no behavior delta.
- [x] Dawn-oracle backend path remains default for existing AMD Vulkan lanes.
- [x] Selection is policy-driven and config-derived.
- [x] Telemetry fields emitted and schema-valid.
- [x] Existing strict AMD Vulkan claim lanes unchanged.

### Phase 2 checklist

- [x] Drop-in behavior and symbol ownership contracts added with schemas.
- [x] Stage A diagnostics and behavior-mode signals active.
- [x] Stage B symbol routing map implemented for selected symbols.
- [x] Stage C strict fallback prohibition enforced for required owners.
- [x] Proc-resolution tests and gate coverage included.

### Phase 3 checklist

- [x] WGSL->SPIR-V and SPIR-V post-pass runners deterministic under pinned toolchains.
- [x] Shader artifact manifests emitted with full hash chain + taxonomy code.
- [x] `shader_artifact_gate.py` integrated in strict Vulkan flows.
- [x] Claim/cycle checks require shader artifact chain for claimable workloads.
- [x] Reproducibility evidence captured in artifacts.

### Phase 4 checklist

- [x] Vertical slices land in order with explicit unsupported taxonomy errors.
- [x] Upload/copy/compute/pipeline/render/surface/proc coverage implemented incrementally.
- [x] Unit and integration tests added per slice.
- [x] Trace provenance complete for each slice before next slice begins.

### Phase 5 checklist

- [x] Vulkan-native command submission completion semantics implemented.
- [x] Timing-source policy enforced by config per backend/workload domain.
- [x] Comparability obligations include timing-class + sync-model checks.
- [x] Strict runs fail on mixed-scope timing and invalid ignore-first.
- [x] Conformance and timing gates pass with artifacts.

### Phase 6 checklist

- [x] Local Vulkan compare configs and workload maps added.
- [x] Vulkan preflight host script integrated in pipeline.
- [x] AMD Vulkan strict default remains unchanged.
- [x] Vulkan strict lanes use same comparability/claimability path.
- [x] End-to-end strict comparable Vulkan run demonstrated.

### Phase 7 checklist

- [x] Full matrix tests added: selection, drop-in, shader, sync/timing, compute/upload/render/surface.
- [x] Reliability thresholds (sample floor, p95/p99, flake budget, retry policy) live in config.
- [x] Long-run sync and pipeline-cache churn stress tests included.
- [x] Stability window and threshold evidence recorded.

### Phase 8 checklist

- [x] Cutover conditions encoded in `backend-cutover-policy` and enforced.
- [x] Default backend flip scoped to AMD Vulkan app lane only.
- [x] Dawn oracle lane preserved for comparative benchmarking.
- [x] Rollback config switch validated pre- and post-cutover in CI.

## 8) Evidence snapshot (2026-02-26)

- Completed strict local Vulkan comparable gate run with report `bench/out/vulkan.finish.local.comparable.1kb.json`.
- Blocking gates passed on that report: schema, correctness, trace, backend-selection, shader-artifact, vulkan-sync, vulkan-timing-policy.
- `amd_vulkan_app` strict claim/cycle run is now green under a lane-specific local contract:
  - report: `bench/out/20260226T164929Z/vulkan.amd_vulkan_app.local.claim_cycle.json`
  - status: `comparisonStatus=comparable`, `claimStatus=claimable`
  - cycle gate: `bench/out/20260226T164929Z/cycle_gate_report.json` (`pass=true`)
- Additional strict Vulkan app-lane gates pass on the same evidence artifact: backend-selection, shader-artifact, vulkan-sync, vulkan-timing-policy.
- Rollback switch posture was exercised with `FAWN_BACKEND_SWITCH=force_dawn_oracle`; backend selection moved `amd_vulkan_app` from `zig_vulkan` to `dawn_oracle` (`bench/out/vulkan.finish.amd_vulkan_app.rollback.json`).
- Scope note: this closes app-lane strict local claim/cycle evidence; full release-matrix claim substantiation remains a separate release-proof track.
