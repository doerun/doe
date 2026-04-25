# Doe status archive: Cerebras and CSL — 2026-04-25 loop cycles 7 through 15 plus late+16 to late+21

This archive holds dated history entries previously kept inline in
`docs/status/cerebras-csl.md`. They were moved here when the live shard
crossed its 1200-line cap during the long-term work loop.

Do not add new live status entries here. New status belongs in
[`../cerebras-csl.md`](../cerebras-csl.md).

## 2026-04-25 (cycle 15) — TSIR CSL emitters take a Config (var_prefix); bare-prefix output matches live byte-for-byte

Item 2 cycle-15 slice. Cycle 14 made TSIR emitters honor
`binding.name`. The live `emit_csl_semantic_ops.emitResidualPe`
output uses bare `a` / `b` / `output` var names; TSIR's default
output uses `tsir_a` / `tsir_b` / `tsir_output`. The substring
test in `emit_csl_host_compile_source.zig` line 561 asserts
`output[idx] = a[idx] + b[idx];` literally, so a TSIR-driven swap
of the live path needed a way to drop the `tsir_` prefix without
breaking other TSIR callers' output (which the existing 4 op
tests pin on).

Landed:

- `runtime/zig/src/tsir/emit_kernel_body.zig`: new public
  `Config { var_prefix: []const u8 = "tsir_" }` and
  `emitWithConfig(writer, func, backend, *const Config)`. Existing
  `emit(...)` keeps its signature and forwards a `&default_config`
  so all current callers see byte-identical output. The four CSL
  emitters and their three helpers (`writeCslBufferArray`,
  `writeCslBufferPointer`, `writeCslExportSymbol`) thread the
  prefix through.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: new
  test `tsir csl residual_add emitWithConfig var_prefix=''
  produces bare names`. Constructs a SemanticFunction with
  bindings named `a` / `b` / `output`, calls `emitWithConfig` with
  `var_prefix=""`, and asserts the output contains:
    - `var a: [chunk_size]f32 = @zeros([chunk_size]f32);` etc.
    - `output[idx] = a[idx] + b[idx];` (matches the live path's
      loop body byte-for-byte)
    - `@export_symbol(a_ptr, "a");` etc.
  And — load-bearing — `expectNotContains(csl, "tsir_a")` to
  prove the prefix is fully gone in this mode.

This is the structural completion of the live-swap unblock. Cycle
16's slice can replace `emit_csl_semantic_ops.emitResidualPe`'s
hand-written body with a SemanticFunction construction +
`tsir.emit_kernel_body.emitWithConfig(..., .csl, &.{ .var_prefix
= "" })` call, with the host_compile_source residual_add test
continuing to pass on its existing substring assertion.

Validation:

- `zig build test-wgsl`: 963 / 964 passed. Only the pre-existing
  unrelated `reduction pattern` test still fails.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 follow-up after this slice: actually flip
`emit_csl_semantic_ops.emitResidualPe` to delegate to TSIR. The
remaining cosmetic difference (live emits `param chunk_size: i16
= 1024;` with default; TSIR emits `param chunk_size: i16;`) is
either a Config knob (`default_param_value`) or accepted because
the host plan compile params bind `chunk_size` at cslc time
either way. Cycle 16 should make the call.

## 2026-04-25 (cycle 14) — TSIR CSL emitters now parameterize var + export naming via binding.name

Item 2 cycle-14 slice. The four executable TSIR-to-CSL emitters
added earlier in this loop (residual_add, gelu_gated, kv_write,
kv_read) now derive their CSL variable and exported-symbol names
from `BufferBinding.name` instead of hardcoding the role string.
This is the hook the live HostPlan path needs to swap through TSIR
without changing downstream symbol bindings — bindings can be named
to match whatever the live emitter exports today (e.g. `a`, `b`,
`output` for residual rather than `summand_a`, `summand_b`,
`output`) and the TSIR output will use those names.

Landed:

- `runtime/zig/src/tsir/emit_kernel_body.zig`: new helpers
  `writeCslBufferArray`, `writeCslBufferPointer`,
  `writeCslExportSymbol`. The four executable CSL emitters
  (`emitCslResidualAdd`, `emitCslGeluGated`, `emitCslKvWrite`,
  `emitCslKvRead`) now route var and export emission through these
  helpers, threading `binding.name` through. The `tsir_` internal
  prefix on var names is preserved — only the exported symbol name
  changes when the caller picks a different `binding.name`.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: new
  test `tsir csl residual_add honors binding.name for var + export
  naming` constructs a SemanticFunction with bindings named `a` /
  `b` / `output` and verifies the emitter exports those names
  instead of the role-default `summand_a` / `summand_b`.

The four pre-existing op tests (which use binding.name == role
name in their fixtures) continue to pass byte-for-byte — the
parameterization is backward compatible by construction.

Validation:

