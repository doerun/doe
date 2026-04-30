# Gemma 4 31B on Cerebras WSE: Evidence summary

External-facing snapshot of what is bound in-tree for Gemma 4 31B before WSE hardware. The Gemma path mirrors the Qwen 3.6 27B evidence trail at [`docs/cerebras-27b-qwen-evidence.md`](cerebras-27b-qwen-evidence.md); identical source-identity chain, parallel artifacts, and hardware-gated tail.

The shared cross-model receipt at [`bench/out/r3-cross-model-parity/receipt.json`](../bench/out/r3-cross-model-parity/receipt.json) binds both models to the same `cslc` toolchain, TSIR schema, opToSpec table, host-plan hashes, budget hashes, and compile-blocker taxonomy.

## Bound non-hardware scope

**Smoke-config full architecture.** [`runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json`](../runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json) declares the Gemma manifest architecture and is the source of truth for the host-plan bundle shape.

**Manifest compile receipt.** [`bench/tools/synthesize_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_full_graph_compile_attempt_receipt.py) binds the current Gemma steps-mode bundle and driver result. The receipt reports `blocker.class="none"`; see [`bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`](../bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json) for the current target inventory and measured `cslc` verdicts.

**Frozen Doppler boundary fixture.** [`bench/fixtures/r3-1-31b-doppler-frozen/`](../bench/fixtures/r3-1-31b-doppler-frozen/) binds the Doppler browser WebGPU reference probes for the Gemma smoke prompt; the transcript records `surface="browser-webgpu"` and greedy decode of `The color of the sky is` producing `blue`. [`bench/tools/validate_frozen_doppler_reference.py`](../bench/tools/validate_frozen_doppler_reference.py) validates the fixture digest, manifest identity, schema, and probe set.

**Per-kernel byte identity.** [`bench/tests/test_one_layer_per_kernel_byte_identity.py`](../bench/tests/test_one_layer_per_kernel_byte_identity.py) asserts that shared kernel classes emit byte-identical `layout.csl`, `pe_program.csl`, and `pe_program.metadata.json` across the single-layer and full-shape host plans. This is the property the L1 hardware smoke receipt relies on.

**Cerebras semantic kernels.** The Gemma host plan exercises the shared transformer CSL surface, including kv-axis-sharded attention for the large head-dim path. The attention emitter lives in [`runtime/zig/src/tsir/emit_kernel_body_attention.zig`](../runtime/zig/src/tsir/emit_kernel_body_attention.zig); host-side log-sum-exp stitching lives in [`bench/tools/attention_kv_axis_sharded_stitch.py`](../bench/tools/attention_kv_axis_sharded_stitch.py); semantic identity coverage lives in [`bench/tests/test_attention_canary_kv_axis_sharded_identity.py`](../bench/tests/test_attention_canary_kv_axis_sharded_identity.py).

**Fused-dequant SUMMA wedge.** The Q4K fused-dequant SUMMA path is bound by [`bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/receipt.json`](../bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/receipt.json) and the Gemma dispatch receipt at [`bench/out/r3-1-31b-multi-token-decode-q4k/receipt.json`](../bench/out/r3-1-31b-multi-token-decode-q4k/receipt.json). The emitter and structural tests are linked from those receipts; this is correctness and structural fabric-byte evidence, not a WSE speed claim.

**Cross-model parity gate.** [`bench/tools/aggregate_cross_model_parity.py`](../bench/tools/aggregate_cross_model_parity.py) joins Gemma 4 31B and Qwen 3.6 27B receipts, asserts shared toolchain and contract identity, and writes [`bench/out/r3-cross-model-parity/receipt.json`](../bench/out/r3-cross-model-parity/receipt.json). [`bench/runners/run_blocking_gates.py`](../bench/runners/run_blocking_gates.py) runs this gate by default.

**Fail-closed af16 HostPlan evidence.** The Gemma f16 CSL dtype contract lives
in [`config/doe-csl-dtype-contracts.json`](../config/doe-csl-dtype-contracts.json)
and forbids implicit af32 fallback for activation, KV, output, lm-head, logits,
sample, and accumulation roles. The current bounded receipt at
[`bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json`](../bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json)
validates that contract and records the inference gate result. It is blocked
on lm-head dispatch evidence and session transcript absence; it is not a
token-output success receipt.

**Checkpointed session scratch trace.** The latest local real-session scratch
trace is
[`bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt70.json`](../bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt70.json).
It records checkpointed HostPlan execution progress and remains
`checkpoint_stopped`; no WSE or transcript claim follows from it.

## Simulator performance guardrail

Manifest-shape simfabric is a correctness and budget guardrail, not a WSE latency claim. [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) keeps the Gemma envelope under the shared calibrated ceiling in [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json). Real performance claims remain gated on WSE receipts.

## Hardware-gated tail

The remaining Gemma claims require real WSE execution or a hardware-authorized compile/run lane:

- R3-1 Gemma 4 31B L1 smoke hardware receipt.
- WSE execution receipt for the manifest-shape full architecture.
- Scale proof beyond the non-hardware host-plan and simfabric gates.
- Performance proof with WSE timing counters and hardware telemetry.

## Regeneration contract

The Gemma compile-step bundle is regeneration output under `bench/out/`, not source. Source of truth remains the smoke config, TSIR/reference implementations, CSL semantic emitters, frozen Doppler fixture, and gate scripts above.

## Claim enabled by this branch

WGSL -> TSIR -> CSL is transformer-family agnostic across the two current proof targets. Gemma 4 31B and Qwen 3.6 27B are both bound at the non-hardware portability/execution scope; hardware execution, scale, and performance remain explicitly gated on WSE receipts.
