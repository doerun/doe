# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

Current queue summary lives in `docs/cerebras-north-star.md`. Older entries
below are historical status, including the WS4 memory-blocker framing that was
later narrowed by the Gemma 3 1B compile fixes. The active execution blocker is
the tiled SUMMA `launchIndex=2` host D2H stall, not the earlier embed/lm-head/
attention compile blockers.

## 2026-04-25 (afternoon) — 31B-primary pivot, R2 verdict closure, singularity wrapper, L1+L61 receipts, overnight matrix

A multi-decision turn. Pinning here so tomorrow's session does not re-derive.

### Strategic reframe

- **31B is the product target; E2B is the test fixture.** Existing E2B claims
  (real-weight smoke, manifest-shape evidence, attention-core diagnostic) stay
  valid in CLAIM_SCOPE — the demotion is in narrative ordering, not in claim
  substance. Recorded in `docs/cerebras-north-star.md` Queue + 31B-first
  execution plan sections.
- **Bundle path (b) breaks the simfabric-vs-hardware chicken-and-egg.** Path
  (b) (Cerebras-assisted bundle run) does NOT require simfabric parity to
  unlock; the existing bundle is sufficient to circulate. R2-6 does NOT gate
  R2-10; R2-7 parity bind is execution-target-agnostic. The 14-failure bundle
  gate regression is real but not load-bearing for the 31B hardware ask.

### R2 closure verdicts

R2-4 SDK 2.10 D2H sweep against canonical
`csl-extras-202604101435-6/examples/benchmarks/gemm-collectives_2d/`
(`bench/runners/r2_4_summa_sweep.py`):

| Cell | P | Mt | Total C | Run sec | Result |
|------|---|----|---------|---------|--------|
| baseline | 4 | 14 | 12.5KB | 3.9 | success |
| tile-up | 4 | 22 | 30KB | 9.7 | success |
| count-up-1 | 8 | 14 | 50KB | 15.1 | success |
| count-up-2 | 16 | 14 | 197KB | 92.2 | success |
| count-up-3 | 32 | 14 | 787KB | 948.1 | success (20-min timeout) |
| doe-exact | 54 | 22 | 5.6MB | extrapolated ~110min | timed out |

Findings: trigger axis is PE-count P; per-PE bytes scale linearly when P held
constant; scaling is ~O(P^3) per doubling (P=8→16: 6.1×; P=16→32: 10.3×). NOT
a deadlock; just simfabric superlinear scaling. R2-1's earlier "kernel
completed compute, host D2H hangs" framing was wrong; both compute and d2h
are gated on simfabric throughput. R2-2 (timeout probe) closed insufficient,
not failed. R2-3 (SUMMA fence audit) closed: Doe matches canonical
structurally. R2-4 closed with the sweep above. R2-5/R2-6/R2-7 relabeled to
"Control-lane diagnostic" so the Queue (R2 demoted) and per-item sections
agree.

### Singularity wrapper landed

Root-caused a class of bundle-gate failures to `cs_python` on this host
preferring `--direct-rootfs` mode, which does NOT bind `/cbcore` for cslc
subprocesses. Paint flow then fails with `Could not find source code for
"/cbcore/src/sdk/ucode/io_port.csl"`. Fix:

- `runtime/zig/tools/cs_python_singularity.sh`: Doe-local wrapper that
  invokes `singularity exec` with the canonical SIF binds. Falls back to
  the SDK default cs_python when singularity is not available.
- `runtime/zig/tools/csl_sdk_driver.py`: `infer_cs_python_from_cslc` prefers
  the wrapper when both singularity (or apptainer) and a SIF are available.
- `bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py`: same
  preference inside its `select_cs_python`.

Validation: `gemma4-e2b-manifest-shape-attention-core` flipped FAIL → PASS
under the wrapper. The 14-failure bundle gate cluster splits into two:
paint-flow (singularity-fixable, attention-core type) and stale-fixtures
(regen-fixable, int4ple-blocked-transcript type with missing
`gemma-3-1b-doe-csl-hostplan/host-plan.json` and
`doppler-program-bundle.json`). The patch addresses the first cluster, not
the second.

