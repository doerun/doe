# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

## 2026-04-24 (late+17) — Python sharding follow-up: SUMMA layout + weight-mapping helpers

The two next-split targets named in late+16 landed.

- `bench/runners/csl-runners/int4ple_summa_layout.py`: new module for the
  pure SUMMA host transforms. `required_positive_int`,
  `a_tiles_from_logical`, and `b_tiles_from_weight_matrix` moved out of
  `int4ple_compile_target_sim_runner.py`. The runner imports them under
  the previous underscore-prefixed names so its call sites are
  unchanged. Weight I/O (`_read_weight_prefix_bytes`) and the
  dequantize-to-f32 weight matrix path stay in the runner because they
  cross the file-I/O boundary and the dequant path is shared with the
  non-SUMMA weight materialization.
- `bench/tools/int4ple_runtime_weight_mappings.py`: new module for the
  weight-key inference helpers. `tensor_name_candidates_for_weight_key`,
  `tensor_name_for_weight_key`, `layer_index_from_step_weight_key`,
  `infer_layer_index_from_steps`, `inferred_rmsnorm_weight_key`, and
  `required_weight_keys` moved out of
  `bench/tools/run_doe_csl_int4ple_transcript.py`. The transcript
  module re-exports the same names so existing importers
  (`build_doppler_shared_execution_contract.py`,
  `test_int4ple_scheduler_readiness.py`) keep working without churn.

After the splits the two donor files are still over the 1200-line
modularity threshold (runner 1934, transcript 2662). The remaining
overage is mixed I/O / orchestration code that does not have a clean
single-purpose extraction yet; further sharding needs its own design.

Validation:

- `python3 -m py_compile` on the four edited Python files.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`: 67
  tests passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 tests passed (including `SummaHostMaterializationTests` and
  `SemanticKernelDataflowTests`).
- `python3 bench/gates/schema_gate.py` passed.
- `git diff --check` passed.

## 2026-04-24 (late+16) — P7.4 first slice plus tiled host materialization

P7.4 is narrowed from "all HostPlan kernels are stubbed" to the actual
stub path: `rmsnorm`, `residual`, and `gelu` were still inheriting toy
WGSL through the generic reduction/elementwise lowerers. The specialized
emitters for tiled matmul, fused GEMV/dequant, sample, attention, rope,
and gather remain separate generated CSL paths and are not the launch[2]
body blocker.

Landed in this entry:

- `runtime/zig/src/doe_wgsl/emit_csl_semantic_ops.zig`: new direct
  semantic CSL emitter for `rms_norm`, `residual_add`, and `gelu_gated`.
  RMSNorm now emits full-hidden-vector math with Gemma's `1.0 + weight`
  offset; residual emits binary activation add; GELU emits gated tanh
  approximation over `gate` and `input`.
- `runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig` and
  `emit_csl_host_compile_source.zig`: route Doppler `rmsnorm`,
  `residual`, and `gelu` to the semantic patterns instead of the toy
  `reduction` / `element_wise` fixtures. The WGSL fixture path remains
  available for non-Gemma generic patterns.
- `bench/runners/csl-runners/int4ple_runtime_scheduler.py`: bind
  RMSNorm weight tensors, residual `a`/`b` activation inputs, and gated
  GELU `input`/`gate` inputs explicitly. Tiled matmul bindings now carry
  matrix column metadata inferred from the weight shape.
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`: parse
  generated CSL `@zeros([...])` arrays and follow
  `@export_symbol(A_ptr, "a")` style pointer exports back to their
  backing arrays, so tiled `a` / `b` / `c` no longer collapse to
  `elementsPerPe=1`. The plan also attaches explicit SUMMA host
  transforms for logical activation/weight matrices and C-tile outputs.
- `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py` and
  `int4ple_launch_step_adapter.py`: materialize logical activations into
  SUMMA A tiles, dequantize/tile rowwise Q4_K_M weights into SUMMA B
  tiles, and detile C outputs back to logical downstream buffers.
- `bench/tools/run_doe_csl_int4ple_transcript.py`: runtime weight mapping
  now includes inferred layer/final RMSNorm weights, including BF16 norm
  tensors.

Validation:

- `python3 -m py_compile` on the edited Python runner/tool files.
- `python3 -m unittest` across the eight CSL-focused test modules: 88
  tests passed.
- `zig build test-wgsl` passed; only existing TSIR line-limit allowlist
  warnings were printed.
- `zig build csl-host-plan-tool` passed.
- `python3 bench/gates/schema_gate.py` passed.
- `git diff --check` passed.

Still not claimed:

- No regenerated full HostPlan simulator run has been executed against
  these changes yet. The expected next validation is that launch[2]
  stages `tiled.a` as `P*P*Mt*Kt` device elements and writes a logical
  `[tokens, out_dim]` activation for the next launch.
- `kv_cache` and `fused_ffn` are still audit items: they have dedicated
  emitters, but their exact parity against the Doppler reference still
  needs source-level verification or simulator evidence.
- Python sharding follow-up: `int4ple_compile_target_sim_runner.py` and
  `bench/tools/run_doe_csl_int4ple_transcript.py` remain over the 1200
  line modularity threshold. Owner: CSL lane. Next split target:
  move SUMMA host transforms into `bench/runners/csl-runners/int4ple_summa_layout.py`
  and runtime weight mapping/RMSNorm inference helpers into a dedicated
  `bench/tools/int4ple_runtime_weight_mappings.py`.

## 2026-04-24 (late+15) — Path A Zig target emission wired

Path A routing is now connected through the Zig host-plan target emitter.
This supersedes late+14's "Zig target emission owed" note.

Landed in this entry:

- `runtime/zig/src/csl_host_plan_tool.zig`: `buildCompileTargets`
  now emits base targets plus `_prefill` / `_decode` compile targets
  for `rmsnorm`, `residual`, and `gelu`. The variant targets use
  unique target names while pointing at the base kernel source files
  (`<base>/layout.csl` and `<base>/pe_program.csl`) so cslc builds
  separate binaries with the phase-specific compile params already
  emitted by `bench/tools/int4ple_manifest_compile_params.py`.
