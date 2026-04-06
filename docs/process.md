# Doe process

## 1. Pipeline: Mine -> Normalize -> Verify -> Bind -> Gate -> Benchmark -> Release

1. Intake
- pull upstream sources
- extract candidate driver/workaround deltas
- canonical miner entrypoint:
  `python3 pipeline/agent/mine_upstream_quirks.py --source-root <upstream-root> --source-repo <repo> --source-commit <commit> --vendor <vendor> --api <api> --output bench/out/mined-quirks.json --manifest-output bench/out/mined-quirks.manifest.json`
  miner output is deterministic and hash-linked (`config/quirk-mining-manifest.schema.json`).

2. Normalize
- convert deltas into structured quirk records
- validate schema

3. Verify
- apply deterministic guards for all quirks
- apply Lean obligations from `verificationMode` policy:
  - `guard_only`: no Lean proof requirement
  - `lean_preferred`: Lean preferred, not required in v0
  - `lean_required`: proof requirement is blocking (`proofLevel=proven`)
- optional safety-class overrides may be configured in `gates.json`; in v0 they are empty

4. Bind
- generate runtime config inputs and optional validator artifacts
- build specialization targets
- target path: apply proof-driven elimination when Lean discharges a runtime condition, then hoist into artifacts/config and remove the corresponding runtime branch.
- current v0 state: keep explicit Zig runtime branches unless elimination is wired end-to-end through build/CI artifacts.

5. Gate
- run schema + correctness + trace gates (blocking in v0)
- run verification + performance gates (advisory in v0)
- run drop-in compatibility gate (blocking for drop-in artifact lanes)
- current v0 CI does not execute Lean toolchain proofs as a blocking step.
- run schema hard gate:
  `python3 bench/gates/schema_gate.py`
- run comparability parity verification gate (advisory unless explicitly enabled in gate orchestration):
  `python3 bench/comparability_obligation_parity_gate.py`
- run correctness hard gate from comparison report artifacts:
  `python3 bench/gates/check_correctness.py --gates config/gates.json --quirk examples/quirks/intel_gen12_temp_buffer.json --report bench/out/dawn-vs-doe.json`
- run replay hard gate from comparison report artifacts:
  `python3 bench/gates/trace_gate.py --report bench/out/dawn-vs-doe.json --semantic-parity-mode auto`
  CI must run without `--skip-missing` and fail hard if any sample is missing or fails replay checks.
  For runtime-to-runtime reference lanes (for example Zig vs Lean trace parity), run with `--semantic-parity-mode required` so the gate fails unless semantic parity checks execute and pass.
- run drop-in compatibility hard gate from a built shared-library artifact:
  `python3 bench/drop-in/dropin_gate.py --artifact runtime/zig/zig-out/lib/libwebgpu_doe.so --report bench/out/dropin_report.json`
  CI must fail hard if symbol completeness, black-box behavior, or drop-in benchmark execution fails, and must emit a drop-in report on every run.
- run release claimability hard gate from comparison report artifacts:
  `python3 bench/gates/claim_gate.py --report bench/out/dawn-vs-doe.json --require-claimability-mode release --require-claim-status claimable --require-comparison-status comparable --require-min-timed-samples 15`
  CI must fail hard if report claim metadata is not explicit release mode claimable/comparable.
- run cycle lock + rollback hard gate for claim-lane governance:
  `python3 bench/gates/cycle_gate.py --cycle config/claim-cycle.active.json --report bench/out/dawn-vs-doe.json --artifact-class claim`
  claim lanes must fail if contract hashes drift, comparable workload identity drifts, enabled rollback criteria trigger, or claim artifacts violate namespace policy.
- run DXIL structural validation gate (opt-in):
  `python3 bench/dxil_validate_gate.py`
  validates that the native DXIL emitter produces structurally correct DXBC containers (header magic, version, part bounds, DXIL program sub-header, LLVM bitcode magic). Also exercises the Zig-level `dxil_validate.zig` and `emit_dxil_test.zig` inline tests via `zig build test-wgsl`. Opt-in via `--with-dxil-validate-gate` in `run_blocking_gates.py`.
