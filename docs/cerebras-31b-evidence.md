# Gemma 4 31B on Cerebras WSE — Evidence Summary

External-facing snapshot of what's bound in-tree, what's verified
end-to-end against the SDK simulator, and the single remaining
hardware-gated step. Every claim below resolves to a specific file,
digest, or runnable test in this repo.

The full receipt-bound rung ladder and working-notes context live at
[`docs/cerebras-north-star.md`](cerebras-north-star.md) — read that if
you want the long form.

## What's bound today

**Full-graph compile.** Gemma 4 31B's full 60-layer model compiles
clean against the WSE-3 simulator.
[`bench/tools/synthesize_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_full_graph_compile_attempt_receipt.py)
produces the bound receipt: `compileSucceededCount=23/23`,
`compileFailedCount=0`, `blocker.class="none"`. The host plan it cites
is hash-linked (`hostPlanHash=88ea720740…`); rerunning the synthesizer
is byte-stable against the bound receipt.

**Per-kernel byte-identity (the 1-of-60-layer property).**
[`bench/tests/test_one_layer_per_kernel_byte_identity.py`](../bench/tests/test_one_layer_per_kernel_byte_identity.py)
runs the host-plan tool against `numLayers=1` and `numLayers=61`
configs and asserts every shared kernel emits byte-identical
`layout.csl`, `pe_program.csl`, and `pe_program.metadata.json`. This is
the property a 1-of-60-layer first-token receipt relies on — kernel
CSL is per-class, not per-layer-instance. 2/2 pass, 17 shared kernels
match.

**Numerical parity vs reference inference.** Frozen 4-of-4 TSIR
boundary probes (post_rmsnorm / post_qkv / post_attn / post_ffn at
L=0) bound at
[`bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/`](../bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/)
with `fixtureDigest=8cc17070fedf9c3dd6571714b85a96ee1715519425c0e686990909c60c80ea87`.
Captured from a Doppler reference run with prompt "The color of the
sky is"; greedy decode produces "blue". Validator
([`bench/tools/validate_frozen_doppler_reference.py`](../bench/tools/validate_frozen_doppler_reference.py))
passes (`schemaValid=true`, `bound=true`, `verdict="bound"`).

**head_dim=512 attention fits per-PE SRAM.** Multi-PE kv-axis
sharding. Emit body at
[`runtime/zig/src/tsir/emit_kernel_body_attention.zig`](../runtime/zig/src/tsir/emit_kernel_body_attention.zig)
(`emitKvAxisSharded`) — partials-only kernel that writes
`[head_dim + 2]f32` per PE (`local_O[d]` un-normalized + `local_max` +
`local_sum_exp`). Host-side log-sum-exp stitch at
[`bench/tools/attention_kv_axis_sharded_stitch.py`](../bench/tools/attention_kv_axis_sharded_stitch.py).
Identity tests at
[`bench/tests/test_attention_canary_kv_axis_sharded_identity.py`](../bench/tests/test_attention_canary_kv_axis_sharded_identity.py)
pin rtol=1e-4 vs single-PE reference across multiple PE-grid
configurations (13/13 pass).

**Wall-clock budget under ceiling.**
[`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py)
produces `decision=allow` against
[`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json)
(schema at
[`config/manifest-simfabric-budget.schema.json`](../config/manifest-simfabric-budget.schema.json),
12/12 tests pass).

## What's hardware-gated

A single on-cluster `cslc` compile + dispatch run for the bound
bundle produces the runtime parity receipt that supersedes the
canary-proxy calibration constant and closes the 1-of-60-layer
first-token rung. The bundle is hash-linked (host plan, CSL,
fixture, expected-output digests). The dispatch is bounded — single
first-token decode at 60 layers, not a sweep.

## Pipeline scope

WGSL → TSIR → CSL is model-agnostic. The same path lowers any
open-weight transformer with a clean reference implementation;
Gemma 4 31B is the first proof. Qwen 3.6-27B is queued behind
hardware validation of the first.
