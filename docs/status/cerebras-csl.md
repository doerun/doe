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