- `zig build test-wgsl`: 962 / 963 passed. Same pre-existing
  unrelated `reduction pattern` test failure as cycles 9–13.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 next slice — the actual live-path swap — is now structurally
unblocked for residual_add. The remaining work to flip the live
`emit_csl_semantic_ops.emitResidualPe` body to delegate to TSIR is:

1. Construct a SemanticFunction inside `emitResidualPe` with
   bindings named `a`, `b`, `output` (matching the symbols the live
   exports, which downstream binding maps already expect).
2. Call `tsir.emit_csl.emitSemanticFunction` and write the bytes.
3. Reconcile cosmetic differences (live emits `param chunk_size:
   i16 = 1024;` with a default; TSIR omits the default. Either add
   a default-value hook in the TSIR emitter or accept that cslc
   takes the param from the host-plan compile params either way.)
4. Delete the hand-written body once equivalence is confirmed.

## 2026-04-25 (cycle 13) — Item 4 audit: rewrite Current state + Active blockers against actual evidence

Item 4 audit slice. The "Current state" claim that the host
"compiles 10 of 14 targets ... and fails 4 with real
kernel-level diagnostics: embed, lm_head_gemv_stable,
attn_head256, attn_head512" was stale, and the "Active blockers"
list of four kernels needing per-PE residency redesign was based
on the same out-of-date runs.

Cross-referenced the section text against:

- `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/trace.json.driver-result.json`
  (cycle-7 + cycle-12 evidence): 17 of 17 compile targets succeed.
  Including `embed`, `attn_head256`, `attn_decode`, `lm_head_gemv`.
  No `attn_head512` target exists in the live compileTargets list.
- `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/simulator-evidence.json`
  (cycle-8 gate output, refreshed): runtime executes
  `embed` (6 sublaunches succeed) and `rmsnorm_prefill` end-to-end;
  was inside `tiled` q_proj output memcpy_d2h when the 600s
  wallclock timeout hit.

Section rewrite:

- "Current state" now reflects 17 / 17 compile success, the
  three-launch runtime advance, and explicitly retires the
  kernel-architecture-blocker framing in favor of the actual
  remaining work (simulator wallclock, TSIR live-path wiring,
  parity-comparison data wiring).
- "Active blockers" now lists the real open items instead of the
  obsolete four-kernel claim:
    - Simulator wallclock vs simfabric per-launch cost.
    - TSIR live-path wiring (the open Item-2 work, now
      explicit including the symbol-export reconciliation issue).
    - Numeric parity wiring (the open Item-5 work).
    - Stale `reduction pattern` test in
      `emit_csl_host_compile_source.zig` (technical debt noticed
      in cycles 9–12).

This audit doesn't change any code — it removes future cycles of
chasing kernel-architecture redesign work that is already
unblocked. The cycle-7 BF16 layernorm-broadcast fix (Item 4 first
slice) plus the late+16 manifest compile-param projection together
already moved past the per-PE sizing concern.

Validation: no build / test changes — pure documentation update.
The shard size moves from 860 → ~888 lines, well under the 1200
cap.

## 2026-04-25 (cycle 12) — TSIR-to-CSL kv_read op completes the kv_cache pair

Item 2 cycle-12 slice. Adds the symmetric counterpart to cycle 11's
`kv_write`. The TSIR semantic surface now covers both halves of the
KV-cache lifecycle that `emit_csl_kv_cache.zig` hand-maintains in
the live HostPlan path.

Landed:

- `runtime/zig/src/tsir/schema.zig`: `SemanticBodyOp` gains
  `kv_read`. `SemanticBindingRole` gains `key_output` and
  `value_output` — the cache inputs reuse `key_cache` /
  `value_cache` from cycle 11.
- `config/doe-tsir-semantic.schema.json`: matching enum extensions.
- `runtime/zig/src/tsir/emit_kernel_body.zig`: `emitCsl` dispatch
  arm + `emitCslKvRead` impl. Mirrors the live
  `emit_csl_kv_cache.emitRead` shape — outer loop over `read_len`
  position rows, inner copy of `head_dim` elements per row,
  `read_start` defaults to zero so prefill paths can skip the
  offset arg.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: new
  `kvReadSemantic()` constructor + test pinning the CSL output.

This completes Item 2's coverage of the elementwise + kv-cache
families. Loop tally: residual_add (cycle 9), gelu_gated (cycle 10),
kv_write (cycle 11), kv_read (cycle 12). Binding role count
22 total (added `key_output`, `value_output` this cycle).

Validation:

- `zig build test-wgsl`: 961 / 962 passed. Same pre-existing
  unrelated `reduction pattern` test failure.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 hand-maintained surface remaining:

- `emit_csl_fused_ffn.zig` — fused SiLU-gated FFN; non-trivial
  semantic shape (gate_proj + up_proj + silu + multiply with
  fabric reduce).
- `emit_csl_dequant.zig`, `emit_csl_sample.zig`,
  `emit_csl_attention.zig`, `emit_csl_fused.zig` (gemv+dequant),
  `emit_csl_gather.zig` (embed) — domain kernels with non-trivial
  bodies.