- run CTS baseline regression gate (opt-in):
  `python3 bench/tools/cts_baseline_compare.py --baseline bench/out/cts-baseline/<baseline>.json --current bench/out/cts-baseline/<current>.json --policy config/cts-baseline-policy.json --gate`
  compares a new CTS run against a stored baseline snapshot and detects regressions (tests that were passing but now fail). Policy in `config/cts-baseline-policy.json` controls `maxNewFailures`, `requireNoRegressions`, and `gateMode` (advisory in v0). Opt-in via `--with-cts-baseline-gate` in `run_blocking_gates.py`.
  baseline generation: `python3 bench/tools/cts_baseline_generate.py --config bench/fixtures/cts_subset.fawn-node.json --backend doe_metal`
  the CTS subset config currently retains its historical compatibility filename.
  trend reporting: `python3 bench/tools/cts_baseline_trend.py --dir bench/out/cts-baseline/ --policy config/cts-baseline-policy.json`
- benchmark and drop-in pipeline scripts timestamp output artifacts by default (`YYYYMMDDTHHMMSSZ`) and place them under per-run folders (`bench/out/<timestamp>/...`) to avoid clobbering and keep directory ordering chronological. Release pipeline compare HTML is generated by default in the same run folder unless `--no-compare-html-output` is set. For fixed report paths in manual command chains, either pass `--no-timestamp-output` to the producing command or feed the resolved stamped path into gates.
- each timestamped run folder emits `run_manifest.json` (`runType`, `config`, `fullRun`, `claimGateRan`, `dropinGateRan`, and status metadata) for quick human+automation audit.
- ad-hoc/manual artifact names are routed under `bench/out/scratch/<timestamp>/...` to keep canonical run folders and dashboard inputs clean.
- canonical CI/script entrypoint for blocking gate sequence:
  `python3 bench/runners/run_blocking_gates.py --report bench/out/dawn-vs-doe.json --trace-semantic-parity-mode auto --with-comparability-parity-gate --with-dropin-gate --dropin-artifact runtime/zig/zig-out/lib/libwebgpu_doe.so --with-claim-gate --claim-require-claimability-mode release --claim-require-claim-status claimable --claim-require-comparison-status comparable --claim-require-min-timed-samples 15`
  when `--with-claim-gate` is enabled, `run_blocking_gates.py` also auto-enables `structural_equivalence_gate.py` so path asymmetry and timing-phase mismatch block the claim lane before publication.
  runs without `--with-claim-gate` validate blocking quality gates but are not release-claim readiness evidence; use `--require-claim-gate` to enforce this contract in local automation.
- canonical CI/script entrypoint for full release pipeline (preflight + compare + gates):
  `python3 bench/runners/run_release_pipeline.py --config bench/native-compare/compare.config.amd.vulkan.release.json --strict-amd-vulkan --trace-semantic-parity-mode auto --with-dropin-gate --dropin-artifact runtime/zig/zig-out/lib/libwebgpu_doe.so --with-claim-gate`
  the release config now targets the governed AMD Vulkan native-supported comparable contract, not the older default-only file and not the broader aspirational extended matrix.
  when `--with-claim-gate` is enabled, the pipeline now emits claim rehearsal artifacts by default:
  claim gate result, tail-health table, timing-invariant audit, and contract-hash manifest
  (disable only for diagnostics via `--no-with-claim-rehearsal-artifacts`).
  when `--with-claim-gate` is enabled, cycle-lock/rollback enforcement also runs by default via `cycle_gate.py`
  (disable only for diagnostics via `--no-with-cycle-gate`).
- standalone claim rehearsal artifact builder:
  `python3 bench/tools/build_claim_rehearsal_artifacts.py --report bench/out/dawn-vs-doe.json --require-comparison-status comparable --require-claim-status claimable --require-claimability-mode release --require-min-timed-samples 15`
