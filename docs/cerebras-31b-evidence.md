# Gemma 4 31B on Cerebras WSE: Evidence Summary

External-facing snapshot of what's bound in-tree, what's verified end-to-end against the SDK simulator, and the single remaining hardware-gated step.

Every claim below resolves to a specific file, digest, or runnable test in this repo.

## What's bound today

**Full-graph compile.** Gemma 4 31B's full 60-layer model compiles clean against the WSE-3 simulator.

Receipt produced by [`bench/tools/synthesize_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_full_graph_compile_attempt_receipt.py): `compileSucceededCount=23/23`, `compileFailedCount=0`, `blocker.class="none"`.

The host plan it cites is hash-linked (`hostPlanHash=88ea720740…`); rerunning the synthesizer is byte-stable against the bound receipt.

**Per-kernel byte-identity (the 1-of-60-layer property).** [`bench/tests/test_one_layer_per_kernel_byte_identity.py`](../bench/tests/test_one_layer_per_kernel_byte_identity.py) runs the host-plan tool against `numLayers=1` and `numLayers=61` configs and asserts every shared kernel emits byte-identical `layout.csl`, `pe_program.csl`, and `pe_program.metadata.json`.

This is the property a 1-of-60-layer correctness receipt relies on. Kernel CSL is per-class, not per-layer-instance.

2/2 pass, 17 shared kernels match.

**Numerical parity vs reference inference.** Frozen 4-of-4 TSIR boundary probes (post_rmsnorm / post_qkv / post_attn / post_ffn at L=0) bound at [`bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/`](../bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/) with `fixtureDigest=8cc17070fedf9c3dd6571714b85a96ee1715519425c0e686990909c60c80ea87`.

Captured from a Doppler reference run with prompt "The color of the sky is"; greedy decode produces "blue".

Validator ([`bench/tools/validate_frozen_doppler_reference.py`](../bench/tools/validate_frozen_doppler_reference.py)) passes: `schemaValid=true`, `bound=true`, `verdict="bound"`.

**head_dim=512 attention fits per-PE SRAM.** Multi-PE kv-axis sharding.

Emit body at [`runtime/zig/src/tsir/emit_kernel_body_attention.zig`](../runtime/zig/src/tsir/emit_kernel_body_attention.zig) (`emitKvAxisSharded`). Partials-only kernel that writes `[head_dim + 2]f32` per PE (`local_O[d]` un-normalized, `local_max`, `local_sum_exp`).

Host-side log-sum-exp stitch at [`bench/tools/attention_kv_axis_sharded_stitch.py`](../bench/tools/attention_kv_axis_sharded_stitch.py).

Identity tests at [`bench/tests/test_attention_canary_kv_axis_sharded_identity.py`](../bench/tests/test_attention_canary_kv_axis_sharded_identity.py) pin rtol=1e-4 vs single-PE reference across multiple PE-grid configurations (13/13 pass).

**Wall-clock budget under ceiling.** [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) produces `decision=allow` against [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json).

Schema at [`config/manifest-simfabric-budget.schema.json`](../config/manifest-simfabric-budget.schema.json), 12/12 tests pass.

**Fused-dequant SUMMA wedge (Q4K-input, on-PE dequant).** Q4_K_M-quantized B is broadcast to PEs as raw bytes (~7× smaller fabric memcpy than f32-dense) and dequanted on-PE before SUMMA accumulation, instead of pre-dequanting on the host.

Cell receipt at [`bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/receipt.json`](../bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/receipt.json) — `verdict=pass`, parity vs canonical Doppler dequant within float32 precision.

Bound dispatch receipt at [`bench/out/r3-1-31b-multi-token-decode-q4k/receipt.json`](../bench/out/r3-1-31b-multi-token-decode-q4k/receipt.json) — `mode=compile_and_execute`, `cellParityPassed=true`, hash-linked to the cell receipt and the cslc invocation. Fabric-byte ratio (`baselineFabricBytes_f32_dense / wedgeFabricBytes_q4k_block256`) recorded structurally.

Emitter at [`runtime/zig/src/doe_wgsl/emit_csl_matmul_q4k.zig`](../runtime/zig/src/doe_wgsl/emit_csl_matmul_q4k.zig); host-side B-tile q4k passthrough at [`bench/runners/csl-runners/int4ple_summa_layout.py`](../bench/runners/csl-runners/int4ple_summa_layout.py) (`b_tiles_from_q4k_bytes`); structural-pin tests at [`bench/tests/test_q4k_summa_receipt_parity.py`](../bench/tests/test_q4k_summa_receipt_parity.py) and [`bench/tests/test_int4ple_q4k_passthrough.py`](../bench/tests/test_int4ple_q4k_passthrough.py); CSL emit unit tests at [`runtime/zig/tests/wgsl/emit_csl_matmul_q4k_test.zig`](../runtime/zig/tests/wgsl/emit_csl_matmul_q4k_test.zig).

Wedge mechanism is proven at small SUMMA shape; promotion to Gemma 4 31B's full compile sweep shape is named in the dispatch receipt's `remainingForFullClaim`. This is not a speed claim — simfabric is correctness-only — and the fabric-byte ratio is structural.

## What's hardware-gated

An on-cluster compile + dispatch run for the bound bundle delivers two things simfabric cannot:

1. **Dispatch parity.** Runtime parity receipt vs the simulator, confirming the bundle dispatches the same on real silicon. Supersedes the canary-proxy calibration constant.

2. **Speed.** Wall-clock tok/s for prefill and decode, comparable against published Gemma 4 31B inference references on competing accelerators.

Simfabric is correctness-only. There is no way to measure speed without real silicon.

A short multi-token inference run produces both. The bundle is hash-linked (host plan, CSL, fixture, expected-output digests).

## Running the bundle on hardware

The compiled artifacts referenced above live at `bench/out/r3-1-31b-manifest-fullgraph-compile-steps/` (~319 MB, 124 files): `host-plan.json`, `simulator-plan.json`, `runtime-config.json`, `memory-plan.json`, plus `compile/<kernel>/{layout,pe_program}.csl` for 17 kernel classes.

The bundle directory is regeneration output, not source. It is gitignored under `bench/out/`, byte-stable regenerable from source.

Regenerate with:

```
runtime/zig/zig-out/bin/doe-csl-host-plan-tool \
  --input runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json \
  --bundle-root bench/out/r3-1-31b-manifest-fullgraph-compile-steps \
  --mode steps
```

After regeneration, `host-plan.json` digests to `hostPlanHash=88ea720740…` (full hash bound in the synthesizer receipt). Run `cslc` against each `compile/<kernel>/` directory.

For an on-cluster run, the bundle plus the smoke config (`runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json`) and the frozen reference fixture (`bench/fixtures/r3-1-31b-doppler-frozen/`) ship as a single tarball on request.

## Pipeline scope

WGSL → TSIR → CSL is transformer-agnostic. The same path lowers any open-weight transformer with a clean reference implementation.

Gemma 4 31B is the first proof. Qwen 3.6-27B is queued behind hardware validation of the first.