- Live HostPlan path still routes through
  `emit_csl_semantic_ops.zig` and `emit_csl_kv_cache.zig` for the
  ops covered above. The wiring switch is itself a slice; needs
  bootstrap fixtures the `tsir-real-entries` directory does not
  yet carry. The natural next-level Item 2 cycle is to convert one
  of the now-TSIR-covered ops (residual_add or gelu_gated being
  the smallest) into a live-path swap with name-mapping or
  symbol-convention reconciliation.

## 2026-04-25 (cycle 11) — TSIR-to-CSL kv_write op (5 new binding roles, multi-storage shape)

Item 2 cycle-11 slice. Third new TSIR semantic body in this loop,
this one exercising a different role surface than the elementwise
ops added in cycles 9 / 10: read-write storage bindings (key/value
caches), a `u32` state-buffer binding (decode_position), and two
read-only projection inputs.

Landed:

- `runtime/zig/src/tsir/schema.zig`: `SemanticBodyOp` gains
  `kv_write`. `SemanticBindingRole` gains five new entries —
  `key_projection`, `value_projection`, `key_cache`, `value_cache`,
  `decode_position`. The cache pair are read-write; the position is
  a single-element `u32` state buffer the runtime updates each
  decode step.
- `config/doe-tsir-semantic.schema.json`: matching enum extensions.
- `runtime/zig/src/tsir/emit_kernel_body.zig`: `emitCsl` dispatch
  arm + `emitCslKvWrite` impl. Mirrors the live
  `emit_csl_kv_cache.emitWrite` shape — computes
  `base = decode_position[0] * head_dim` and copies head_dim
  elements from each projection into the cache slot. Other 4
  backends keep typed-rejection.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: new
  `kvWriteSemantic()` constructor + test pinning the CSL output
  (param decls, cache shape, position lookup, copy loop, exports)
  and asserting webgpu typed-rejection.

This brings the loop's TSIR-op tally to three (residual_add,
gelu_gated, kv_write) and the binding-role count to thirteen
(matrix, vector, input, scale, indices, table, output, query, key,
value, kv_len_buffer, page_table, summand_a, summand_b, gate,
key_projection, value_projection, key_cache, value_cache,
decode_position — sixteen total).

Validation:

- `zig build test-wgsl`: 960 / 961 passed. Same pre-existing
  unrelated `reduction pattern` test failure as cycles 9 / 10
  (semantic-emitter-replaced rmsnorm vs the test's old assertions).
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 hand-maintained-emitter remaining surface:

- `emit_csl_kv_cache.emitRead` — symmetrical with the new TSIR
  `kv_write`; could land next cycle on the same pattern.
- `emit_csl_fused_ffn.zig` — fused SiLU-gated FFN; bigger semantic
  shape (gate_proj + up_proj + silu + multiply), would need new
  binding roles.
- `emit_csl_dequant.zig`, `emit_csl_sample.zig`, etc. — domain
  kernels with non-trivial bodies; later cycles.
- Live HostPlan path still routes through
  `emit_csl_semantic_ops.zig` for residual / gelu / rmsnorm rather
  than through the TSIR emitters added here. The wiring switch is
  itself a slice — needs bootstrap fixtures the
  `tsir-real-entries` directory does not yet carry for these ops.

## 2026-04-25 (cycle 10) — TSIR-to-CSL gelu_gated op

Item 2 cycle-10 slice. Adds the second new TSIR semantic body in
this loop, validating the cycle-9 pattern scales: schema enums,
binding role, dispatch arms, CSL emitter, test — same shape, no
new infrastructure required.

Landed:

- `runtime/zig/src/tsir/schema.zig`: `SemanticBodyOp` gains
  `gelu_gated`. `SemanticBindingRole` gains `gate` (paired with the
  existing `.input` and `.output` roles).
- `config/doe-tsir-semantic.schema.json`: matching enum extensions.
- `runtime/zig/src/tsir/emit_kernel_body.zig`: `emitCsl` dispatch
  arm + `emitCslGeluGated` implementation. The gelu polynomial is
  inlined as a CSL helper using the same constants the live
  `emit_csl_semantic_ops.emitGeluPe` uses
  (`GELU_A=0.7978845608028654`, `GELU_B=0.044715`,
  `0.5 * x * (1 + tanh(GELU_A * (x + GELU_B*x^3)))`). Other 4
  backends keep typed-rejection.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: new test
  pins the CSL output (binding decls, gelu helper, gated multiply,
  exports) and asserts webgpu still returns
  `error.UnsupportedKernelBody`.

Validation:

- `zig build test-wgsl`: 959 / 960 passed. Same pre-existing
  unrelated `reduction pattern` test failure as cycle 9; new
  `gelu_gated` test passes.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 progress so far in this loop: residual_add (cycle 9),
gelu_gated (cycle 10). Remaining hand-maintained semantic ops in
`emit_csl_semantic_ops.zig`: `rms_norm` (already in TSIR but the
live HostPlan still routes through `emitRmsNormPe`, not the TSIR
emitter), plus everything in `emit_csl_kv_cache.zig`
(`kv_write`, `kv_read`) and `emit_csl_fused_ffn.zig` (the
fused SiLU-gated FFN). Wiring the live HostPlan path through TSIR
for any of these requires bootstrap fixtures the
`tsir-real-entries` directory does not yet contain.

## 2026-04-25 (cycle 9) — TSIR-to-CSL residual_add op: first new semantic body in this loop

Item 2's first concrete advance in the loop. Adds `residual_add` to
the TSIR semantic schema and a CSL emitter for it, demonstrating
that the schema-extension + emit-flow pipeline accommodates a new
kernel without disturbing the existing fused_gemv / rms_norm /
gather / attention_scores set.

Landed:

- `runtime/zig/src/tsir/schema.zig`: `SemanticBodyOp` gains
  `residual_add`. `SemanticBindingRole` gains `summand_a` and
  `summand_b` — two distinct roles because `bindingForRole`
  returns one binding per role and positional `a`/`b` would be
  ambiguous. No body-specific struct: the op kind plus the binding
  roles fully specify the kernel.
- `config/doe-tsir-semantic.schema.json`: matching enum extensions
  (`bodyOp`, `bindingRole`).
- `runtime/zig/src/tsir/emit_kernel_body.zig`: dispatch arm in
  `emitCsl` plus `emitCslResidualAdd` implementation. The other
  four backends (webgpu, msl, dxil, spir_v) keep
  `error.UnsupportedKernelBody` for the new op — same typed-rejection
  posture `attention_scores` uses today, so the build doesn't pretend
  to support what hasn't been written.
- `runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`: one new
  test `tsir csl emitter produces executable residual_add body`
  pins the CSL output (binding decls, the per-element add, and the
  exported symbols) AND asserts `emit_webgpu` returns the typed
  rejection so future-cycle backend wiring can flip the assertion
  intentionally.

The TSIR-emitted CSL for residual_add mirrors the live
`emit_csl_semantic_ops.emitResidualPe` shape (per-PE `[chunk_size]f32`
buffers, `output[i] = a[i] + b[i]`, `sys_mod.unblock_cmd_stream`),
just under the TSIR `summand_a` / `summand_b` / `output` naming
convention. Wiring the live HostPlan path through the TSIR emitter
is a follow-up — this cycle establishes the contract; the live
swap is its own slice.

Validation:

- `zig build test-wgsl`: 958 / 959 passed. The 1 failure is the
  pre-existing stale `reduction pattern emits real rmsnorm` test
  (assertions written for the old WGSL-derived reduction lowering;
  the late+16 semantic emitter replaced that path so the test is
  out of date — independent of this cycle's changes; reproduces on
  the pre-cycle tree via `git stash`).
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 2 follow-ups:

- Wire `residual_add` lowering through the other 4 backends
  (webgpu/msl/dxil/spir_v) — flip the typed-rejection posture as
  each is implemented.
- Wire `residual_add` into the live HostPlan path so the runtime
  CSL for residual launches comes from TSIR instead of
  `emit_csl_semantic_ops.emitResidualPe`. That requires the host
  plan to carry TSIR realization fixtures for the residual kernel,
  which the bootstrap surface does not yet emit.
- Repeat for `gelu_gated`, `kv_write`, `kv_read`, and the other
  hand-maintained semantic ops in `emit_csl_semantic_ops.zig`.
- Address the stale `reduction pattern` test in
  `emit_csl_host_compile_source.zig` — its assertions need updating
  for the semantic-emitter rmsnorm shape (uses `@range(i16, hidden_size)`,
  not `i < hidden_size`; folds the Gemma `1+w` offset inline as
  `1.0 + weight[idx]`, not as a separate `rms_norm_offset` const).

## 2026-04-25 (cycle 8) — csl_simulator_evidence_gate: parity vs plumbing classification

Item 5's first slice. New
`bench/gates/csl_simulator_evidence_gate.py` reads the
`trace.json.driver-result.json` and `trace.json.progress.jsonl`
artifacts a HostPlan bundle produces, walks events in timeline order
(last observation per launch wins, so a launch that failed in an
earlier regen and succeeded in the latest reports as succeeded),
and emits a `simulator-evidence.json` receipt with two
intentionally-separate fields:

- `plumbingClassification` ∈ { `artifacts_missing`, `driver_exception`,
  `compile_failed`, `compile_only`, `plumbing_partial`,
  `plumbing_pass` } — derived from compile status, run reason, and
  per-launch terminal events.
- `numericParity.status` — always `unknown` until a reference
  transcript is wired in. The slot exists in the schema so future
  iterations can drop in real Doppler-reference comparison without
  rewriting the contract; it explicitly never implies parity from
  plumbing metrics alone.

Driver-exception classification takes precedence over
`compile_failed` because the driver halts both phases at once when
it hits a Python exception (schema validation, missing inputs); the
late+18 bf16 dtype regression would have shown as `compile_failed`
under a naive ordering even though the actual failure was a JSON
schema rejection before any cslc invocation.

Live evidence — running the gate against the cycle-7 artifacts on
disk classifies correctly:

```
plumbing=plumbing_partial  parity=unknown
launchesStarted=[0, 1, 2]
launchesSucceeded=[0, 1]
launchesFailed=[]              # last-observation-wins erases the
                                # stale pre-fix launch[1] block
lastLaunchSucceededIndex=1
```

Test coverage:
`bench/tests/test_csl_simulator_evidence_gate.py` exercises every
classification branch with synthetic fixtures including
last-observation-wins across simulated regen runs and the
"`numericParity` always unknown until reference wired" invariant.

Validation:

- `python3 -m unittest bench.tests.test_csl_simulator_evidence_gate`:
  10 / 10 passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed (10 new from this slice).
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 5 follow-ups (next slices, not landed here):

- Wire the `numericParity` lane to compare against Doppler reference
  logits / KV digests when available. The receipt schema slot
  (`compareSource`, `reason`, `status`) is the contract.
- Promote the gate to a blocking step in
  `run_cerebras_evidence_bundle.py` once parity wiring is in place.

## 2026-04-25 (cycle 7) — BF16 broadcast path unblocks rmsnorm runtime; gemma-3-1b sim advances past launch[2]

Item 4's first concrete runtime fix in this loop. The launch[1] BF16
norm-broadcast blocker recorded in late+18 is gone — the simulator
now executes embed (launch[0]), rmsnorm_prefill (launch[1]), and
tiled q_proj (launch[2]) before hitting the wallclock timeout
during launch[2]'s `c` output memcpy_d2h.

Root cause and fix:

- BF16 layernorm weights are `[hidden_size]` shared vectors meant
  to be broadcast across every PE in the rmsnorm prefill grid.
  `_materialize_weight_input`'s `bf16_to_f32` path was reading
  `total_elements * 2 = 34560` bytes for a source weight that holds
  `2304` bytes — `1152 * 2` (one PE's worth, since the same vector
  is replicated to every PE).
- New helper `_broadcast_factor_or_one` in
  `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`
  detects the broadcast case explicitly: if the source byte size
  matches `elementsPerPe * source_byte_width` AND
  `elementsPerPe * peCount == total_elements`, the factor is
  `peCount` and the materializer reads one PE's worth of bytes,
  then `np.tile`s across the grid. Otherwise the factor is 1 and
  the existing distributed read path runs unchanged. The branch
  applies to both `bf16_to_f32` and `f16_to_f32` /
  `litert_axis_dequant` to keep the f16 path consistent.

Validation evidence:

- `python3 csl_sdk_driver.py simulator-plan.json` exit 4 (compile
  succeeds, run times out) vs the prior exit 4 with launch[1]
  blocked. Compile is still 17 / 17 succeeded.
- `trace.json.progress.jsonl` last successful event:
  `hostplan_launch_complete target=rmsnorm_prefill status=succeeded`,
  followed by `hostplan_launch_start target=tiled launch[2]`.
- launch[2] (tiled q_proj) staged inputs cleanly at the expected
  per-binding size: `a` and `b` each 1411344 elements
  (= 484 / PE × 2916 PEs). This is the exact path that the
  pre-`1ef893a94` artifacts blamed on a missing
  `@export_symbol(X_ptr, "y")` resolver — confirming the resolver
  + the SUMMA host materialization land cleanly together.
- Embed launch[0] uses chunked dispatch (6 sublaunches across
  hidden offsets 0, 192, 384, 576, 768, 960). Each sublaunch is
  ~33 seconds in simfabric.

Next blocker is performance, not correctness. The 600-second
default `INT4PLE_RUNTIME_RUNNER` timeout was insufficient to drain
launch[2]'s 1.4M-element output memcpy_d2h after spending three
minutes on embed sublaunches. Two ways forward (no slice taken
this cycle, surfaced for next iteration):
1. Raise the runner timeout to a value matched to per-kernel
   simfabric cost (this is purely a config knob).
2. Audit embed's per-sublaunch cost — 33 seconds × 6 to fan
   one PE row across the grid is heavy and may indicate the embed
   chunked-dispatch ROI is doing more work than it needs to.

P7.4 is now end-to-end validated for the prefill prefix. The
launch[2] failure that motivated the original P7.4 #3 framing
is gone in code AND demonstrated gone in simulation. The earlier
"Active blockers" entries for embed, lm_head_gemv_stable,
attn_head256, attn_head512 (per-PE state too large) are also
contradicted by the post-late+18 compile-side success — those need
re-evaluation rather than the runtime redesign they were scoped to.

## 2026-04-25 (later) — compile/targets.metadata.json carries phase + base kernel

Item 1's cycle-6 slice replaces the Python `kernel_name + "_" + phase`
suffix convention with a Zig-emitted `(baseKernel, phase) → target name`
table. The bug this surfaced is concrete: the previous suffix
heuristic would have misclassified `attn_decode` as a phase-decode
variant of a hypothetical `attn` kernel, because the suffix matched
even though `attn` is not phase-specialized. Threading phase + base
kernel through the Zig `CompileTarget` struct at construction time
removes the ambiguity at the source.

Landed:

- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`: `CompileTarget`
  struct gains optional `phase` and `base_kernel` fields. Both default
  to `null` so existing call sites are unchanged for base targets.
- `runtime/zig/src/csl_host_plan_tool.zig`: `appendCompileTarget` now
  takes a `phase: ?[]const u8` parameter; `buildCompileTargets`
  passes `null` for base targets and the suffix string for phase
  variants. New `materializeTargetsMetadata` writes
  `compile/targets.metadata.json` listing every compile target with
  `{ name, baseKernel, phase, layout, peProgram }`.
- `runtime/zig/src/csl_pe_program_metadata.zig`: new
  `TargetDescriptor` struct + `emitTargetsJson`. One unit test pins
  the JSON shape and that base targets serialize `phase` as `null`.
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`:
  `_load_targets_metadata` returns a
  `(baseKernel, phase) → name` dict.
  `_resolve_phase_variant_target` now accepts an optional
  `targets_metadata` argument and prefers it; the legacy
  `f"{kernel_name}_{phase}"` lookup remains as fallback.
  `build_hostplan_execution_plan` loads the metadata once before the
  launch loop.

The regenerated `gemma-3-1b-doe-csl-hostplan/compile/targets.metadata.json`
correctly classifies `attn_decode` as `baseKernel="attn_decode", phase=null`
(its own kernel, not a phase variant of a non-existent `attn`). The
six entries the Python loader reads are exactly the
elementwise prefill/decode pairs:

```
(gelu, decode) -> gelu_decode
(gelu, prefill) -> gelu_prefill
(residual, decode) -> residual_decode
(residual, prefill) -> residual_prefill
(rmsnorm, decode) -> rmsnorm_decode
(rmsnorm, prefill) -> rmsnorm_prefill
```

Validation:

- `zig test src/csl_pe_program_metadata.zig`: 5 / 5 passed.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`: 67 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`: 40 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Item 1 has now covered: variables, pointers, exports,
compile-time constants, layout exports, and target phase + base
kernel. The remaining vision items (binding shape resolved against
runtime compile params, per-PE shape after staging, SUMMA tile-
transform parameters, detile transform, weight source) are runtime-
materialization concerns rather than CSL-source parsing — a
different category of work.

## 2026-04-25 — layout.metadata.json sidecar replaces Python layout.csl regex

Item 1's cycle-5 slice extended the structured-metadata sidecars to
also cover `layout.csl`. The HostPlan executor's
`_parse_layout_exports` now reads `@export_name(...)` declarations
from `layout.metadata.json` instead of regex-parsing the CSL text
when the sidecar is present.

Landed:

- `runtime/zig/src/csl_pe_program_metadata.zig`: added a parallel
  `LayoutParsed` / `parseLayoutExportLine` / `emitLayoutJson` set.
  `parseLayoutExportLine` tracks parenthesis depth so `fn()void`
  isn't split prematurely on its inner parens, and the
  `classifyLayoutExportKind` helper mirrors the Python rule
  (`fn`-typed → `device_function`, else `device_variable`).
  `mutable` defaults to `false` and is set `true`/`false`
  explicitly when the third arg is present.
- `runtime/zig/src/csl_host_plan_tool.zig`:
  `materializeCompileSources` now also writes
  `layout.metadata.json` per kernel via a new
  `emitLayoutMetadataFile` helper.
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`:
  new `_layout_exports_from_metadata` helper.
  `_parse_layout_exports` prefers the sidecar and falls back to
  `_EXPORT_NAME_RE` when missing, matching the existing
  pe_program.metadata.json pattern.

Spot check after regen — rmsnorm and tiled both produce identical
results from JSON vs the regex path:

```json
{"exports":[
  {"name":"input","type":"[*]f32","kind":"device_variable","mutable":true},
  {"name":"compute","type":"fn()void","kind":"device_function","mutable":false}
]}
```

Validation:

- `zig test src/csl_pe_program_metadata.zig`: 4 / 4 passed (one
  new layout-exports test).
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  67 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

CSL text parsing now covered by structured Zig metadata (with regex
fallback for backwards-compat):
`pe_program.csl` → `pe_program.metadata.json` (variables, pointers,
exports, compileTimeConstants — cycles 2 + 4) and `layout.csl` →
`layout.metadata.json` (export_name entries — this entry).

Higher-level Item 1 metadata (binding shape resolved against runtime
compile params, per-PE shape after staging, SUMMA tile-transform
parameters, detile transform, target phase, weight source) remain
Python-derived in `_binding_materialization` and the runner's
staging path. Those are the next deeper slices.

## 2026-04-24 (late+21) — pe_program.metadata.json carries compile-time constants

Item 1's cycle-4 slice extended the `pe_program.metadata.json`
sidecar emitted by `csl_host_plan_tool` to also carry every
`const X: T = N;` / `param X: T = N;` declaration our CSL emitters
produce. The Python HostPlan executor now derives the
`compile_time` dict from the JSON instead of running
`_PE_PROGRAM_CONST_OR_PARAM_RE` over the source text whenever the
sidecar is present.

Landed:

- `runtime/zig/src/csl_pe_program_metadata.zig`: added a
  `parseConstantLine` pass and a new `compileTimeConstants` JSON
  array `[{"kind":"const|param","name":...,"type":...,"expr":...}]`.
  `param X: T;` (no default) is intentionally skipped — it is a
  cslc-supplied input, not a value the host plan can read.
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`:
  new `_compile_time_from_metadata` helper. The combined parser
  prefers metadata-derived constants and falls back to the regex
  parser only when the sidecar is missing or empty.

Spot check after regen:

- `rmsnorm/pe_program.metadata.json` carries
  `hidden_size: i16 = 1024` and `rms_eps: f32 = 0.000001`. The
  Python loader resolves `hidden_size → 1024` (int) and skips
  `rms_eps` (non-int), matching the prior regex behavior exactly.
- `tiled/pe_program.metadata.json` carries the four
  `local_task_id` consts, all of which are correctly skipped by the
  integer-only `_resolve_size_expr`.

Validation:

- `zig test src/csl_pe_program_metadata.zig`: 3 / 3 passed.
- `zig build csl-host-plan-tool`: passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`: 67 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`: 40 passed.
- `python3 bench/gates/schema_gate.py`: PASS.

Still open on Item 1: higher-level metadata the longer-term vision
calls for — binding shape, per-PE shape, staging transform, detile
transform, target phase, weight source — remain Python-derived in
`_binding_materialization`. Those depend on runtime compile params
and on kernel-specific routing logic, so they are a deeper next
slice rather than a sidecar extension.

## 2026-04-24 (late+20) — cerebras-csl shard split: late+15 and earlier moved to archive

This shard crossed the 1200-line modularity cap during this same
session as the late+18 / late+19 entries landed. Per the shard
preamble's "Split by subdomain before it exceeds the cap" rule,
late+15 through 2026-04-23 entries were moved to
`archive/2026-04-24.md`. The live shard now keeps late+16 onward
plus the steady-state sections (Current state, Active blockers,
Landed infrastructure, Ground truth, Use this shard for).

Live shard: 1226 → 322 lines after this entry. Archive file: 933 lines.

## 2026-04-24 (late+19) — Zig-emitted pe_program.metadata.json replaces Python CSL regex on the read path

First slice of "structured metadata emitted by Zig" landed. The
HostPlan executor no longer has to re-parse generated CSL text to
discover binding shapes — `csl_host_plan_tool` now writes a small
sidecar JSON next to each compile target's source, and the Python
side prefers that sidecar over its regex parser when present.

Landed in this entry:

- `runtime/zig/src/csl_pe_program_metadata.zig`: new module. A
  conservative line-oriented parser for the four declaration shapes
  our own CSL emitters produce (`var <name>: [<size>]<elem>`,
  `var <name> = @zeros([<size>]<elem>)`, `var <ptr>: [*]<elem> = &<backing>`,
  `@export_symbol(<ptr>, "<symbol>")`). `emitJson` serializes the
  parsed result, resolving each export through its pointer to the
  backing variable's `sizeExpr` and `elemType` so consumers do not
  follow the indirection themselves. Two `zig test` cases cover the
  SUMMA tiled style (`var X = @zeros([Mt * Kt]f32)`) and the semantic
  RMSNorm style (`var input: [hidden_size]f32 = @zeros(...)`).
- `runtime/zig/src/csl_host_plan_tool.zig`:
  `materializeCompileSources` now writes `pe_program.metadata.json`
  alongside `layout.csl` and `pe_program.csl` for each kernel. Buffer
  cap `PE_PROGRAM_METADATA_CAPACITY = 16 KiB` matches the largest
  generated metadata observed today (tiled has the most entries; ~1
  KiB).
- `bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`:
  `_parse_pe_program_arrays` now checks for the sidecar at
  `<pe_program>.metadata.json`. When present, decls come from the
  structured JSON. The regex parser remains as a fallback for old
  artifacts and continues to drive the `compile_time` constants path
  (the metadata sidecar does not carry const/param defaults yet).

The regenerated `gemma-3-1b-doe-csl-hostplan/compile/<kernel>/pe_program.metadata.json`
files now exist for all 17 compile targets. Spot check on tiled:

```
exports: [
  {"symbol":"a","pointer":"A_ptr","backing":"A_tile","sizeExpr":"Mt * Kt","elemType":"f32"},
  {"symbol":"b","pointer":"B_ptr","backing":"B_tile","sizeExpr":"Kt * Nt","elemType":"f32"},
  {"symbol":"c","pointer":"C_ptr","backing":"C_tile","sizeExpr":"Mt * Nt","elemType":"f32"}
]
```

The Python loader produces the same `decls` shape it produced from
regex parsing earlier (sizeExpr, elemType, backingVariable,
exportPointer keys), so downstream `_binding_materialization` is
unchanged.

Out of scope for this slice (deferred to follow-ups):

- Compile-time constants (`const X: T = N;` / `param X: T = N;`).
  Still parsed by Python regex. Most of the load is already on
  per-target `out.json` from cslc; the regex path is only hit when a
  default is declared inline.
- Higher-level metadata the user's longer-term vision calls for —
  binding shape, per-PE shape, staging transform, detile transform,
  target phase, weight source. Those are derived downstream from the
  primitives this sidecar already carries; the sidecar contract is
  the foundation, not the full surface.

Validation:

- `zig build csl-host-plan-tool` passed.
- `zig test src/csl_pe_program_metadata.zig`: 2 / 2 passed.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`: 67
  passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- `python3 bench/gates/schema_gate.py`: PASS.
- End-to-end:
  `python3 bench/tools/run_doe_csl_int4ple_transcript.py --program-bundle ...`
  emits the sidecars; Python loader picks them up; spot-check on
  tiled `a`/`b`/`c` produces identical decls vs the regex path.

## 2026-04-24 (late+18) — bf16 dtype schema fix unblocks gemma-3-1b regen; all 17 kernels compile

The first end-to-end gemma-3-1b CSL HostPlan regen against the
post-`1ef893a94` code surfaced a stale schema enum that rejected the
BF16 norm-weight dtype the late+16 weight mapper now emits:

- `bench/runners/csl-runners/int4ple_runtime_weight_mappings`
  produces `dtype="bf16"` for `layer.<N>.input_layernorm` /
  `post_attention_layernorm` / `pre_feedforward_layernorm` /
  `post_feedforward_layernorm` / `norm` per `runtime_dtype("BF16")`.
- `config/doe-wgsl-runtime-config.schema.json` (line 140
  `weightMappings.items.dtype` and line 319
  `hostIoLayout.items.dtype`) and
  `config/doe-shared-execution-contract.schema.json` (line 462)
  rejected `bf16`. The driver's schema validation failed before the
  CSL compile started.

Schema enums now include `bf16`. `bench/gates/schema_gate.py` passed.

After the schema fix, the regenerated simulator artifacts at
`bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/` show
**every one of the 17 compile targets succeeded against `cslc`**:
`embed`, `rmsnorm` / `rmsnorm_prefill` / `rmsnorm_decode`, `tiled`,
`rope`, `attn_head256`, `residual` / `residual_prefill` /
`residual_decode`, `gelu` / `gelu_prefill` / `gelu_decode`, `gemv`,
`attn_decode`, `lm_head_gemv`, `sample`. The `csl_compile_pe_memory_exhausted`
and `csl_compile_unclassified` blockers documented earlier in this
shard for `embed`, `lm_head_gemv_stable`, `attn_head256`, and
`attn_head512` no longer appear in the per-target diagnostics for
this regen — needs follow-up confirmation against the corresponding
"Active blockers" entries.

Runtime then advanced past launch[0] `embed` and blocked at launch[1]
`rmsnorm` with `weight bytes unavailable:layer.0.input_layernorm 2304<34560`.
The available bytes (2304) match `hidden_dim * 2 = 1152 * 2` for the
BF16 layernorm tensor; the requested bytes (34560) match
`2304 * 15 = hidden_dim_bytes * prefill_pe_count`. The materializer
in `bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`
needs a broadcast/replicate path for layernorm-style weights so
each PE sees a copy of the same hidden-dim vector instead of
attempting to read distinct slices from disk.

This is the next concrete blocker. The original launch[2] tiled
binding-shape failure that motivated the earlier P7.4 `#3` framing
was not reached this run, but compile-side and `@export_symbol`
binding resolution are both validated end-to-end.

Validation:

- `python3 bench/gates/schema_gate.py` passed before and after the
  schema edit.
- `python3 /home/x/deco/doe/runtime/zig/tools/csl_sdk_driver.py
  simulator-plan.json` exit code 4 (compile success, run blocked at
  launch[1]) vs the prior exit code 5 (driver_exception during
  schema validation).

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

**Older 2026-04-24 entries (late+1 through late+15) and prior days
(2026-04-24 morning, 2026-04-23) have been archived to
[`archive/2026-04-24.md`](archive/2026-04-24.md). The live shard keeps
late+16 onward inline.**