- canonical trend/substantiation entrypoint for repeated release windows:
  `python3 bench/runners/run_release_claim_windows.py --config bench/native-compare/compare.config.amd.vulkan.release.json --windows 3 --strict-amd-vulkan --with-substantiation-gate --substantiation-policy config/substantiation-policy.json`
  this emits a timestamped window summary, per-window claim rehearsal artifacts (default-on), and a substantiation report with policy-backed report-count and profile-diversity checks.
- substantiation policy can enforce target profile diversity as a hard failure:
  `releaseEvidence.enforceTargetUniqueBaselineProfiles=true` makes `targetUniqueBaselineProfiles` blocking (not warning-only).
- for strict Dawn-vs-Doe upload comparability, fail fast if the executed `doe-zig-runtime` binary does not expose/validate upload knobs or appears older than key upload/runtime Zig sources.
- comparability decisions must be emitted as machine-checkable per-workload obligations in benchmark reports; release claim gates must validate obligation schema + blocking-pass status, not only summary strings.
- native D3D12 lane contract (`doe_d3d12`):
  - backend routing must stay direct (`backendKind=native_d3d12`), with no delegate fallback on strict D3D12 lanes.
  - legacy simulator/runtime-state modules are not part of the D3D12 lane; command execution must flow through the instance-owned native backend implementation.
  - command support must be capability-gated via `backend/common/capabilities.zig`; unsupported commands fail fast with typed taxonomy and capability name.
  - comparability/timing labeling must be derived from shared artifact classification (`backend/common/artifact_meta.zig`): GPU timestamp valid => strict; attempted-but-invalid or no-attempt => directional CPU timing classes.
  - the first governed D3D12 comparable workload scope remains compute/upload/pipeline/p0-resource only. `bench/workloads/workloads.local.d3d12.json` is the canonical D3D12 catalog; strict D3D12 compare/claim lanes select the governed comparable subset from that catalog via `selector.cohorts=["governed"]` and `selector.benchmarkClass=["comparable"]`, while broader directional parity scaffolds remain in the same catalog under exploration cohorts until Windows-backed evidence expands the contract.
  - Windows preflight is explicit and blocking before compare execution:
    `python3 bench/runners/preflight_d3d12_host.py --json`
  - first compare configs:
    - smoke: `bench/native-compare/compare.config.local.d3d12.smoke.json`
    - compare: `bench/native-compare/compare.config.local.d3d12.compare.json`
    - release scaffold: `bench/native-compare/compare.config.local.d3d12.release.json` (contract only until a Windows host produces evidence)
  - Windows handoff runner for the first governed D3D12 lane:
    `python3 bench/runners/run_local_d3d12_lane.py`
  - backend workload catalog drift is now blocked by both generation verify and catalog tests:
    - `python3 bench/tools/generate_backend_workloads.py --verify`
    - `python3 bench/tests/test_backend_workload_catalog.py`
  - render/texture contracts remain out of scope for strict D3D12 claim lanes until native D3D12 coverage expands beyond the current compute-first backend.

6. Benchmark
- run self-contained benchmark matrix
- publish deltas against Dawn/wgpu baselines
- generate post-benchmark visualization artifacts from comparison reports
- build/update tested-profile inventory + dashboard from comparison artifacts:
  `python3 bench/tools/build_test_inventory_dashboard.py --report-glob "bench/out/**/dawn-vs-doe*.json"`
  this maintains a canonical latest inventory file (`bench/out/test-inventory.latest.json`) plus dashboard (`bench/out/test-dashboard.latest.html`) and timestamped snapshots for audit.
- build/update baseline trend package from comparison artifacts:
  `python3 bench/tools/build_baseline_dataset.py --report-glob "bench/out/**/dawn-vs-doe*.json"`
  this maintains timestamped JSON+markdown baseline summaries plus stable latest outputs.
- include distribution diagnostics in benchmark reporting (ECDF overlays, KS/p-value, Wasserstein, superiority probability, and bootstrap CI summaries)
- claimability rules (sample floors, tail consistency, structural equivalence) are defined in `docs/performance-strategy.md`
- run claim-mode (`--claimability local|release`) for benchmark artifacts that will be used in performance claims