### 31B simfabric receipts: L1 and L61 landed

First-ever full Gemma 4 31B 61-layer execution end-to-end on simfabric.

| Cell | numLayersChained | Compile | Run | numericalParity | Receipt |
|------|------------------|---------|-----|-----------------|---------|
| L1 | 1 | 262.2ms | 7167.9ms | passed=True, max_abs_err=0 | `bench/out/r3-1-31b-l1-dry/trace.json` |
| L61 | 61 | 237.5ms | 395310.3ms | passed=True, max_abs_err=0 (all 61 layers) | `bench/out/r3-1-31b-l61-smoke/trace.json` |

Per-layer L61 timing flat-consistent: min 4.8s, mean 6.5s, max 7.9s. No
SUMMA-style scaling pathology in the smoke shape — the smoke's bounded
per-PE byte count keeps simfabric viable at L61 / 61 layers. Captured under
R3-1 done-when in `docs/cerebras-north-star.md`; hardware-side equivalents
remain pending R2-10 / endpoint access.

### Overnight matrix infrastructure landed

User-authored `bench/runners/overnight_evidence_matrix.py` (289 LOC):
bounded-concurrency, lane-aware (webgpu_heavy=1, csl_heavy=2, light=8),
per-cell isolation, resume that skips already-succeeded cells, JSON-driven
matrix, 5-state status taxonomy including `missing_receipt` (catches "exit 0
but no receipt written"), full test coverage. Agent-authored
`bench/tools/generate_overnight_31b_matrix.py` templates the standard 31B
sweep into the orchestrator's matrix shape with stable zero-padded IDs and
per-cell `expectSuccessReceiptPath` paths under `cells/<id>/`.

### TSIR-as-truth incremental progress

Commit `212a46868` adds `tryResidualAdd` and `tryGeluGated` to the reference
interpreter (`runtime/zig/src/tsir/reference_interpreter.zig`). 7 of 11
transcript bodyOps now have a host-side parity oracle (was 5). `kv_write` /
`kv_read` deferred — the read-write binding semantics need a convention pick
for whether `inputs[]` extends to read-write slots or a separate
`prior_state[]` parameter is added to `run()`. R1-1 done-when updated.

### WebGPU re-run finding (separate thread)

`bench/tools/run_doe_webgpu_shared_contract.py` re-run for Gemma 3 1B today
flipped to `status=failed` with blocker `Logits has no finite candidate
logits after masking the pad token` — NaN/Inf upstream in decode, NOT the
SPIR-V emitter issue B1/B2 fixed earlier this cycle. The `-real` path
(Apr 24 18:19, post-B2) still succeeds with full 8-step decode, so the
divergence is in HOW the shared-contract wrapper invokes the exporter
(`--runtime-profile profiles/production` + capability-aware policy).
Distinct triage thread, not blocking 31B work.

### What landed in tonight's overnight sweep

`bench/out/overnight/20260425T175736Z/` — 12 cells (8 csl_heavy + 4 light),
Lane A intentionally deferred behind `--include-lane-a` flag pending Doppler
31B workflow verification (now resolved in the generator with the canonical
`run-program-bundle-reference.js --manifest --model-dir --conversion-config
--surface node --prompt --max-tokens --report-out --out` invocation;
re-runnable tomorrow with `--include-lane-a`). Critical evidence pieces:
`csl-31b-L061-size1024` (independent receipt for L61 bundle citation),
`csl-3-1b-L001-decode-truncated-size1024` (first ever exercise of
`kv_write`/`kv_read` in any Doe receipt via `--max-layers 1` truncation in
`bench/tools/run_doe_csl_int4ple_transcript.py`).

## 2026-04-25 — Structured compile-target metadata first slice

The HostPlan executor now has a structured metadata path for compile-target
bindings, so fresh Zig-emitted simulator plans no longer require Python to
reparse `layout.csl` and `pe_program.csl` text for the kernels covered by the
metadata contract.

Landed in this entry:

- `config/doe-wgsl-simulator-plan.schema.json`: `compileTargets[]` now accepts
  `metadata` with target phase, binding shape, per-PE shape,
  staging/detile transforms, and weight-source hints.
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`,
  `runtime/zig/src/doe_wgsl/emit_csl_simulator.zig`, and
  `runtime/zig/src/csl_host_plan_tool.zig`: Zig compile targets can carry
  structured binding metadata, and simulator-plan emission writes it for
  `reduction`/`rms_norm`, `residual`, `gelu`, and `tiled_matmul`.
- `bench/runners/csl-runners/int4ple_binding_metadata.py` plus
  `int4ple_hostplan_execution_plan.py`: Python materialization consumes the
  structured metadata first and falls back to CSL text parsing only for legacy
  targets. The tiled path still enriches metadata with concrete SUMMA
  dimensions and preserves nested q4k/f16/bf16 staging transforms.
- `bench/runners/csl-runners/int4ple_runtime_scheduler.py`: residual and GELU
  dataflow symbols now match the real WGSL bodies (`input`/`residual`/`output`
  for residual, `input`/`output` for GELU) instead of the previous shared
  elementwise stub symbols.

Validation:

- `python3 -m unittest bench.tests.test_int4ple_binding_metadata
  bench.tests.test_int4ple_scheduler_readiness
  bench.tests.test_csl_host_plan_kernel_patterns` passed.
- `python3 -m unittest bench.tests.test_csl_gelu_wgsl_backed_fixture` passed.
- `python3 -m unittest bench.tests.test_config_schemas` passed.
- `zig build test-wgsl` passed; only existing TSIR line-limit allowlist notices
  were printed.
- `python3 bench/gates/csl_operation_graph_gate.py` passed.
- `git diff --check` passed.

Still not claimed:

- `python3 bench/gates/schema_gate.py` is blocked on this checkout by missing
  local `bench/out/...` evidence artifacts, not by the metadata schema; the
  focused schema/unit coverage above is the current local validation.
- Full simulator evidence still needs regeneration before this becomes a
  numeric-parity claim. The permanent evidence gate still needs to distinguish
  HostPlan plumbing success from transcript/logit parity success.
- The next CSL status update should split this shard by subdomain before it
  approaches the 1200-line live shard cap.

## 2026-04-25 (cycle 20) — Live HostPlan kv_read now sourced from TSIR (fourth ownership transfer; kv_cache file fully migrated)

Item 2 cycle-20 slice. Symmetric counterpart to cycle 19's
`emitWrite` swap. The hand-written body of
`emit_csl_kv_cache.emitRead` is gone. Same recipe: extract
WGSL-derived storage names from `module` + `info`, build a TSIR
SemanticFunction with bindings named to match those exact
symbols, delegate through `emitWithConfig` with `var_prefix=""`.

The `kv_read` body has no state buffer (no `decode_position`);
the read range is supplied by the host plan via `read_start` /
`read_len` params. TSIR's `emitCslKvRead` already declares those
params with the correct defaults (`read_start: i16 = 0;`,
`read_len: i16;`).

`emit_csl_kv_cache.zig` is now fully TSIR-driven on both halves
of the KV-cache lifecycle. The hand-maintained-emitter surface
in this module is empty.

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–19).
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.

Loop tally for live ownership transfers from hand-written
emitters to TSIR-driven CSL: **8 kernel bodies** (residual /
residual_prefill / residual_decode + gelu / gelu_prefill /
gelu_decode + kv_write + kv_read).

Hand-maintained surface remaining for Item 2: `emitRmsNormPe` in
`emit_csl_semantic_ops.zig` is the last entry. The TSIR
`rms_norm` body needs a Gemma `1+w` offset Config knob (or a
body-level flag) before swapping; the live hand-written body
emits `output[idx] = input[idx] * inv_rms * (1.0 + weight[idx])`,
where the `1.0 +` is the Gemma offset. TSIR's current emitter
uses the standard `inv_rms * scale[d]` form. Adding the offset
is a contained Config addition similar to `chunk_size_default`.

## 2026-04-25 (cycle 19) — Live HostPlan kv_write now sourced from TSIR (third ownership transfer)

Item 2 cycle-19 slice. Cycle 16's recipe applied to
`emit_csl_kv_cache.emitWrite`. The hand-written body — including
its `pe_id` / `num_pes` unused params, separate
`emitDecodePositionState` call, and module-driven storage-pointer
loop — is gone. The live wrapper extracts the WGSL-derived
storage-binding names from `module` + `info`, threads them into
a TSIR `SemanticFunction` (binding names `kp` / `vp` / `kc` /
`vc` from the WGSL globals plus the literal `position` for the
runtime state buffer), and asks TSIR to emit with no `tsir_` var
prefix.

The exported symbol contract is preserved:
`@export_symbol(<kp>_ptr, "<kp>")` etc. with the WGSL global
names, plus `@export_symbol(position_ptr, "position")` for the
decode-position state buffer. Internal var names differ from the
prior hand-written body (TSIR uses the binding name as the var
name; live used `decode_position` as a separate hardcoded var
name), but those are not part of the host plan binding contract.

This is the first ownership transfer outside
`emit_csl_semantic_ops.zig` — the `emit_csl_kv_cache.zig`
module's emitWrite is now a thin TSIR wrapper. `emitRead` remains
hand-maintained; symmetric swap is the natural next slice.

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–18).
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.

Note: the `kv_write` pattern is not in the gemma-3-1b HostPlan
target set so this swap doesn't affect that simulator regen.
Models that DO use kv_write (KV-cache attention variants outside
the gemma-3-1b fused-attention path) will get TSIR-driven CSL.

Loop tally for live ownership transfers from hand-written
emitters to TSIR-driven CSL: **7 kernel bodies** (residual /
residual_prefill / residual_decode + gelu / gelu_prefill /
gelu_decode + kv_write).

## 2026-04-25 (cycle 18) — cerebras-csl shard split (cycles 7–15 + late+16–21 → archive)

Item 6 cycle-18 slice. The live shard hit 1171 lines after cycle 17's
status entry — 29 line headroom against the 1200-line cap. Cycles 7
through 15 plus the earlier late+16 through late+21 history moved to
`archive/2026-04-25-loop-cycles-7-to-15.md` (968 lines). The live
shard now keeps cycles 16 + 17 inline (the live ownership-transfer
milestones) plus the steady-state sections.

Live shard: 1171 → 219 lines after this entry. Archive file: 968
lines.

This is the second split in this loop — the first happened in cycle
3 when the late+18 / late+19 entries pushed the shard over. The
archive file references in the live shard now form a chain:
`2026-04-25-loop-cycles-7-to-15.md` (this split) →
`2026-04-24.md` (cycle 3 split) → older monthly archives.

Validation: no code changes, no test runs needed.

## 2026-04-25 (cycle 17) — Live HostPlan gelu_gated now sourced from TSIR (second ownership transfer)

Item 2 cycle-17 slice. Cycle 16's recipe applied to
`emitGeluPe`. The hand-written gelu body is gone; `compile/gelu/`,
`compile/gelu_prefill/`, and `compile/gelu_decode/` pe_program.csl
files are now generated by TSIR's `emitCslGeluGated` path with
`var_prefix=""` and `chunk_size_default=1024`.

The TSIR `gelu_gated` body gained saturation clamping
(`if (inner < ±15.0) inner = ±15.0;`) to preserve the prior
hand-written numerical behavior. The live wrapper builds a
SemanticFunction with bindings named `gate` / `input` / `output`
(matching the live exports the host plan binding map expects).

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–16). The TSIR
  test for `gelu_gated` now also asserts on the clamping lines.
- `csl_sdk_driver.py simulator-plan.json`: **17 / 17 compile
  succeeded**, all 3 residual variants AND all 3 gelu variants
  succeed.
- Schema gate, CSL + TSIR Python tests: all green.

Loop tally for live ownership transfers from
`emit_csl_semantic_ops.zig` to TSIR-driven CSL: **6 kernel
bodies** (residual / residual_prefill / residual_decode +
gelu / gelu_prefill / gelu_decode). Remaining hand-maintained
in this file: `emitRmsNormPe` (TSIR `rms_norm` body needs a Gemma
`1+w` offset Config knob). And in `emit_csl_kv_cache.zig`:
`emitWrite` and `emitRead` (TSIR `kv_write`/`kv_read` ready).

## 2026-04-25 (cycle 16) — Live HostPlan residual_add now sourced from TSIR (first ownership transfer)

Item 2 cycle-16 slice. The hand-written body of
`emit_csl_semantic_ops.emitResidualPe` is gone. The live HostPlan
residual / residual_prefill / residual_decode pe_program.csl files
are now generated from a TSIR `SemanticFunction` with body op
`residual_add`, dispatched through
`tsir.emit_kernel_body.emitWithConfig(.., .csl, &.{ .var_prefix
= "", .chunk_size_default = 1024 })`. This is the first time a
production HostPlan kernel's CSL comes out of the TSIR contract
emitter rather than a hand-maintained per-kernel body in
`emit_csl_semantic_ops.zig`.

Landed:

- `runtime/zig/src/tsir/emit_kernel_body.zig`: `Config` extended
  with `chunk_size_default: ?u32 = null`. New helper
  `writeCslChunkSizeParam` emits either `param chunk_size: i16;`
  (default null preserves existing behavior) or `param chunk_size:
  i16 = <value>;` when set. Wired through `emitCslResidualAdd` and
  `emitCslGeluGated`.
- `runtime/zig/src/doe_wgsl/emit_csl_semantic_ops.zig`: added
  imports for `tsir/emit_kernel_body.zig` and `tsir/schema.zig`.
  `emitResidualPe`'s 30-line hand-written body replaced with a
  SemanticFunction construction (bindings `a` / `b` / `output`,
  body op `residual_add`) plus a TSIR delegation through an
  `ArrayList(u8)` writer (TSIR helpers' error set is
  Allocator.Error-shaped, so `FixedBufferStream`'s NoSpaceLeft
  doesn't fit). The live wrapper sets
  `chunk_size_default = 1024` to match the prior hand-written
  default — the elementwise layout doesn't forward `chunk_size`
  through `@set_tile_code`, so cslc raises
  `csl_compile_uninitialized_param` without it.

Why a default was needed: the live elementwise `layout.csl` only
forwards `.memcpy_params` to pe_program. Top-level
`--params=chunk_size:N` from the cslc command flows to the layout
module, where it's logged as "externally provided initializer:
chunk_size: unused entry in module instantiation" because the
layout doesn't declare `chunk_size`. The pe_program ran on its
hand-written `param chunk_size: i16 = 1024;` default. Mirroring
that default in the TSIR-emitted output is the minimal-change
swap that preserves cslc's compile path.

Validation evidence:

- `zig build test-wgsl`: 963 / 964 passed. Same single
  pre-existing `reduction pattern` test failure as cycles 9–15.
  The live `host compile source` test that asserts
  `output[idx] = a[idx] + b[idx];` substring on the residual
  pe_program continues to pass — the TSIR-emitted output produces
  this byte-equivalent line.
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- End-to-end: `csl_sdk_driver.py simulator-plan.json` against the
  regenerated artifacts compiles **17 / 17** targets. All three
  residual variants succeed:
    `residual succeeded`,
    `residual_prefill succeeded`,
    `residual_decode succeeded`.

Item 2 hand-maintained surface remaining in
`emit_csl_semantic_ops.zig`:

- `emitGeluPe` (TSIR has the `gelu_gated` body since cycle 10;
  same swap pattern as residual but with `gate` / `input` /
  `output` bindings).
- `emitRmsNormPe` (TSIR has `rms_norm` since the original Phase A
  surface; the live body has the Gemma `1+w` offset which the
  TSIR `rms_norm` body does not yet model — need a Config knob or
  a body-level flag before swapping).
- `emit_csl_kv_cache.emitWrite` and `emitRead` (TSIR has
  `kv_write` / `kv_read` since cycles 11–12; live binding map
  expects `kp` / `vp` / `kc` / `vc` symbol names which differ
  from TSIR's `key_projection` / `value_projection` /
  `key_cache` / `value_cache` — same `binding.name` parameterization
  works).

Each of these is now a tractable next-cycle slice using the same
recipe this cycle established.

**Older 2026-04-25 loop entries (cycles 7 through 15) and the late+16
through late+21 entries from the start of this loop have been archived
to [`archive/2026-04-25-loop-cycles-7-to-15.md`](archive/2026-04-25-loop-cycles-7-to-15.md).
The earlier 2026-04-24 history is at
[`archive/2026-04-24.md`](archive/2026-04-24.md). The live shard keeps
cycles 16 onward inline.**

## Current state

- The forward architecture for replacing classifier/template CSL lowering with
  parity-oracle-first TSIR lowering is documented in
  `docs/tsir-lowering-plan.md`. Phase A compiler surface is landed (schema,
  digests, frontend, planner, reference interpreter, and mechanical skeleton
  emitters for five backends including a TSIR-to-CSL skeleton; see
  [`docs/status/tsir.md`](./tsir.md)). The TSIR-to-CSL emitter has executable
  bodies for `fused_gemv`, `rms_norm`, `gather`, `residual_add`,
  `gelu_gated`, `kv_write`, and `kv_read`; the live CSL lane still routes
  through the classifier/template + `emit_csl_semantic_ops.zig` path for
  those kernels rather than through the TSIR emitter — the wiring switch is
  the open Item-2 work.
- The INT4 PLE CSL lane now applies manifest compile params to the live
  simulator plan and records the result at
  `hostPlanBundle.manifestCompileParamApplication`.
- The fresh simulator driver result on this host compiles **17 of 17**
  compile targets at manifest scale (embed, rmsnorm, rmsnorm_prefill,
  rmsnorm_decode, tiled, rope, attn_head256, residual, residual_prefill,
  residual_decode, gelu, gelu_prefill, gelu_decode, gemv, attn_decode,
  lm_head_gemv, sample). Source of truth:
  `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/trace.json.driver-result.json`.
- Runtime advances through `embed` (chunked dispatch, 6 sublaunches succeed
  in launch[0]) and `rmsnorm_prefill` (launch[1] succeeds end-to-end); was
  in `tiled` q_proj output memcpy_d2h when the 600s wallclock timeout hit.
  Source of truth:
  `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/simulator-evidence.json`.
- The blocker is no longer kernel architecture — the four kernels previously
  flagged (`embed`, `lm_head_gemv_stable`, `attn_head256`, `attn_head512`)
  all compile cleanly and at least `embed` runs cleanly under the BF16
  layernorm-broadcast fix landed late+18 / cycle 7. Open work is now the
  simulator wallclock vs simfabric per-launch cost, the TSIR-to-live-path
  wiring, and the parity-comparison data the simulator-evidence gate
  cannot yet produce.

## Active blockers

- Simulator wallclock: the 600s default
  `INT4PLE_RUNTIME_RUNNER` timeout drains in three launches (embed +
  rmsnorm_prefill + tiled-in-progress) for the gemma-3-1b regen. Either
  raise the timeout to a value matched to per-kernel simfabric cost, or
  audit embed's chunked-dispatch ROI (6 sublaunches × ~33 s each) before
  asking the simulator to traverse the full prefill + decode tail.
- TSIR live-path wiring: the live HostPlan still routes through
  `emit_csl_semantic_ops.zig` and `emit_csl_kv_cache.zig` for the seven
  ops the TSIR emitter now covers. Switching the live path through TSIR
  needs symbol-export reconciliation (live exports `a` / `b` vs TSIR
  `summand_a` / `summand_b`, etc.) and bootstrap fixtures the
  `tsir-real-entries` directory does not yet carry for these ops.
- Numeric parity: the `csl_simulator_evidence_gate` reports
  `numericParity.status = unknown` because no Doppler reference logits /
  KV digests are wired into the comparison path. Until that source is
  attached, plumbing-pass is the strongest signal the gate can emit.
- Stale doc assertion: the `reduction pattern` test in
  `runtime/zig/src/doe_wgsl/emit_csl_host_compile_source.zig` asserts
  `i < hidden_size` and `@range(u32, 64)` — both belong to the old
  WGSL-derived reduction lowering. The semantic-emitter rmsnorm replaces
  the loop with `for (@range(i16, hidden_size))` and inlines the Gemma
  `1+w` offset directly. The test fails in `zig build test-wgsl` and is
  unrelated to any active code change in this loop.

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
