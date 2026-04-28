# Qwen 3.6 27B on Cerebras WSE: Evidence summary

External-facing snapshot of what is bound in-tree for Qwen 3.6 27B before WSE hardware. The Qwen path mirrors the Gemma 4 31B evidence trail at [`docs/cerebras-31b-evidence.md`](cerebras-31b-evidence.md); identical source-identity chain, parallel artifacts, and hardware-gated tail.

The shared cross-model receipt at [`bench/out/r3-cross-model-parity/receipt.json`](../bench/out/r3-cross-model-parity/receipt.json) binds both models to the same `cslc` toolchain, TSIR schema, opToSpec table, host-plan hashes, budget hashes, and compile-blocker taxonomy.

## Bound non-hardware scope

**Smoke-config full architecture.** [`runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`](../runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json) declares the Qwen manifest architecture and is the source of truth for the host-plan bundle shape, including the hybrid full-attention and gated-DeltaNet SSM layer pattern.

**Manifest compile receipt.** [`bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py) binds the current Qwen steps-mode bundle and driver result. The receipt reports `blocker.class="none"`; see [`bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json`](../bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json) for the current target inventory and measured `cslc` verdicts.

**Frozen Doppler boundary fixture.** [`bench/fixtures/r3-2-27b-doppler-frozen/`](../bench/fixtures/r3-2-27b-doppler-frozen/) binds the Doppler reference probes for the first full-attention layer in Qwen's hybrid pattern. [`bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py`](../bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py) validates the fixture digest, manifest identity, schema, and probe set.

**Per-kernel byte identity.** [`bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py`](../bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py) asserts that shared kernel classes emit byte-identical `layout.csl`, `pe_program.csl`, and `pe_program.metadata.json` across the single-layer and full-shape host plans. This is the property the L1 hardware smoke receipt relies on.

**Cerebras semantic kernels.** The Qwen host plan exercises the shared transformer CSL surface plus model-specific SSM body ops. The exec-v1 op table routes Qwen body ops through concrete CSL emitters for kv-axis-sharded attention, SDK-collective GEMV, depthwise convolution, q/k normalization, and linear attention. [`runtime/zig/src/tsir/reference_interpreter.zig`](../runtime/zig/src/tsir/reference_interpreter.zig) carries executable reference semantics for the newly bound SSM body ops.

**Per-kernel simfabric cells.** Qwen CSL cell runners live under [`bench/runners/csl-runners/qwen-3-6-27b-cells/`](../bench/runners/csl-runners/qwen-3-6-27b-cells/) and provide small-shape simfabric execution checks for the model-specific kernel surface. These are correctness cells, not throughput claims.

**Cross-model parity gate.** [`bench/tools/aggregate_cross_model_parity.py`](../bench/tools/aggregate_cross_model_parity.py) joins Gemma 4 31B and Qwen 3.6 27B receipts, asserts shared toolchain and contract identity, and writes [`bench/out/r3-cross-model-parity/receipt.json`](../bench/out/r3-cross-model-parity/receipt.json). [`bench/runners/run_blocking_gates.py`](../bench/runners/run_blocking_gates.py) runs this gate by default.

## Simulator performance guardrail

Manifest-shape simfabric is a correctness and budget guardrail, not a WSE latency claim. [`bench/tools/predict_simfabric_wallclock.py`](../bench/tools/predict_simfabric_wallclock.py) and [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) keep the Qwen predicted-cycle envelope under the shared calibrated ceiling in [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json). Real performance claims remain gated on WSE receipts.

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