7. Release
- commit only when blocking gates are green
- mandatory release precondition in CI: gate scripts must fail hard when schema, correctness, replay, drop-in compatibility, or release-claimability checks fail.
- scheduled claim-trend publication should run the substantiation gate policy over repeated windows; single-run release CI remains focused on per-run blocking gates.

## 2. Gate Policy (v0)

v0 is speed-first. Blocking vs advisory:

1. Schema gate: blocking
2. Correctness gate: blocking
3. Trace gate: blocking
4. Drop-in compatibility gate: blocking for artifact-lane acceptance (`dropin_gate.py`)
5. Verification gate: blocking (proof artifact must pass comptime validation when `-Dlean-verified=true`; per-quirk obligation is blocking when `verificationMode=lean_required`)
6. Structural work equivalence gate: blocking for claimable results
   - both sides must execute the same commands with matching dispatch counts (all domains, not only compute)
   - both sides must report non-trivial timing in the same phases (setup, encode, submit_wait)
   - hardware-path asymmetries must be annotated with `pathAsymmetry: true` and transferability caveats
   - universally-zero timing phases on one side while the other reports material values is a blocking failure
   - see `bench/docs/benchmark-writing-guide.md` section 5.1 for full checklist
7. Performance gate: advisory (ratchet report)

This keeps process weight aligned with v0 maturity.

Promoted Track B (modules) follow the same blocking schema, correctness, and trace requirements as other core runtime modules. `python3 bench/runners/run_blocking_gates.py --with-modules` enables those promoted-module gates in the canonical blocking runner. Track B (modules) performance gates remain advisory and are not required for M6 governance promotion, but no Track B module may carry claimability assertions until explicit advisory performance coverage is added.

Promoted Track A (browser) diagnostics are governed through the lane-wrapper browser gate in `bench/browser/browser_gate.py`. `python3 bench/runners/run_blocking_gates.py --with-browser-gate` runs the macOS/host browser preflight plus fresh Playwright smoke and strict layered-superset validation with required browser promotion approvals. That default browser gate remains diagnostic-only by contract.

Track A (browser) claimability is now a separate repeated-window lane in `bench/browser/browser_claim_gate.py`, controlled by `config/browser-claim-policy.json`. `python3 bench/runners/run_blocking_gates.py --with-browser-claim-gate` runs the claim gate instead of the single-window browser gate, aggregates repeated strict browser windows, and requires positive local-claim percentiles before reporting `claimStatus=claimable`. Browser claimability remains local-only until a release-grade browser claim policy is explicitly added.

### Numeric-stability promotion rule

Numeric-stability discovery artifacts and promoted signatures are advisory for
novelty. The blocking novelty bar is a runtime-exercised receipt.

- Discovery/promotion policy lives in `config/fragility-promotion-policy.json`.
- Checked-in promoted cases live in `config/promoted-fragility-catalog.json`
  plus `config/fragility-signatures/promoted/*.json`.
- Public/runtime novelty claims require the `runtime-exercised` stage described
  in the promotion policy; promoted bench receipts alone do not satisfy that
  bar.

### Verification obligation precedence

1. `verificationMode` is the primary selector for Lean obligation.
2. `safetyClass` can impose stricter requirements only if `requireProofLevelForSafetyClass` is non-empty.
3. If both apply, the stricter `proofLevel` requirement wins.

### Zig-first, then Lean-eliminate rule

1. Runtime/hot-path behavior should land in Zig first with deterministic trace evidence.
2. Lean proofs may eliminate runtime checks by moving decisions to bind/build artifacts.
3. Elimination requires deleting the runtime branch, not leaving placeholder behavior.
4. If proof is unavailable, keep explicit Zig behavior and benchmark it.

## 3. Benchmark Matrix (Self-Contained)

Benchmark categories:
1. command encode overhead
2. validation overhead
3. submit latency (`p50`, `p95`, `p99`)
4. allocation churn