- `runtime/zig/src/csl_host_plan_tool.zig`: compile-source
  materialization now writes sources once from `plan.kernels` rather
  than assuming a strict one target per kernel pairing. This means
  `plan.kernels` and launches can remain base-name stable while the
  compile-target list grows by the six phase variants.
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`: host-plan
  validation now accepts only the explicit phase variants backed by
  base kernels (`rmsnorm`, `residual`, `gelu`) and rejects phase
  suffixes on unrelated kernels.
- `runtime/zig/tools/csl_sdk_driver.py`: `rmsnorm_prefill` and
  `rmsnorm_decode` are treated as row-kernel compile targets so their
  SDK fabric height stays at one. Residual and gelu phase variants
  carry `height: 1` in compile params already.
- `bench/tests/test_csl_driver_taxonomy.py`: assertion added for the
  rmsnorm phase target row-kernel classification.

Correction to late+14: no matching phase `KernelSpec` entries are needed
in `plan.kernels`, and `plan.prefill_launches` / `plan.decode_launches`
do not need to rewrite `kernelName` to the variant. The intended shape is:
Zig emits phase compile targets, Python execution planning remaps
base-name launches with `launch.phase` to the resolved `targetName`, and
legacy no-phase launches keep using the base target.

Validation:

- `zig fmt runtime/zig/src/csl_host_plan_tool.zig runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`
- `zig build csl-host-plan-tool`
- `zig test --dep build_options -Mroot=src/csl_host_plan_tool.zig -Mbuild_options=.zig-cache/c/c2462405c3bf55dcb3c6284318814a0c/options.zig`
  passed 76 tests, including the new phase-target emission and
  host-plan validation tests.
- `python3 -m py_compile bench/runners/csl-runners/int4ple_hostplan_execution_plan.py runtime/zig/tools/csl_sdk_driver.py`
- 80 Python tests passed across:
  `test_csl_governed_lane_gate`,
  `test_csl_source_wgsl_regeneration`,
  `test_csl_wgsl_role_integration`,
  `test_csl_driver_taxonomy`,
  `test_csl_host_plan_kernel_patterns`,
  `test_int4ple_manifest_compile_params_gate`,
  `test_int4ple_scheduler_readiness`,
  `test_csl_governed_lane_receipt`.
- Host-plan artifact smoke: `doe-csl-host-plan-tool --mode steps` against
  the existing Gemma 3 1B normalized execution emitted 17 compile targets
  under `/tmp/doe-path-a-hostplan-check`, including all six phase variants
  with base source paths.

Still open before a positive Gemma 3 1B CSL parity receipt:

- Regenerate the CSL hostplan artifacts and confirm the generated
  compile target list contains the six phase variants with matching
  compile params.
- Run the full simulator through prefill plus 8 decode cycles and
  confirm no `phase_variant_target_missing`, `target_missing`, or
  input-buffer-size mismatch blockers.
- Implement P7.4 real kernel bodies for rmsnorm, residual, gelu, and
  the remaining stubbed math kernels before expecting numerical parity.
- Bind the new CSL transcript to the bundle-derived reference export
  only after routing, full execution, and kernel math are green.

## 2026-04-24 (late+14) — Path A Python half landed; Zig target emission owed

The iter-15 runner-side override (late+13) is reverted. Path A replaces
it: upstream Zig compile-target registration + Python hostplan dispatch
remap + drift-guard tests, with base kernel names preserved for
back-compat.

Landed in this entry:

- `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`:
  removed `_ELEMENTWISE_DECODE_TARGETS`, `_is_elementwise_decode_launch`,
  `_compile_elementwise_decode_override`,
  `_apply_elementwise_decode_override`, and the dispatch block that
  applied the override before `_stage_launch_arrays`. The runner is
  back to its pre-iter-15 shape plus the embed-ROI pattern.
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`:
  `_resolve_phase_variant_target` added. Called at the launch resolution
  loop (formerly `target_name = launch["kernelName"]`). For rmsnorm /
  residual / gelu launches with `launch.phase` set to `prefill` or
  `decode`, the resolver remaps to `<kernel>_<phase>`. Missing phase
  variants or unsupported phases emit explicit blockers
  (`phase_variant_target_missing:<name>` or
  `phase_variant_unsupported:<kernel>:<phase>`) rather than silently
  falling back to the base binary. Legacy launches without a phase
  pass through unchanged. Launch records now carry both `kernelName`
  (base) and `targetName` (resolved) for auditability.
- `bench/tests/test_int4ple_scheduler_readiness.py`:
  `PhaseVariantTargetResolverTests` class with 8 focused cases:
  non-elementwise pass-through, legacy launch pass-through, prefill
  and decode variant resolution, all three elementwise kernels with
  both phases, missing-variant blocker, unsupported-phase blocker, and
  a drift guard asserting the compile-params projection emits every
  `<kernel>_<phase>` key the resolver may remap to. 26 total tests
  pass in this file.
- `bench/tools/int4ple_manifest_compile_params.py` unchanged from
  iter-12 — already emits the `_prefill` / `_decode` keys the resolver
  and drift-guard depend on.

Tests green across 8 CSL-related test files (82 tests total):
`test_int4ple_manifest_compile_params_gate`,
`test_int4ple_scheduler_readiness` (includes the 8 new phase-routing
cases), `test_csl_host_plan_kernel_patterns`, `test_csl_driver_taxonomy`,
`test_csl_governed_lane_gate`, `test_csl_governed_lane_receipt`,
`test_csl_source_wgsl_regeneration`, `test_csl_sdk_210_migration`.

Zig-side work NOT landed in this entry — scope beyond what can be
validated without a full pipeline regen:

- `runtime/zig/src/csl_host_plan_tool.zig:buildCompileTargets` needs
  to emit 6 additional compile targets (`rmsnorm_prefill`,
  `rmsnorm_decode`, `residual_prefill`, `residual_decode`,
  `gelu_prefill`, `gelu_decode`) pointing at the base kernels'
  `layout.csl` / `pe_program.csl` source files. Strict 1:1 pairing at
  `materializeCompileSources:443` (`plan.kernels.len != targets.len`)
  means the upstream planner that builds `plan.kernels` must also
  gain matching `KernelSpec` entries. Launches in
  `plan.prefill_launches` must reference `<kernel>_prefill` and
  `plan.decode_launches` must reference `<kernel>_decode` so the
  `validateLaunch` pairing at `emit_csl_host_plan.zig:317-332` holds.
- A compile-sources materialization pass that accepts phase-variant
  kernel specs by reusing the base kernel's CSL sources (both
  variants share `rmsnorm/layout.csl`).
- `zig build csl-host-plan-tool` must stay green.

Until the Zig emitter lands the variants, any plan regen that feeds
launches with `launch.phase` set into the Python execution planner
will emit `phase_variant_target_missing:<kernel>_<phase>` blockers.
That is the intended behavior per the explicit-over-implicit
discipline and surfaces the staging bug directly — no silent
fallback to the wrong-width binary. Legacy plans without `phase`
fields on launches continue to work unchanged.

Stub-kernel caveat remains (punch-list P7.4): rmsnorm, residual, gelu,
attn_head256, and lm_head_gemv `pe_program.csl` bodies must emit
full normalized tensors rather than scalar-at-pe_id before CSL
digests can match the bundle-derived reference transcript. This is
independent of routing and can proceed in parallel with the Zig
emission work; keep it separate from the routing patch so failure
classification stays clean.

## 2026-04-24 (late+13) — Decode-phase elementwise override wired in runner

`bench/runners/csl-runners/int4ple_compile_target_sim_runner.py` now
intercepts decode-phase launches of `rmsnorm`/`residual`/`gelu` and runs
each against a width=1 binary compiled at runtime. Mirrors the existing
`_compile_embed_roi_target` pattern. Four new symbols:

- `_ELEMENTWISE_DECODE_TARGETS = {"rmsnorm", "residual", "gelu"}`
- `_is_elementwise_decode_launch(launch)` — true iff `launch.phase` is
  `"decode"` and `launch.targetName` is an elementwise target compiled
  with `width > 1`.
- `_compile_elementwise_decode_override(launch, runtime_dir)` — invokes
  `cslc_executable()` against the base kernel's `layout.csl` with
  `width:1,hidden_size:<N>` (rmsnorm) or `width:1,height:1,chunk_size:<N>`
  (residual/gelu). Output at `<runtime_dir>/decode-override/<target>/compiled/`,
  cached per kernel name.
- `_apply_elementwise_decode_override(launch, runtime_dir)` — returns a
  launch copy with `compileDir` repointed, `compileParams.width=1`,
  `targetGeometry` rebuilt, and `resolvedInputs/resolvedOutputs[*]
  .materialization.plannedElementCount` narrowed from
  `attention_tokens * elementsPerPe` to `1 * elementsPerPe`.

