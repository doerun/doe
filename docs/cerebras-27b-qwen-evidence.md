# Qwen 3.6 27B on Cerebras WSE: Evidence Summary

External-facing snapshot of what is bound in-tree for Qwen 3.6 27B before WSE hardware. The Qwen path mirrors the Gemma 4 31B evidence trail at [`docs/cerebras-31b-evidence.md`](cerebras-31b-evidence.md); identical source-identity chain, parallel artifacts, and hardware-gated tail.

## Bound non-hardware scope

**Smoke-config full architecture.** [`runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`](../runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json) declares Qwen's manifest architecture: GQA 24:4, head_dim=256, hidden=5120, intermediate=17408, 64 layers, partial-rotary 0.25, queryKeyNorm, 16 full-attention layers, and 48 gated-DeltaNet SSM layers. The SSM layer sequence is now present in the host plan as `conv1d_depthwise -> l2_normalize(q/k) -> linear_attention` with linear-attention dimensions bound separately from the full-attention head size.

**Cerebras semantic kernels.** The exec-v1 op table routes Qwen's non-hardware body ops through concrete CSL emitters: `attention_prefill_kv_axis_sharded`, `gemv` via SDK `collectives_2d`, `conv1d_depthwise`, `l2_normalize`, and `linear_attention`. The paired-gate canary pins their host-plan params, binding shapes, opToSpec dispatch, and shared-kernel byte identity for `gemv`, `rope`, `rmsnorm`, and `attention_prefill_kv_axis_sharded`.

**Manifest compile receipt.** [`bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py) binds the current steps-mode bundle and driver result. The receipt now reports `blocker.class="none"` with no accepted compile blockers; see [`bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json`](../bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json) for the current target inventory and measured cslc verdicts.

**Reference-interpreter parity.** [`runtime/zig/src/tsir/reference_interpreter.zig`](../runtime/zig/src/tsir/reference_interpreter.zig) carries executable reference semantics for the newly bound SSM body ops, so TSIR smoke parity is no longer placeholder-only for `linear_attention`, `conv1d_depthwise`, or `l2_normalize`.

**Frozen Doppler boundary fixture.** [`bench/fixtures/r3-2-27b-doppler-frozen/`](../bench/fixtures/r3-2-27b-doppler-frozen/) covers the first full-attention layer in Qwen 3.6 27B's `linear x3 -> full` pattern with `post_rmsnorm`, `post_qkv`, `post_attn`, and `post_ffn` probes. [`bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py`](../bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py) binds the fixture digest, manifest identity, schema, and probe set.

**Per-kernel simfabric cells.** Qwen CSL cell runners live under [`bench/runners/csl-runners/qwen-3-6-27b-cells/`](../bench/runners/csl-runners/qwen-3-6-27b-cells/) and continue to provide small-shape simfabric execution checks for the model-specific kernel surface. These are correctness cells, not throughput claims.

**Cross-model parity gate.** [`bench/tools/aggregate_cross_model_parity.py`](../bench/tools/aggregate_cross_model_parity.py) joins Gemma 4 31B and Qwen 3.6 27B receipts, asserts shared `cslc` toolchain identity, Doe commit, runtime/zig commit, opToSpec table version, TSIR schema version, host-plan hashes, budget hashes, and per-model compile blocker summaries, then writes `bench/out/r3-cross-model-parity/receipt.json` with `verdict=bound|unbound`. [`bench/runners/run_blocking_gates.py`](../bench/runners/run_blocking_gates.py) runs this gate by default.

## Simulator performance guardrail

Manifest-shape simfabric is a correctness and budget guardrail, not a WSE latency claim. [`bench/tools/predict_simfabric_wallclock.py`](../bench/tools/predict_simfabric_wallclock.py) and [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) keep the Qwen predicted-cycle envelope under the shared calibrated ceiling in [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json). This catches accidental kernel-count, launch-shape, or body-op regressions before hardware while keeping real performance claims gated on WSE receipts.

## Hardware-gated tail

The remaining Qwen claims require real WSE execution or a hardware-authorized compile/run lane:

- R3-2 Qwen 3.6 27B L1 smoke hardware receipt.
- WSE execution receipt for the manifest-shape full architecture.
- Scale proof beyond the non-hardware host-plan and simfabric gates.
- Performance proof with WSE timing counters and hardware telemetry.

## Regeneration contract

The Qwen compile-step bundle is regeneration output under `bench/out/`, not source. Source of truth remains the smoke config, TSIR/reference interpreter implementations, CSL semantic emitters, frozen Doppler fixture, and gate scripts above.

## Claim enabled by this branch

WGSL -> TSIR -> CSL is transformer-family agnostic across the two current proof targets. Gemma 4 31B and Qwen 3.6 27B are both bound at the non-hardware portability/execution scope; hardware execution, scale, and performance remain explicitly gated on WSE receipts.