Each benchmark run must emit reproducible metadata from `run-metadata.schema.json`.
Matrix definition comes from `config/benchmarks.json`.
Performance ratchet uses `submit_latency_p95_ms` in `gates.json`.

## 4. Why This Still Counts as "Zero-Tape"

Doe removes recurring human bureaucracy, not machine-readable controls.

- no recurring committee approval loops for routine decisions
- policies are explicit in config and executed automatically
- human escalation is reserved for policy exceptions

## 5. Debug/Trace Standard

Tracing is binary and deterministic:
- fixed ring buffer settings from `config/tracing.json`
- required event fields: `module`, `opCode`, `seq`, `timestampMonoNs`, `hashes`
- crash artifact: binary dump + metadata JSON
- replay tool must reproduce module sequence and hash chain
- trace-meta may also emit coarse once-per-sample host-overhead totals
  (`host*TotalNs`) so compare reports can explain workload-unit wall minus the
  selected execution timing without inserting per-dispatch profiling probes
- semantic operator debugging extends the same deterministic contract:
  semantic IDs must be explicit command-stream inputs, trace rows must preserve
  them verbatim, and any capture/repro artifact emitted from a trace run must be
  hash-linked back to the originating trace anchor and shader manifest.

## 6. Thresholds and Placeholder Policy

Some thresholds in `gates.json` are bootstrap placeholders.

Rules:
1. placeholders must be marked explicitly in config
2. placeholders are non-blocking in v0
3. thresholds become blocking only after baseline stabilization window
4. placeholder policy applies to thresholds/reports only; runtime execution paths must be explicit implementations or explicit unsupported errors

## 7. Toolchain Upgrade Mechanism

Toolchains are pinned in `toolchains.json`.

Upgrade flow:
1. open dedicated upgrade branch
2. bump toolchain config
3. run blocking + advisory gates
4. compare delta reports
5. merge only if blocking gates pass

## 8. Apple Metal hardening flow (additive)

Apple Metal lanes are additive and must not weaken AMD Vulkan strict defaults.

1. preflight
- run `python3 bench/runners/preflight_metal_host.py`

2. compare
- use Apple Metal config presets:
  - `bench/native-compare/compare.config.apple.metal.compare.json`
  - `bench/native-compare/compare.config.apple.metal.release.json`
  - `bench/native-compare/compare.config.apple.metal.frontier.json` for broader comparable-only diagnostics
  - `bench/native-compare/compare.config.apple.metal.explore.json` for mixed comparable/directional engineering runs
  - optional Dawn-baseline lane forcing for baseline checks: `--local-metal-lane metal_dawn_release`
  - render/bundle rows may still select encode-only timing for strict comparability, but claim evaluation must use `timingInterpretation.workloadUnitWall` when `selectedTiming.scopeClass=narrow-hot-path`
  - repeat-asymmetric rows must normalize both selected operation timing and `workloadUnitWall` to one workload unit via `commandRepeat` before comparability or claimability is evaluated
  - comparable runtime workloads that expose `planPath` must execute the normalized plan boundary on both sides; mixing `planPath` on one side with generated `commandsPath` on the other is a comparability failure for `workloadUnitWall`
  - strict comparable workloads may now declare `strictNormalizationUnit` in the workload contract when the comparable unit is not raw command-row count:
    - `dispatch`: divisor must match repeated dispatch count
    - `cycle`: divisor must match repeated full-workload cycles
    - otherwise strict divisors default to repeated command-row count
    gate evaluation must reject any comparable row whose configured divisor disagrees with the trace-derived physical-op count for the declared unit.

3. blocking gates
- run backend/timing/sync/shader checks through `run_blocking_gates.py`:
  - `--with-backend-selection-gate`
  - `--with-metal-sync-conformance-gate`
  - `--with-metal-timing-policy-gate`
  - `--with-shader-artifact-gate`
  - `--with-spirv-val-gate` (validates .spv binaries with spirv-val; skips when not installed)
  - `--with-dxil-validate-gate` (validates DXIL structural correctness via native emitter and DXBC container checks)