Dispatch in `execute_hostplan_runtime` applies the override before
`_stage_launch_arrays`. Emits `hostplan_decode_override_applied` progress
event for traceability (explicit, not a hidden fallback).

Test coverage unchanged — 68 tests green across
`test_int4ple_manifest_compile_params_gate`,
`test_int4ple_scheduler_readiness`, `test_csl_host_plan_kernel_patterns`,
`test_csl_driver_taxonomy`, `test_csl_governed_lane_gate`,
`test_csl_governed_lane_receipt`.

End-to-end validation still owed:

- A full CSL HostPlan regen + simulator run is needed to verify the
  override binary loads, its input/output buffer sizes match at the SDK
  level, and decode launch[0] (`rmsnorm` post-sample) does not fail.
- The width=1 compile invocation uses fabric-dims 8,3 — matching the
  base compile's fabric for rmsnorm/residual/gelu. If the base compile
  uses different fabric geometry at width=N, that assumption may need
  adjusting.
- Stub kernel caveat unchanged: P7.4 kernel bodies still need real
  normalization logic before digests can match the reference.

Remaining path to positive receipt (unchanged):

1. Verify the override via CSL pipeline regen (not done).
2. Real kernel bodies (P7.4) so digests match reference.
3. Re-run binder with CSL transcript receipt → positive parity artifact.

## 2026-04-24 (late+12) — Phase-aware compile-params variants emitted (additive)

`bench/tools/int4ple_manifest_compile_params.py` now emits six additional
keys alongside the existing `rmsnorm`/`residual`/`gelu` entries:

- `rmsnorm_prefill` (`width=attention_tokens`), `rmsnorm_decode` (`width=1`)
- `residual_prefill`, `residual_decode`
- `gelu_prefill`, `gelu_decode`

All nine entries emit with Gemma 3 1B parameters under a 15-token prompt
reference. The original three keys are preserved for back-compat; new
consumers can opt into the `_<phase>` variants.

Test coverage unchanged — 56 tests green (`test_int4ple_manifest_compile_params_gate`,
`test_int4ple_scheduler_readiness`, `test_csl_host_plan_kernel_patterns`,
`test_csl_driver_taxonomy`).

Remaining downstream wiring (pending):

- Operation graph emitter: register `<kernel>_<phase>` compile targets so
  `cslc` compiles the same CSL source twice, once per phase.
- HostPlan emitter (`int4ple_hostplan_execution_plan.py`): dispatch launches
  to `<kernel>_<phase>` based on `launch.phase`, mirroring the existing
  `lm_head_prefill_stable` pattern at line 183.
- Scheduler tests: update `test_int4ple_scheduler_readiness.py` to assert
  the `_prefill`/`_decode` routing exists when emitted.

Without downstream consumers, the new keys are inert. With them wired,
prefill launches stage 17280-elem activations into the `_prefill` binary
(width=N) and decode launches stage 1152-elem activations into the
`_decode` binary (width=1), resolving the current staging mismatch that
would hit on the first decode launch once prefill clears.

## 2026-04-24 (late+11) — Bundle-derived reference export lands; #11 decode-width surgery scoped

Reference side is now wired. The Doppler program bundle embedded at
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/doppler-program-bundle.json`
(2026-04-24 17:01) carries a non-synthetic `referenceTranscript` with 8 real
per-step logit digests (`logits.perStepDigests`, `logits.steps[]`), 8 real
generated token IDs (`tokens.ids`), KV cache state hash (`kvCache.stateHash`),
and matching `execution.graphHash = 7b8152f81712...` — which is the identity
the CSL HostPlan is pinned against.

Landed:

- `bench/tools/merge_bundle_into_reference_export.py` — adapter that fuses the
  iter-6 node-webgpu export's identity fields (manifest/weight/shard/producer)
  with the CSL-side program bundle's `referenceTranscript`. Output validates
  clean against `config/doppler-int4ple-reference-export.schema.json`.
- `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-export-bundle-derived/doppler_int4ple_reference_export.json`
  — the bundle-derived export. Graph hash 7b8152f81712 (matches CSL),
  manifest hash 6644e3be29b9db5b (matches current manifest), 8 real decode
  steps, stopReason `decode_steps_exhausted`.
- `examples/doe-csl-reference-parity.gemma-3-1b-reference-ready-csl-pending.sample.json`
  — the parity artifact when the binder is run against the bundle-derived
  export with no CSL-side trace. Fields that are now TRUE:
  `sameManifestHash`, `sameGraphHash`, `externalReferenceOutputBound`,
  `syntheticInputsAbsent`, `syntheticWeightsAbsent`, `manifestHashMatched`,
  `graphHashMatched`. Fields that remain FALSE (all CSL-side pending):
  `tokenIdsMatch`, `perStepLogitsParityPassed`, `realKvCacheUsed`,
  `cslOutputHashBound`, `decodeTranscriptBound`, `outputParityPassed`,
  `fullModelDepthExecuted`, `stubStagesAbsent`, `weightHashMatched`.
- Invocation: `python3 bench/tools/bind_doppler_int4ple_reference_to_csl_parity.py
  --reference-export bench/out/doppler-reference/gemma-3-1b-doe-webgpu-export-bundle-derived/doppler_int4ple_reference_export.json
  --out <out> --kernel-stage pending_full_int4ple_csl_transcript_lowering --kernel-is-stub true`
  PASSED schema validation end-to-end.

Follow-up for decode-phase width (not landed, design scoped):

With the late+10 width=attention_tokens fix in place, prefill launch[1]
(rmsnorm) will stage correctly, but decode phase will fail the inverse
direction: kernel expects 17280-elem input per launch but decode produces
only 1*1152 per step. Two implementation options:

- **Runner-side override** (mirrors `_compile_embed_roi_target`). Add
  `_is_elementwise_decode_launch` + `_compile_elementwise_decode_override` at
  `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py:~1208`.
  Compiles width=1 variant to `<runtime_dir>/decode-override/<kernel>/`;
  rewrites `launch.compileDir` and must ALSO rewrite
  `resolvedInputs/resolvedOutputs.materialization.plannedElementCount` from
  `attention_tokens * hidden_size` to `1 * hidden_size` for decode-phase
  elementwise launches. The plannedElementCount rewrite is the step easy to
  miss; without it the override compile is still rejected at the staging size
  check (`int4ple_compile_target_sim_runner.py:1166-1170`).
- **Phase-aware compile params** (cleaner, more files). In
  `bench/tools/int4ple_manifest_compile_params.py` emit both
  `rmsnorm_prefill` (width=attention_tokens) and `rmsnorm_decode` (width=1);
  same for residual/gelu. Hostplan emitter dispatches on `launch.phase` to
  `<kernel>_<phase>` (the pattern `lm_head_prefill_stable` already uses at
  `int4ple_hostplan_execution_plan.py:183`). Adds 3 compile targets and
  updates `test_int4ple_scheduler_readiness.py` expectations.

Stub-kernel caveat: even once #11 unblocks decode staging, rmsnorm
`pe_program.csl` currently writes a single scalar sum at `output[pe_id]`
rather than the full normalized hidden-dim vector. That's punch-list Step
7 (P7.4 real kernel body). Unblocking #11 gets the pipe flowing
end-to-end; real parity-passing digests need #11 AND real kernel bodies.

Independent finding — WebGPU non-determinism: same model + prompt + greedy
across three adapters (CSL-side bundle via unknown adapter at 17:01,
Playwright Chromium/Vulkan, Mesa software llvmpipe) produces three
different 8-token sequences. The CSL-side bundle's embedded
`referenceTranscript` is the authoritative anchor; don't regenerate the
reference on each side and expect parity.

## 2026-04-24 (late+10) — Embed runs clean, rmsnorm width=1 blocks prefill launch[1]

The embed launch now completes under the real HostPlan executor on Gemma 3
1B. The progress log at
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/trace.json.progress.jsonl`
records six `embed_roi_sublaunch` completions stepping
`hiddenOffset` through 0, 192, 384, 576, 768, 960 (the six
`1152 / 192 = 6` hidden chunks) for 15 tokens, ending in
`hostplan_launch_complete status=succeeded target=embed`.

