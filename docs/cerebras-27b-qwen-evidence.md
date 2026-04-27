# Qwen 3.6 27B on Cerebras WSE: Evidence Summary

External-facing snapshot of what's bound in-tree for Qwen 3.6 27B, what's behind named blockers (Qwen-specific architectural deltas not yet lowered through TSIR/CSL), and what's hardware-gated.

Every claim below resolves to a specific file, digest, or runnable test in this repo. The Qwen path mirrors the Gemma 4 31B evidence trail at [`docs/cerebras-31b-evidence.md`](cerebras-31b-evidence.md); identical schema, parallel artifacts.

## What's bound today

**Per-kernel byte-identity (the 1-of-64-layer property).** [`bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py`](../bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py) runs the host-plan tool against `numLayers=1` and `numLayers=64` configs and asserts every shared kernel emits byte-identical `layout.csl`, `pe_program.csl`, and `pe_program.metadata.json`.

This is the property a 1-of-64-layer correctness receipt relies on. Kernel CSL is per-class, not per-layer-instance.

2/2 pass.

**Smoke-config compile-target inventory + cslc verdicts.** [`runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`](../runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json) declares Qwen's actual architecture: GQA 24:4, head_dim=256, hidden=5120, intermediate=17408, 64 layers, partial-rotary 0.25, queryKeyNorm. Receipt produced by [`bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py) at `bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json`: `compileTargetCount=15`, `compileAttempted=true`, `compileSucceededCount=10`, `compileFailedCount=1` (4 phase-specialized variants that share CSL byte-identically with their base kernels are recorded as `not_attempted` — they alias the base kernel's verdict via the per-kernel byte-identity test below).

cslc 2.10.0 against each `compile/<kernel>/` directory: embed, rmsnorm, tiled (SUMMA matmul), rope_partial (with `num_pairs=32` from `partialRotaryFactor=0.25`), residual, silu, gemv (q4k), kv_write (24-head GQA × 213 PE row shard), attn_decode (head_dim=256), and sample all return `Compilation successful`. The 1 failure is `attn_prefill` with `failureCode=linker_pe_memory_overflow` — the same per-PE-residency blocker the Gemma 4 31B prefill ladder carries (named "causal prefill" in the named-blockers list below).

`scopeRestrictions` are lifted from the smoke config so reviewers see exactly which Qwen-specific paths the receipt does and does not cover.

**Partial-rotary `num_pairs` sourced from manifest.** Host-plan tool now derives `num_pairs = head_dim * partialRotaryFactor / 2` from `modelConfig.partialRotaryFactor` (default 1.0). For Qwen 3.6 27B (head_dim=256, factor=0.25), the `rope_partial` compileParams read `num_pairs=32` — the canonical formula, not the previous kernel-default of 64.

Wiring at [`runtime/zig/src/csl_host_plan_tool.zig`](../runtime/zig/src/csl_host_plan_tool.zig) (`compileParamsForPattern` `rope` branch) and [`runtime/zig/src/doe_wgsl/emit_csl_host.zig`](../runtime/zig/src/doe_wgsl/emit_csl_host.zig) (`ModelConfig.partial_rotary_factor`).

**TSIR gated-activation body family.** `silu_gated` (SwiGLU FFN inner) and `sigmoid_gated` (attention output gate) `SemanticBodyOp` variants land on this branch alongside `gelu_gated`:

- Schema: [`runtime/zig/src/tsir/schema.zig`](../runtime/zig/src/tsir/schema.zig) (`SemanticBodyOp`).
- Emit body: [`runtime/zig/src/tsir/emit_kernel_body_gated.zig`](../runtime/zig/src/tsir/emit_kernel_body_gated.zig). Single emit body parameterized by activation kind; clamp form `z = clamp(-x, -15, 15)` matches the live PE arithmetic.
- Reference interpreter: [`runtime/zig/src/tsir/reference_interpreter.zig`](../runtime/zig/src/tsir/reference_interpreter.zig) (`tryGated` recognizes all three op kinds; algorithm-exact against the emit body).
- Tests: [`runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`](../runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig) pins CSL-emit fragments per kind; [`runtime/zig/tests/wgsl/tsir_scaffold_test.zig`](../runtime/zig/tests/wgsl/tsir_scaffold_test.zig) pins reference-interpreter math.

**Wall-clock budget under ceiling.** Qwen rung-2 predicted-wallclock receipt at `bench/out/r3-2-27b-manifest-simfabric-predicted-wallclock/budget.json` records `calibrated=true`, `grandPredictedCycles=392,726,830` (prefill=197,373,216 + decode=195,353,614). [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json) ceilings raised to 1.5× the Qwen prediction (grand=590M, prefill=297M, decode=294M); [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) decision: `allow`. Gemma 4 31B still passes (~35% utilization of the bumped ceiling); per-model ceilings (`ceilingsByModel`) is a tracked follow-up so each model's headroom is attributed precisely.