4. strict lane policy
- strict Apple Metal lanes must fail on fallback (`fallbackUsed=true`)
- strict release claims should require backend telemetry and backend identity `doe_metal`
- shader manifest checks may be required per lane (`metal_doe_release`, `metal_doe_app`)

5. cutover verification (metal_doe_app)
- for app-lane rollout verification, run local-metal gate execution with explicit lane override:
  `--with-local-metal-gates --local-metal-lane metal_doe_app`
- validate rollback readiness by running `bench/gates/cycle_gate.py` (via release pipeline with `--with-cycle-gate --cycle-enforce-rollbacks`) under the same comparable/release evidence policy.
- runtime backend routing is strict no-fallback by contract across all lanes (`allowFallback=false`, `strictNoFallback=true` in `config/backend-runtime-policy.json`).

## 9. AMD Vulkan hardening flow (additive)

AMD Vulkan catalog presets are additive and must not weaken the governed AMD Vulkan release defaults.

1. preflight
- run `python3 bench/runners/preflight_vulkan_host.py`

2. compare
- use AMD Vulkan config presets:
  - `bench/native-compare/compare.config.amd.vulkan.compare.json`
  - `bench/native-compare/compare.config.amd.vulkan.release.json`
  - `bench/native-compare/compare.config.amd.vulkan.frontier.json` for comparable-only diagnostics outside the governed cohort
  - `bench/native-compare/compare.config.amd.vulkan.explore.json` for mixed comparable/directional engineering runs
  - `bench/native-compare/compare.config.amd.vulkan.smoke.json` for diagnostic sanity only

3. blocking gates
- run backend/sync/timing/shader checks in `bench/runners/run_blocking_gates.py`:
  - `--with-backend-selection-gate`
  - `--with-vulkan-sync-conformance-gate`
  - `--with-vulkan-timing-policy-gate`
  - `--with-shader-artifact-gate`
  - `--with-spirv-val-gate` (validates .spv binaries with spirv-val; skips when not installed)
  - `--with-dxil-validate-gate` (validates DXIL structural correctness via native emitter and DXBC container checks)

4. strict lane policy
- strict AMD Vulkan compare/release lanes must fail on fallback (`fallbackUsed=true`)
- strict AMD Vulkan release claims should require backend telemetry and backend identity `doe_vulkan`
- shader manifest checks may be required per lane (`vulkan_doe_comparable`, `vulkan_doe_release`)

## 10. Market-Readiness Evidence Flow (Additive)

This flow is additive and does not replace blocking v0 runtime gates. Its role is external claim scoping and repeatable buyer-facing evidence packaging.

1. produce strict compare evidence
- run `bench/runners/run_release_pipeline.py` (or `bench/runners/run_market_readiness_bundle.py` wrapper) on a strict comparable config.

2. scope claim statements
- run `bench/tools/build_claim_scope_report.py` and require:
  - `comparisonStatus=comparable`
  - `claimStatus=claimable`
  - `claimabilityPolicy.mode=release` (or lane-appropriate mode)
- every external statement must cite workload/domain + timing source/class + backend profile + artifact path.

3. publish runtime footprint evidence
- run `bench/tools/measure_runtime_footprint.py` and publish raw + stripped sizes and dependency counts.
- if build timing claims are made, include `--doe-build-cmd` and `--dawn-build-cmd` measured wall-time outputs.

4. publish CTS trend evidence
- run `bench/runners/run_cts_subset.py` with a versioned query config (for example `bench/fixtures/cts_subset.fawn-node.json`).
- report exact pass/fail counts and query list used.

5. publish model ceiling matrix (when AI/ML positioning is in scope)
- run `bench/tools/build_model_capacity_matrix.py` with measured row inputs (hardware, model, quantization, status, TTFT/decode/prefill, peak VRAM, artifact path).
- do not generalize beyond measured rows.

6. canonical one-command wrapper
- use `bench/runners/run_market_readiness_bundle.py` to run steps 1-5 and emit a linked manifest.