The next blocker is deterministic: launch[1] target `rmsnorm` fails the
runner's input size check at
`bench/runners/csl-runners/int4ple_compile_target_sim_runner.py:1166-1170`
with
`launch[1].input_buffer_size_mismatch:activation:prefill:0000:global:embed:17280!=1152`.
The embed stages its batched `[prompt_tokens=15, hidden_dim=1152]` output
(17280 f32) into `global:embed`, but the rmsnorm kernel was compiled with
`width=1, hidden_size=1152` — a single-vector kernel that expects 1152 elements
per launch. The rmsnorm `layout.csl` annotates itself as
`single-PE reduction kernel (width x 1, no cross-PE fabric)`; `width` maps
one PE per token via `@set_rectangle(width, 1)`.

Source of the hardcoded width: `bench/tools/int4ple_manifest_compile_params.py`
lines 434-447 pin `"width": 1` for rmsnorm, residual, and gelu, ignoring
`attention_tokens = max(1, prompt_tokens)` that the same function already
derives and threads into the attention kernels.

Landed (this entry): the three hardcoded `width: 1` values are replaced
with `attention_tokens` so rmsnorm / residual / gelu compile for the
prefill token batch. The compiled kernel's `plannedElementCount` becomes
`attention_tokens * hidden_dim` and matches the embed's staged batched
activation.

Decode-phase follow-up (not landed): the same rmsnorm / residual / gelu
kernels are reused in the decode phase (393 launches each for prefill and
decode in `simulator-plan.json:runtime`). Decode stages a single-token
activation (1152 f32) into the same symbol, so the next blocker will shift
to the first decode launch with the inverse mismatch (`1152 != N*1152`).
Three design options are open:

- phase-aware compile: emit distinct `rmsnorm_prefill` and `rmsnorm_decode`
  targets with their own `width` values; extends the kernel registry.
- runner-side decode padding: stage a zero-padded N-token buffer and read
  back only the first 1152 elements. Keeps one compiled kernel; adds
  runner logic.
- runner-side per-token unroll (prefill): keep `width=1`, have the runner
  loop per token during prefill. Mirrors the existing embed-ROI sublaunch
  pattern in `_is_embed_roi_launch` at the same runner file. Cleanest long-term
  shape, biggest change surface.

The `late+9` entry below is superseded: embed runtime is no longer the blocker.

Verified:

- `python3 -m unittest bench.tests.test_int4ple_manifest_compile_params_gate bench.tests.test_int4ple_scheduler_readiness`
- `python3 -m unittest bench.tests.test_csl_host_plan_kernel_patterns bench.tests.test_csl_driver_taxonomy bench.tests.test_csl_governed_lane_gate bench.tests.test_csl_governed_lane_receipt bench.tests.test_csl_source_wgsl_regeneration bench.tests.test_csl_sdk_210_migration`

Full-pipeline revalidation (cslc recompile + simfabric run) is not yet
performed; the edit changes the params dict only.

## 2026-04-24 (late+9) — Gemma 3 HostPlan compile green; real embed launch is the blocker