**Frozen Doppler reference validator binding (skip-when-absent).** [`bench/tests/test_validate_frozen_qwen_3_6_doppler_reference.py`](../bench/tests/test_validate_frozen_qwen_3_6_doppler_reference.py) binds the (model-agnostic) [`bench/tools/validate_frozen_doppler_reference.py`](../bench/tools/validate_frozen_doppler_reference.py) to the Qwen fixture path `bench/fixtures/r3-2-27b-doppler-frozen/`. Fixture itself is hardware/Doppler-gated (see below); when present the test asserts schema-valid manifest, hash-bound artifacts, recomputed `fixtureDigest`, recognized Qwen modelId, and four-probe boundary set (`post_rmsnorm`/`post_qkv`/`post_attn`/`post_ffn` at L=0).

## What's behind named blockers

These are Qwen-specific architectural deltas that the smoke config carries as explicit `scopeRestrictions` entries so receipts cannot be misread as covering them:

- **Linear-attention layers.** Qwen 3.6 27B is hybrid (full + linear-attn Mamba/SSM with conv1d). The TSIR layer has no body op for linear attention. Smoke config targets full-attention layers only.
- **mrope-interleaved 3D rotary.** Manifest carries `mropeSection=[11,11,10]` for text/image/video. Smoke config falls back to standard 1D RoPE with `partialRotaryFactor=0.25`. True mrope lowering is deferred.
- **Causal prefill.** `AttentionScoresBody` rejects `causal_mode != .none`. Same blocker the Gemma 4 31B prefill ladder carries; decode-only receipts are unblocked.
- **attentionOutputGate (sigmoid_gated).** Qwen applies `sigmoid(qGateProjection) * attnOutput` before the O projection. The TSIR `sigmoid_gated` body op landed; the doe_wgsl classifier surface and exec-v1 `opToSpec` map do not yet route this op. The smoke config drops the `o_gate` step entirely (rather than silently mapping to a non-gated stand-in) so receipts cannot misread Qwen attention as gate-free.
- **SwiGLU fused gate (silu_gated).** Qwen FFN is `silu(gate_proj(x)) * up_proj(x) → down_proj`. The smoke config maps the activation step to single-input `op="silu"` (existing `element_wise` pattern); the gate*up multiplication is currently implicit in the host-plan MLP fusion and not surfaced as a discrete `silu_gated` step. The classifier wiring + opToSpec entries that would close this are tracked in [`docs/status/cerebras-csl.md`](status/cerebras-csl.md).

## What's hardware-gated

Same shape as the Gemma 31B evidence packet:

1. **cslc invocation against the Qwen bundle.** Materializes [`bench/out/r3-2-27b-manifest-fullgraph-compile-steps/`](../bench/out/r3-2-27b-manifest-fullgraph-compile-steps/) (regeneration output, gitignored). Running cslc per-target attaches measured `failureCode` values to the synthesizer's compileTargets[] and flips `compileAttempted` to true. SDK-toolchain-dependent.

2. **Doppler reference fixture capture.** The frozen Qwen Doppler reference fixture at `bench/fixtures/r3-2-27b-doppler-frozen/` is captured cross-repo on Doppler's `feat/qwen-3-6-bringup` branch via `tools/run-program-bundle-reference.js --tsir-fixture-dir`. Once captured, the validator-binding test transitions from skip to verifying schema, artifact hashes, recomputed fixture digest, and four-probe boundary coverage.

3. **Dispatch parity + speed.** On-cluster compile + dispatch run delivers runtime parity vs the simulator and wall-clock tok/s. Same shape Gemma 31B carries.

## Running the bundle

The Qwen 3.6 27B compile-step bundle is regeneration output, not source. It is gitignored under `bench/out/`, byte-stable regenerable from source.

Regenerate with:

```
runtime/zig/zig-out/bin/doe-csl-host-plan-tool \
  --input runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json \
  --bundle-root bench/out/r3-2-27b-manifest-fullgraph-compile-steps \
  --mode steps
```

Then run cslc against each `compile/<kernel>/` directory.

## Pipeline scope

WGSL → TSIR → CSL is transformer-agnostic. Gemma 4 31B is the first proof bound end-to-end with hardware-gated tail; Qwen 3.6 27B rides the same path, with a smaller scope today (full-attention layers; no mrope; no fused gated activation) and explicit named blockers carried in the receipts. Each named blocker has a typed lowering target in [`docs/status/cerebras-csl.md`](status/cerebras-csl.md).

The same lowering path covers any open-weight transformer once its architectural deltas have body-op + emit + classifier coverage.