The Gemma 3 CSL HostPlan now clears the previous compile blockers. The
current simulator driver artifact records successful compilation for the
active Gemma 3 targets, including `embed`, `tiled`, `attn_head256`, and
`lm_head_gemv`, with concrete HostPlan params at
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/simulator-driver-result.json`.

Runtime materialization has advanced far enough to enter the real HostPlan
executor: the Program Bundle tokenized prompt is hash-matched from the
Doppler token IDs, runtime weight aliases resolve through the Program Bundle
tensor inventory, packed Q4 bytes stage as SDK u32 memcpy words, and the
tiled/lm-head launch symbols resolve against generated CSL exports. The
current transcript receipt is therefore non-stub
(`kernelStage=int4ple_hostplan_executor_runtime`) at
`bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json`.

The remaining simulator blocker is execution, not compilation or artifact
binding. The latest bounded run fails with `runtime_timeout` after reaching
`hostplan_launch_start` for launch `embed`, before a comparable
`cslTranscript` is produced. The next Person A step is to make this first
real embed launch complete under a bounded runner, either by chunked embed
execution with output reassembly or an equivalent governed streaming/ROI path
that still emits receipt-grade token/logit/KV evidence.

Verified:

- `python3 -m unittest bench.tests.test_int4ple_scheduler_readiness`
- `python3 -m unittest bench.tests.test_csl_driver_taxonomy bench.tests.test_int4ple_manifest_compile_params_gate`
- `python3 -m py_compile bench/tools/run_doe_csl_int4ple_transcript.py bench/runners/csl-runners/int4ple_hostplan_execution_plan.py bench/runners/csl-runners/int4ple_compile_target_sim_runner.py bench/runners/csl-runners/int4ple_runtime_scheduler.py bench/tests/test_int4ple_scheduler_readiness.py`
- `python3 bench/gates/schema_gate.py`
- `zig build csl-host-plan-tool`
- `zig build test-wgsl`

## 2026-04-24 (late+8) — Track C hardware preflight paths verified pending

The Gemma 3 hardware receipt path is wired for both non-blocking C
entry points, without claiming hardware execution:

- direct system mode records the `DOE_CSL_CMADDR=$DOE_CSL_CMADDR`
  command shape for `run_doe_csl_int4ple_transcript.py`
- WSC appliance mode records the `csl_appliance_driver.py --system`
  command shape with `%CMADDR%` substitution
- `verify_cmaddr_propagation.py` confirms endpoint redaction and
  simfabric/system target classification

The pending hardware receipts gate in both modes with
`hardwareRun.status=pending_simulator_parity`. Strict hardware success
still fails, as intended, until simulator parity exists and a real
endpoint or WSC appliance run emits hardware token/logit/KV evidence.

The Program Bundle reference export schema now admits tokenized prompt
provenance fields (`source`, `sourcePath`, `tokenIdsSha256`) used by
the current reference artifact, so the parity bind step is no longer
blocked by schema drift before the hardware preflight.

Verified:

- `python3 bench/tools/verify_cmaddr_propagation.py --out-json /tmp/cmaddr-propagation-smoke.json`
- `python3 bench/tools/bind_doppler_int4ple_reference_to_csl_parity.py --reference-export bench/out/doppler-reference/program-bundle-export/doppler_program_bundle_reference_export.json --csl-transcript-receipt bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --out /tmp/gemma-3-1b-doe-csl-reference-parity.pending.json`
- `python3 bench/tools/prepare_doe_csl_int4ple_hardware_receipt.py --parity-receipt /tmp/gemma-3-1b-doe-csl-reference-parity.pending.json --transcript-receipt bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --out /tmp/gemma-3-1b-doe-csl-hardware-receipt.system.pending.json --program-bundle /home/x/deco/doppler/examples/program-bundles/gemma-3-1b-it-q4k-ehf16-af32.program-bundle.json --execution-target system`
- `python3 bench/tools/prepare_doe_csl_int4ple_hardware_receipt.py --parity-receipt /tmp/gemma-3-1b-doe-csl-reference-parity.pending.json --transcript-receipt bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --out /tmp/gemma-3-1b-doe-csl-hardware-receipt.wsc.pending.json --program-bundle /home/x/deco/doppler/examples/program-bundles/gemma-3-1b-it-q4k-ehf16-af32.program-bundle.json --execution-target wsc_appliance`
- `python3 bench/gates/doe_csl_int4ple_hardware_receipt_gate.py --receipt /tmp/gemma-3-1b-doe-csl-hardware-receipt.system.pending.json`
- `python3 bench/gates/doe_csl_int4ple_hardware_receipt_gate.py --receipt /tmp/gemma-3-1b-doe-csl-hardware-receipt.wsc.pending.json`
- `python3 -m unittest bench.tests.test_doppler_int4ple_reference_export_schema bench.tests.test_int4ple_hardware_receipt`

## 2026-04-24 (late+7) — Gemma 3 transcript parity report normalizes WebGPU receipts

The generic transcript parity report builder now accepts the current Gemma
3 WebGPU receipt shape, where the comparable transcript is nested under
`webgpuTranscript.decodeTranscript`. It also treats non-ready transcript
lanes as blocked execution evidence instead of failed parity, while keeping
source-program identity independent from readiness state.

Regenerated:

- `bench/out/doppler-reference/gemma-3-1b-transcript-parity-report.json`

Current Gemma 3 1B report state:

- participants: Doppler reference, Doe WebGPU, Doe CSL
- comparisons: 3
- passed: 0
- failed: 1
- blocked: 2
- `sameSourceProgramAcrossParticipants=true`

All participants agree on manifest, graph, weights, input set, authoring
surface, and program bundle identity. The remaining blockers are execution
evidence, not program drift: the WebGPU lane is `output_ready` but only has
one actual decode step with `eos_token`, so it fails against the eight-step
Doppler reference transcript; the CSL lane is still `simulator_failed` with
`cslTranscript.status=not_produced`, so CSL comparisons are blocked until
the real simfabric transcript is produced.

Verified:

- `python3 -m unittest bench.tests.test_transcript_parity_report`
- `python3 bench/tools/build_transcript_parity_report.py --reference-export bench/out/doppler-reference/program-bundle-export/doppler_program_bundle_reference_export.json --lane webgpu:bench/out/doppler-reference/gemma-3-1b-doe-webgpu-transcript.json --lane csl:bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --out bench/out/doppler-reference/gemma-3-1b-transcript-parity-report.json`
- `python3 bench/gates/schema_gate.py`

## 2026-04-24 (late+6) — Gemma 3 embed CSL chunking compiles

Gemma 3 1B `embed` no longer fails with PE memory exhaustion or the
intermediate fail-closed
`csl_compile_params_infeasible_embed_grid_budget` blocker. The gather PE
program now reads its CSL layout coordinates from `<layout>` and flattens
`width x height` into row shards, so row coverage can use the full
HostPlan grid without generating one distinct PE program per tile. Hidden
and token chunking remain explicit host-plan params.

The current Gemma 3 1B HostPlan projection emits:

- `rows_per_pe=22`
- `hidden_per_pe=192`
- `tokens_per_chunk=16`
- `height=54`

The rebuilt host-plan tool and transcript rerun produced a driver result
where `embed`, `tiled`, `attn_head256`, and `lm_head_gemv` all compile
successfully. The transcript is still not a positive simulator receipt:
`kernelIsStub=true` remains because non-priority targets still fail the
overall compile sweep (`rope`, `attn_decode`, `residual`, and `gelu`).

Verified:

- `zig build csl-host-plan-tool`
- `python3 bench/tools/run_doe_csl_int4ple_transcript.py --program-bundle /home/x/deco/doppler/examples/program-bundles/gemma-3-1b-it-q4k-ehf16-af32.program-bundle.json --out bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --hostplan-bundle-root bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan`
- `python3 -m unittest bench.tests.test_int4ple_manifest_compile_params_gate bench.tests.test_int4ple_scheduler_readiness bench.tests.test_csl_driver_taxonomy`
- `zig build test-wgsl`
- `python3 bench/gates/schema_gate.py`

## 2026-04-24 (late+5) — Gemma 3 tiled matmul CSL export names fixed

The Gemma 3 hostplan `tiled` target no longer fails with
`csl_compile_undeclared_identifier` for symbol `A`. The tiled matmul PE
emitter now exports the WGSL storage global names that the layout declares,
so the generated `pe_program.csl` binds `A_ptr`/`B_ptr`/`C_ptr` to
`a`/`b`/`c` for the active HostPlan fixture. The rebuilt
`doe-csl-host-plan-tool` produced a new hostplan bundle where `tiled`
compiles successfully under the current `P=54`, `Mt=22`, `Kt=22`,
`Nt=22` params.

The current Gemma 3 1B transcript remains blocked, not positive parity:
`embed` is still fail-closed before cslc with
`csl_compile_params_infeasible_embed_grid_budget`, and the simulator
receipt remains `kernelIsStub=true`. Non-priority compile failures now
remaining in the driver result are `rope` as
`csl_compile_builtin_shadow`, `attn_decode` as
`csl_compile_color_config_conflict`, and timeout-class `residual`/`gelu`.

Verified:

- `zig build csl-host-plan-tool`
- `zig build test-wgsl`
- `python3 -m unittest bench.tests.test_int4ple_manifest_compile_params_gate bench.tests.test_int4ple_scheduler_readiness bench.tests.test_csl_driver_taxonomy`
- `python3 bench/gates/schema_gate.py`
- `python3 bench/tools/run_doe_csl_int4ple_transcript.py --program-bundle /home/x/deco/doppler/examples/program-bundles/gemma-3-1b-it-q4k-ehf16-af32.program-bundle.json --out bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json --hostplan-bundle-root bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan`

## 2026-04-24 (late+4) — Gemma 3 hostplan compile params reach cslc

Gemma 3 1B Program Bundle hostplan generation now applies governed
manifest compile params to the active simulator-plan path. The stale
`--contract` transcript entry point is no longer the current interface;
the current run used the Gemma 3 1B Program Bundle and wrote the
hostplan bundle under:

- `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/`
- `bench/out/doppler-reference/gemma-3-1b-doe-csl-transcript.json`

Priority-kernel state from
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/simulator-driver-result.json`:

- `attn_head256` compiles with streaming params from
  `solve_attention_streaming`; it no longer reports the previous PE
  memory-exhausted compile failure.
- `lm_head_gemv` compiles with the 2-D lm-head params from
  `lmhead_gemv_compile_params`; it no longer reports
  `csl_compile_uninitialized_param`.
- `embed` is now fail-closed before cslc with
  `csl_compile_params_infeasible_embed_grid_budget`. The 1B vocab row
  shard plus hidden-shard count cannot fit both the per-PE data budget
  and the current HostPlan grid height. This replaces the old huge-fabric
  cslc invocation and preserves the blocker as an explicit receipt.
- `attn_head512` has projected params but is not present as a compile
  target in the current Gemma 3 1B hostplan bundle, so there is no
  simfabric receipt for that target in this run.

`runtime/zig/tools/csl_sdk_driver.py` now records
`compileBlockedReason` targets as `status=blocked` without invoking cslc,
and `run_doe_csl_int4ple_transcript.py` writes
`runtime.compileTimeoutSeconds` into the simulator plan so per-target
cslc hangs become typed `csl_compile_timeout` failures. At that point,
non-priority compile failures recorded in the driver result were:
`tiled` was `csl_compile_undeclared_identifier`, `rope` was
`csl_compile_builtin_shadow`, and `attn_decode` was
`csl_compile_color_config_conflict`. Both simulator-plan fields are
optional, so `schemaVersion` remains unchanged for existing artifacts.

Verified:

- `python3 -m unittest bench.tests.test_int4ple_manifest_compile_params_gate bench.tests.test_int4ple_scheduler_readiness bench.tests.test_csl_driver_taxonomy`
- `python3 bench/gates/schema_gate.py`

## 2026-04-24 (late+3) — first WS4 kernel simfabric execution PASS

`attention_tiled_streaming_sim_runner.py` executed end-to-end against a
compiled streaming-KV bundle and produced a PASSING governed-lane trace:

- kernel: `attention-tiled-streaming`
- config: width=8, head_dim=256, q_len=32, q_len_per_pe=4, block_size=16,
  kv_len=32, kv tiles=2
- runtimePassed: true, runtimeMaxAbsErr = 2.98e-6 (within f32 precision
  vs the numpy Flash Attention reference)
- trace:
  `bench/out/cslc-attn-streaming-probe/simfabric-trace/attn_streaming.trace.json`

This is the first WS4 kernel to flip off `executionStatus=not_implemented`
under the post-refactor streaming contract. The host helper
`run_streaming_tiled_attention` in `bench/runners/csl-runners/common.py`
drove the tile-loop (H2D K/V per block → launch `compute` → after all
tiles launch `finalize` → D2H + concat across width); numerical parity
holds within f32 precision against the numpy reference.

`lmhead_gemv_2d_sim_runner.py` was written against the parallel
`run_fused_gemv_2d` helper but ran into a simulator stall on D2H:
"received length (0 bytes) is not expected (256 bytes), could be a
kernel stall". The D2H expects all width×height PEs to have unblocked,
and the fabric-reduce chain emits `unblock_cmd_stream` via
`send_done_task` on PE 0..N-2 and directly on PE N-1, so all PEs
*should* unblock. The most likely cause is an interaction between the
newly-2-D layout's per-row reduce-chain routing and the async-send
completion protocol (queue 2 was bound to color 4 in the pre-refactor
path; my new `@set_color_config(pe_x, pe_y, reduce_color, …)` inline
calls may be missing a tile-code side `@initialize_queue` on the
sink PE that only runs in the single-row original loop). The refactor
compiles clean; it's the runtime queue handshake that's off. Probe
and compiled bundle are pinned under
`bench/out/cslc-lmhead-2d-probe/` so the next session has a concrete
reproduction.

The embed helper side (your workstream) plus an integration into
`run_doe_csl_int4ple_transcript.py` that invokes the three per-kernel
cs_python runners and aggregates their traces into a single model-level
receipt is the remaining path to flipping the transcript off
`executionStatus=not_implemented`. The attention half of that chain
now has a proven-working first link.

## 2026-04-24 (late+2) — lm_head_gemv_stable 2-D sharding lands

Fourth and final WS4 blocker kernel. `emit_csl_fused.zig:emit` +
`emit_csl_layout.zig:emitFusedGemvLayout` refactored from the 1-D (width
× 1) reduce chain with PE-resident full out_dim weight to a 2-D (width ×
height) layout where `width` shards in_dim (east-west reduce chain) and
`height` shards out_dim. Per-PE weight drops from
`out_dim * num_blocks_per_row * 144` to
`out_dim_per_pe * num_blocks_per_row * 144`. At Gemma 4 E2B manifest
(out_dim=1331, num_blocks_per_row=2, grid=197×84) this is 383 KiB → 4.6 KiB
per PE. Reduce semantics unchanged: per row independent east-west chain.
Defaults (`height=1`, `out_dim_per_pe=out_dim`) preserve the pre-shard
shape when callers have not plumbed the new knobs.

Direct cslc verification (see
`bench/out/cslc-lmhead-2d-probe/probe-result.json`, `--arch=wse3`):

- E2B `width=197,height=84,out_dim=1331,out_dim_per_pe=16,in_dim_per_pe=512,num_blocks_per_row=2` — **Compilation successful**
- 1-D backward-compat `width=4,height=1,out_dim=16,out_dim_per_pe=16,in_dim_per_pe=512,num_blocks_per_row=2` — **Compilation successful**

HostPlan compile-param assembly
(`bench/tools/int4ple_manifest_compile_params.py`) gained
`solve_lmhead_gemv_2d` + `lmhead_gemv_compile_params`. The solver
iterates candidate heights from `grid_height` down to 1; first feasible
(height, out_dim_per_pe) wins. Budget is
`LMHEAD_PE_DATA_BUDGET_BYTES = 32 KiB` (weight + 4× scratch/output/partial
floats), conservative vs the ~48 KiB ceiling the probe exercised.
Solver output at E2B picks `(out_dim_per_pe=16, height=84)` matching the
probe's hand-verified pair.

Schema
(`config/csl-operation-graph.schema.json`) gained
`$defs/hostIoLayoutFusedGemv` with a `dimSharding` block (`outDimPerPe`,
`width`, `height`, `outDimTotal`), namespaced as peer to `embed` /
`attention` so the three kernel workstreams don't collide on merge.

Host helper
(`bench/runners/csl-runners/common.py`) gained `run_fused_gemv_2d`:
tiles activation across width, stages weight shards per (pe_y, pe_x),
launches `compute`, reads D2H back from every (pe_x=width-1, pe_y) sink
PE and concatenates + trims to `out_dim_total`. Matches the existing
`run_streaming_tiled_attention` pattern.

Verified:
  - `zig build` + `zig build test-wgsl` green.
  - `csl-operation-graph` gate green (hostIoLayoutFusedGemv does not
    break existing validation).
  - 20/20 `bench/tests/test_int4ple*` green (shape-based assertions
    from the earlier refactor absorbed the new lm_head params cleanly).
  - Emitter-generated CSL compiles at both E2B 2-D and tiny 1-D shapes.

All four WS4 kernel blockers (embed, attn_head256/512, lm_head_gemv_stable)
now have:
  - emitter refactored off the pre-shard overflow shape
  - matching layout emitter
  - HostPlan compile-param solver with empirical-budget bounds
  - operation-graph schema key
  - host Python helper for the orchestration contract
  - direct-cslc probe receipt pinned under `bench/out/cslc-*-probe/`

The remaining step to flip any of the four receipts from
`executionStatus=not_implemented` to a live simfabric transcript is
integration: `run_doe_csl_int4ple_transcript.py` imports the
`run_streaming_tiled_attention` / `run_fused_gemv_2d` / embed helpers
(and the analogous embed helper when that lands) and invokes them on the
compile targets, then diffs against numpy references for correctness.
That integration is one focused session away; it is not another
multi-week kernel engineering effort.

## 2026-04-24 (late+1) — attn_head256/512 closure plumbing lands

Follow-on to the streaming-KV emitter refactor earlier today. The schema,
HostPlan compile-param assembly, and host Python streaming helper are now
in place. Closure for the simfabric transcript is one live run away.

`config/csl-operation-graph.schema.json` — added
`$defs/hostIoLayoutAttention` with a `kvStreaming` block (`blockSize`,
`qLenPerPe`, `width`, `tileCount`) namespaced as a peer of
`$defs/hostIoLayoutEmbed`, so schema merges with the embed workstream
do not collide. `csl_operation_graph_gate` green.

`bench/tools/int4ple_manifest_compile_params.py` — added
`solve_attention_streaming` and `attention_compile_params`. The solver
picks `(blockSize, qLenPerPe)` from
`(grid_width, head_dim, q_len, kv_len)` subject to the empirical
per-PE budget `ATTN_PE_DATA_BUDGET_BYTES = 20 KiB`, measured from
`bench/out/cslc-attn-streaming-probe/probe-result.json`. Every working
config the probe reported as compiling clean fits the budget; every
failing config was outside it. At the E2B manifest shape the solver
picks `(16, 4)` for head_dim=256 and `(4, 4)` for head_dim=512, matching
the probe's recommended pairs. `attn_head256` / `attn_head512`
compileParams now also emit `q_len_per_pe` and `width` so the kernel's
new params land in the simulator-plan patch.

`bench/tests/test_int4ple_manifest_compile_params_gate.py` and
`bench/tests/test_int4ple_scheduler_readiness.py` — stale fixtures
that predated the embed and attention solvers updated to assert on the
shape invariants the patch must preserve (presence of the new solver
knobs, non-zero coverage, matching sample/lmHead values) rather than
pre-solver numeric equality. 20 test_int4ple* tests green.

`bench/runners/csl-runners/common.py` — added
`run_streaming_tiled_attention(runner, q_global, k_full, v_full, ...)`.
The helper implements the host-side contract: pad q to
`width x q_len_per_pe x head_dim`, H2D once, then per tile H2D the
K/V blocks (padded with zero rows for the final partial tile), launch
`compute`, and after all tiles launch `finalize`. D2H reshape to
`(q_len, head_dim)` with the width-axis concat and trimming of
q-padded rows. Also added `numpy_tiled_attention_reference` for
parity checks against the simulator output. The helper takes
`MemcpyDataType` and `MemcpyOrder` as arguments because those imports
only resolve inside `cs_python`; raising explicitly on absent args
keeps the shared module importable under vanilla python3.

Verified:
  - `zig build` and `zig build test-wgsl` green (attention emitter
    unchanged since the last entry).
  - `csl-operation-graph` gate green (new `$defs/hostIoLayoutAttention`
    does not break existing validation).
  - 20/20 `bench/tests/test_int4ple*` green.
  - Solver-picked pairs for E2B match the direct-cslc probe pairs.

Still outstanding for simfabric transcript closure (both for embed and
attention, orthogonal surfaces):

- Transcript runner (`run_doe_csl_int4ple_transcript.py` or its
  attention-specific sibling) needs to import the
  `run_streaming_tiled_attention` helper and invoke it on the
  `attn_head256` / `attn_head512` compile targets, substituting its own
  weight staging + numpy reference for correctness validation.
- Evidence bundle should capture `kvStreaming.tileCount` and the
  solver-chosen `(blockSize, qLenPerPe)` alongside the compile-param
  patch output so later parity receipts bind the host orchestration
  identity to the compile identity.
- KV-cache residency upstream of the streaming tile window is still
  untouched. That is orthogonal and not blocking the prefill attention
  transcript shape.

## 2026-04-24 (late) — attn_head256/512 streaming KV emitter lands; compile probes green

`emit_csl_attention.zig:emitTiled` rewritten from PE-resident full KV
(`var key: [kv_len * head_dim]f32`, `var val: ...` — 128/256 KiB per PE at
head_dim=256/512) to streaming-KV. New PE-program params: `q_len_per_pe`
(shards q_len across width) and `block_size` (host-streamed tile window,
default 16). K/V storage is now sized as `block_size * head_dim`, so host
rewrites the tile buffers per block and launches `compute` once per tile;
`finalize` normalizes the accumulated output when all tiles have run.
Defaults (`q_len_per_pe=q_len`, `block_size=16`) preserve a usable 1-D
shape when the host has not opted into the streaming contract.

Layout emitter updated in `emit_csl_layout.zig:emitTiledAttentionLayout` to
surface the new params with matching defaults; `kv_len` is removed from
per-tile params (tile window size is `block_size`, iteration count is a
host-side concern).

Feasibility probe at PE budget ~63 KiB
(`bench/out/cslc-attn-streaming-probe/probe-result.json`):

- head_dim=256: `(block_size, q_len_per_pe) = (16, 4)` compiles clean.
  Working region bounded by `block_size ≤ 16` AND
  `(block_size + q_len_per_pe) ≤ ~24`; block_size=32 overflows even at
  q_len_per_pe=2.
- head_dim=512: `(block_size, q_len_per_pe) = (4, 4)` compiles clean.
  block_size=16 overflows at all q_len_per_pe; only block_size≤8 pairs
  fit in budget.

Emitter output verified by direct cslc on the regenerated PE program at
both shapes: `bench/out/cslc-attn-streaming-probe/emittedByDoe.*`. The
unused-entry warnings on `pe_id`/`num_pes` are harmless carry-overs from
the shared layout tile-loop helper; both PEs and host treat them as
metadata.

`zig build` and `zig build test-wgsl` are green. The validator's
`@export_symbol(compute)` structural marker is preserved by keeping the
streaming consumer named `compute`; a second `finalize` export carries
the post-tile normalize.

Not yet this session (remaining WS4-attn closure blockers):

- HostPlan tool must pick `(width, q_len_per_pe, block_size)` from
  `head_dim`, `kv_len`, and available grid, and emit them into the
  simulator-plan `compileParams` for `attn_head256` / `attn_head512`.
  Today it emits `width / head_dim / kv_len / q_len` only.
- `config/csl-operation-graph.schema.json` needs
  `hostIoLayout.attention.kvStreaming` with `blockSize` and
  `qLenPerPe` keys (namespaced so it doesn't collide with the
  `hostIoLayout.embed.chunkedDispatch` keys added by the embed
  workstream).
- Host Python runner (`int4ple_compile_target_sim_runner.py` or its
  attention-specific sibling) needs to loop `ceil(kv_len / block_size)`
  H2D(K_tile) + H2D(V_tile) + launch(compute) dispatches, then one
  launch(finalize), then D2H the output shards across width PEs and
  concatenate by q position.
- KV cache residency upstream of the tile window: the existing
  `kv_write`/`kv_read` emitters still allocate full per-PE KV memory;
  they are orthogonal to this streaming tile design but block full-model
  parity until wired.

Silent-NaN hazard noted in `emit_csl_attention.zig` header: calling
`compute` without first populating the K/V tile buffers reads zeroed
memory and produces numerically wrong (but non-crashing) attention
output. The emitter cannot detect this; host orchestration owns tile
staging.

## 2026-04-24 (afternoon) — embed chunked-dispatch emitter lands; compile probe green

`emit_csl_gather.zig` rewritten from 1-D pre-chunking to 2-D chunked
dispatch. New PE-program params: `pe_x`, `pe_y`, `hidden_per_pe`,
`tokens_per_chunk`. Per-PE buffers now size as
`[tokens_per_chunk]u32`, `[rows_per_pe * hidden_per_pe]f32`,
`[tokens_per_chunk * hidden_per_pe]f32`. Defaults
(`hidden_per_pe=hidden_size`, `tokens_per_chunk=num_tokens`) preserve
the pre-chunking 1-D behavior when `height=1`.

Layout emitter updated in `emit_csl_layout.zig:emitGatherLayout` to
surface the new params with matching defaults.

Direct cslc probe on the fresh emitter output at E2B per-PE shapes
(`width=32,height=8,hidden_size=1536,hidden_per_pe=192,rows_per_pe=16,
num_tokens=32,tokens_per_chunk=16`): **compile succeeded**. Second
probe at `width=256,height=8` (2048 PEs) also succeeded. The original
pre-chunking emitter output still fails with
`integer value 49152 cannot be coerced to type 'i16'` on the same
E2B shape, confirming the fix is a genuine kernel change rather than
a probe-configuration coincidence. Evidence:
`bench/out/cslc-embed-memory-probe/probe-result.json` plus the
pinned `pe_program.csl` and `layout.csl`.

Per-PE footprint at `(hidden_per_pe=192, rows_per_pe=16,
tokens_per_chunk=16)` is `indices 64B + table 12 KiB + output 12 KiB
= ~24 KiB`, well under the ~48 KiB `.data.hi` budget measured at
`.blocked_ut_ival = 0xFC04`.

`zig build` and `zig build test-wgsl` are green. No existing test
exercised `emit_csl_gather.emit` with specific CSL-output expectations,
so the emitter rewrite is source-compatible with the test surface.

Not yet this session (remaining WS4-embed closure blockers — see
`bench/out/cslc-embed-memory-probe/probe-result.json` for the
authoritative list):

- HostPlan tool (`emit_csl_host_compile_source.zig` path) must pick
  `(width, height, hidden_per_pe, tokens_per_chunk)` that covers vocab
  and fits per-PE budget, and emit them into the simulator-plan
  `compileParams` for `embed`. Today it emits `width/height/
  hidden_size/rows_per_pe/num_tokens` only.
- `config/csl-operation-graph.schema.json` needs
  `hostIoLayout.embed.chunkedDispatch` with `tokens_per_chunk` and
  `hidden_shardCount` keys.
- Host Python runner (in `bench/tools/run_doe_csl_int4ple_transcript.py`
  or an embed-specific runner) needs to dispatch
  `ceil(num_tokens / tokens_per_chunk)` chunks and concatenate per-
  column slices across height PEs to reassemble the
  `[num_tokens, hidden_size]f32` output.
- Weight staging in `emit_csl_host_runtime.zig` is currently 1-D
  (`pe_start:pe_end`). It needs a 2-D (row-shard, hidden-shard)
  mapping so each PE receives the slice of `embed_tokens.weight`
  that matches its `(pe_x, pe_y)` position.

Silent-drop hazard noted in `emit_csl_gather.zig` header: until the
host runner implements chunked iteration, calling the emitter with
`tokens_per_chunk < num_tokens` produces only the first chunk of
output and drops the rest. The kernel cannot detect this; it is a
host-orchestration contract.

## 2026-04-24

Direct cslc verification of the 4 manifest-scale blockers (see stderr logs
under `bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-hostplan/
compile/driver-logs/*.cslc.stderr.log`). The i16 array-dimension error on
`embed` and `lm_head_gemv_stable` is the surface symptom; the architectural
blocker for all 4 is per-PE memory. Direct-probe numbers at PE budget
~63 KiB (`.blocked_ut_ival` at 0xFC04):

- `embed` at `num_tokens=32, hidden_size=1536, rows_per_pe=16`:
  output 192 KiB + table 96 KiB per PE. Both exceed budget. 2D array
  syntax fixes the i16 error (confirmed by `/tmp/test-2d-array` probe)
  but does not help the memory overflow. Fix requires 2D grid with
  `hidden_per_pe` sharding + host-chunked dispatch.

- `lm_head_gemv_stable` at `width=197,height=1,out_dim=1331,
  in_dim_per_pe=512, num_blocks_per_row=2`:
  weight 383 KiB per PE (`out_dim * num_blocks_per_row * 144`). Fix
  requires 2D layout with `out_dim_per_pe = ceil(out_dim/height)` so
  weight drops to 4.6 KiB at grid 197×84.

- `attn_head256` / `attn_head512`: .bss 147 KiB / 294 KiB per PE. Full
  KV cache is PE-resident. Fix requires host-streamed K/V tiles instead
  of the current PE-resident `key`/`val` arrays.

Architectural fix plans landed as header-level TODOs in the emitters:
`runtime/zig/src/doe_wgsl/emit_csl_gather.zig`,
`runtime/zig/src/doe_wgsl/emit_csl_fused.zig`,
`runtime/zig/src/doe_wgsl/emit_csl_attention.zig`. Each names touch
points (emitter, layout, classifier, host runner, operation-graph
schema) and the partial-fix hazard.

Reachable-infrastructure finding: SDK container runs locally and reports
real cslc diagnostics; prior classification `csl_compile_container_runtime_blocked`
is stale on this host.

## 2026-04-23

- `docs/doppler-ingest.md` now explicitly frames TSIR as the planned lowering
  layer between Doe WGSL IR and backend artifacts, and narrows HostPlan to the
  runtime orchestration boundary for the CSL lane. This closes one live doc
  drift between the Doppler ingest boundary, the TSIR plan, and the current
  CSL migration story.

## Current state

- The forward architecture for replacing classifier/template CSL lowering with
  parity-oracle-first TSIR lowering is documented in
  `docs/tsir-lowering-plan.md`. Phase A compiler surface is landed (schema,
  digests, frontend, planner, reference interpreter, and mechanical skeleton
  emitters for five backends including a TSIR-to-CSL skeleton; see
  [`docs/status/tsir.md`](./tsir.md)), but the live CSL lane still uses the
  classifier/template route — the TSIR-to-CSL skeleton emits contract text
  rather than executable kernels.
- The INT4 PLE CSL lane now applies manifest compile params to the live
  simulator plan and records the result at
  `hostPlanBundle.manifestCompileParamApplication`.
- The fresh simulator driver result on this host compiles 10 of 14 targets at
  manifest scale and fails 4 with real kernel-level diagnostics:
  - `embed`
  - `lm_head_gemv_stable`
  - `attn_head256`
  - `attn_head512`
- The blocker is kernel architecture, not SDK discovery, tool lookup, or
  receipt plumbing.

## Active blockers

- `embed` still materializes per-PE state that exceeds CSL array-dimension and
  PE-memory limits at manifest scale.
- `lm_head_gemv_stable` still materializes per-PE weight/scratch state that
  exceeds manifest-scale limits.
- `attn_head256` and `attn_head512` still allocate oversized per-PE K/V/Q/O
  backing arrays and scratch.
- The real CSL transcript lane cannot close until those kernels are redesigned
  for bounded per-PE residency.

## Landed infrastructure

- Shared execution contract wiring between Doppler source artifacts, HostPlan,
  transcript receipts, and parity receipts.
- Manifest compile-param projection and apply path for the live transcript
  producer.
- HostPlan executor validator, execution-plan receipt, target-session probe,
  and bootstrap/runtime scaffolding.
- Fail-closed promotion gates for manifest compile params and transcript
  readiness.

## Ground truth

- SDK access is no longer the primary blocker on this host.
- `cslc` runs and produces real linker/compiler diagnostics.
- The missing work is bounded to kernel redesign plus the downstream transcript
  executor path that consumes those kernels.

## Use this shard for

- Cerebras SDK / CSL runtime status
- INT4 PLE compile/runtime blockers
- HostPlan executor status
- Simulator and hardware promotion status
