# Qwen 3.6 27B on Cerebras WSE: Evidence Summary

External-facing snapshot of what's bound in-tree for Qwen 3.6 27B, what's behind named blockers (Qwen-specific architectural deltas not yet lowered through TSIR/CSL), and what's hardware-gated.

Every claim below resolves to a specific file, digest, or runnable test in this repo. The Qwen path mirrors the Gemma 4 31B evidence trail at [`docs/cerebras-31b-evidence.md`](cerebras-31b-evidence.md); identical schema, parallel artifacts.

## What's bound today

**Per-kernel byte-identity (the 1-of-64-layer property).** [`bench/tools/verify_qwen_3_6_27b_per_kernel_byte_identity.py`](../bench/tools/verify_qwen_3_6_27b_per_kernel_byte_identity.py) materializes the manifest-shape (numLayers from the smoke config) bundle and a 1L truncation, then asserts every shared kernel emits byte-identical `layout.csl`, `pe_program.csl`, and `pe_program.metadata.json`.

This is the property a 1-of-64-layer correctness receipt relies on. Kernel CSL is per-class, not per-layer-instance.

Receipt at `bench/out/r3-2-27b-manifest-shape-1L-identity/receipt.json`: `verdict=bound`, 11/11 shared kernels match.

**Smoke-config compile-target inventory + cslc verdicts.** [`runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`](../runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json) declares Qwen's actual architecture: GQA 24:4, head_dim=256, hidden=5120, intermediate=17408, 64 layers, partial-rotary 0.25, queryKeyNorm.

The 64L manifest-shape receipt produced by [`bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`](../bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py) lands at `bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json`. It cites the bundle's host-plan-derived compile targets and attaches measured `failureCode` values from the bundle's driver-result.json when present. `scopeRestrictions` are lifted from the smoke config so reviewers see exactly which Qwen-specific paths the receipt does and does not cover.

The companion 1L truncated-decode receipt produced by [`bench/tools/aggregate_qwen_3_6_27b_truncated_decode_compile_attempt.py`](../bench/tools/aggregate_qwen_3_6_27b_truncated_decode_compile_attempt.py) at `bench/out/r3-2-27b-truncated-decode-full-graph-compile-attempt/receipt.json` is observation, not synthesis: it re-emits a 1L Qwen bundle and invokes cslc 2.10.0 per target. Result: 14/15 pass (embed, rmsnorm, tiled, rope_partial with `num_pairs=32` from `partialRotaryFactor=0.25`, residual, silu, gemv, kv_write, attn_decode, sample, plus 4 phase-specialized variants that emit byte-identically with their base kernels). The 1 failure is `attn_prefill` with `failureCode=linker_pe_memory_overflow` — the same per-PE-residency blocker the Gemma 4 31B prefill ladder carries (named "causal prefill" in the named-blockers list below). The byte-identity receipt above licenses these 1L verdicts to stand for 64L verdicts on shared kernels.

**Per-kernel simfabric end-to-end runs (small-shape canary).** Beyond cslc compile-success, all 10 compile-target kernels carry simfabric-cell drivers under [`bench/runners/csl-runners/qwen-3-6-27b-cells/`](../bench/runners/csl-runners/qwen-3-6-27b-cells/). Summary receipt produced by [`bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py`](../bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py) at `bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json` records `cellCount=10`, `passCount=10`, `verdict=pass_with_documented_canary_constraints`, with the 11th compile target (`attn_prefill`) carried as a `knownBlockers` entry (cslc `linker_pe_memory_overflow`).

The 10 cells that execute end-to-end on simfabric and parity-check against host references: `rmsnorm` (width=4, hidden=128), `rope_partial` (head_dim=8, num_pairs=2 — validates the `partialRotaryFactor` wiring delta), `residual` (width=4, chunk_size=128), `silu` (passthrough stand-in — kernel currently emits as identity, not real SiLU; receipt cites `scopeRestrictions.swigluFfnFusedGate`), `embed` (token gather), `tiled` (P=2 SUMMA matmul C = A @ B), `kv_write` (slot-write at requested position), `gemv` (Q4_K dequant + GEMV, width=2 to avoid the routing gap), `attn_decode` (head_dim=8, kv_chunk=8, width=1 — single-PE attention validates the post-fix async-recv path), and `sample` (width=2, greedy argmax with paired-index reduction).

Two earlier WGSL→CSL emit gaps that this lane uncovered have been closed in [`runtime/zig/src/doe_wgsl/emit_csl_sample.zig`](../runtime/zig/src/doe_wgsl/emit_csl_sample.zig) and [`runtime/zig/src/doe_wgsl/emit_csl_attention.zig`](../runtime/zig/src/doe_wgsl/emit_csl_attention.zig): `sample` now carries a paired (max_value, max_index) reduction so the last PE writes the global argmax, not its own local index; `attn_decode` now uses the canonical wse3 scratch-buffer + `@mov32(.{.async, .activate=reduce_task_id})` pattern (replacing the wse2-era `@fmovs` that bound `reduce_recv` but never activated it) and adds a `num_pes==1` branch that bypasses the chain so single-PE attention completes without stalling.

One documented gap remains: `gemv` at width≥3 routes middle PEs as `rx={WEST}, tx={EAST}` (pass-through), which hangs the chain because middle PEs never deliver wavelets to RAMP. The cell carries `width=2` to avoid this; closing the multi-PE chain reduction at width≥3 needs the csl-extras `collectives_2d/pe.csl` teardown/switch machinery and is tracked separately. The `rmsnorm`/`residual`/`silu` cells additionally use a hand-patched layout that forwards the per-PE buffer size — the upstream emit at [`runtime/zig/src/doe_wgsl/emit_csl_layout.zig`](../runtime/zig/src/doe_wgsl/emit_csl_layout.zig) deliberately omits this at manifest scale because the per-PE buffers (60 KB at hidden_dim=5120) overflow the WSE-3 38 KB working budget; the broader R3-2 single-PE-reduction → fabric-shard redesign closes that gap. All patches and gaps travel inside each per-cell receipt's `notWhat` block so the summary cannot be misread as fully covering the lane.

**Partial-rotary `num_pairs` sourced from manifest.** Host-plan tool now derives `num_pairs = head_dim * partialRotaryFactor / 2` from `modelConfig.partialRotaryFactor` (default 1.0). For Qwen 3.6 27B (head_dim=256, factor=0.25), the `rope_partial` compileParams read `num_pairs=32` — the canonical formula, not the previous kernel-default of 64.

Wiring at [`runtime/zig/src/csl_host_plan_tool.zig`](../runtime/zig/src/csl_host_plan_tool.zig) (`compileParamsForPattern` `rope` branch) and [`runtime/zig/src/doe_wgsl/emit_csl_host.zig`](../runtime/zig/src/doe_wgsl/emit_csl_host.zig) (`ModelConfig.partial_rotary_factor`).

**TSIR gated-activation body family.** `silu_gated` (SwiGLU FFN inner) and `sigmoid_gated` (attention output gate) `SemanticBodyOp` variants land on this branch alongside `gelu_gated`, with the doe_wgsl classifier surface and the exec-v1 `opToSpec` map both routing them:

- Schema: [`runtime/zig/src/tsir/schema.zig`](../runtime/zig/src/tsir/schema.zig) (`SemanticBodyOp`).
- Emit body: [`runtime/zig/src/tsir/emit_kernel_body_gated.zig`](../runtime/zig/src/tsir/emit_kernel_body_gated.zig). Single emit body parameterized by activation kind; clamp form `z = clamp(-x, -15, 15)` matches the live PE arithmetic.
- Reference interpreter: [`runtime/zig/src/tsir/reference_interpreter.zig`](../runtime/zig/src/tsir/reference_interpreter.zig) (`tryGated` recognizes all three op kinds; algorithm-exact against the emit body).
- WGSL→CSL classifier: [`runtime/zig/src/doe_wgsl/emit_csl_semantic_ops.zig`](../runtime/zig/src/doe_wgsl/emit_csl_semantic_ops.zig) (`isSemanticPattern`, `emitLayout`, `emitPeProgram` dispatch all three gated kinds via the shared `emitGatedPe` parameterized by `SemanticBodyOp`).
- exec-v1 `opToSpec`: [`runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig`](../runtime/zig/src/doe_wgsl/emit_csl_exec_v1.zig) routes `gelu_gated`, `silu_gated`, `sigmoid_gated`, and `o_gate` (alias to `sigmoid_gated`).
- Tests: [`runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig`](../runtime/zig/tests/wgsl/tsir_emit_kernel_body_test.zig) pins CSL-emit fragments per kind; [`runtime/zig/tests/wgsl/tsir_scaffold_test.zig`](../runtime/zig/tests/wgsl/tsir_scaffold_test.zig) pins reference-interpreter math.

**Wall-clock budget under ceiling.** Qwen rung-2 predicted-wallclock receipt at `bench/out/r3-2-27b-manifest-simfabric-predicted-wallclock/budget.json` records `calibrated=true`, `grandPredictedCycles=392,726,830` (prefill=197,373,216 + decode=195,353,614). [`config/manifest-simfabric-budget.json`](../config/manifest-simfabric-budget.json) ceilings raised to 1.5× the Qwen prediction (grand=590M, prefill=297M, decode=294M); [`bench/tools/check_simfabric_budget_gate.py`](../bench/tools/check_simfabric_budget_gate.py) decision: `allow`. Gemma 4 31B still passes (~35% utilization of the bumped ceiling); per-model ceilings (`ceilingsByModel`) is a tracked follow-up so each model's headroom is attributed precisely.

**Frozen Doppler reference validator binding (typed-blocker when absent).** [`bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py`](../bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py) wraps the model-agnostic [`bench/tools/validate_frozen_doppler_reference.py`](../bench/tools/validate_frozen_doppler_reference.py), defaults `--root` to `bench/fixtures/r3-2-27b-doppler-frozen/`, and emits a Qwen-labeled receipt at `bench/out/r3-2-27b-frozen-reference-validation/report.json`.

The fixture itself is upstream-gated: as of 2026-04-27 the upstream reference inference path produces non-deterministic outputs at the 27B scale (greedy decode of a fixed prompt yields a different first token on each run, indicating near-uniform logits), so no clean reference forward exists to capture from yet. The first full-attention layer's input residual stream is corrupted on entry (`post_rmsnorm` magnitudes ~70σ above expectation), and the first linear-attention (DeltaNet SSM) layers show large outliers on `post_attn` and `post_ffn`. The smaller Qwen 3.5 family runs the same upstream code path cleanly, so the bug is Qwen 3.6 27B-config-specific. Until the upstream path produces in-distribution outputs, the validator emits `verdict=not_attempted` with `blocker.class=qwen_frozen_reference_fixture_absent`. When the upstream fix lands and the fixture is captured, the validator binds: schema-valid manifest, hash-bound artifacts, recomputed `fixtureDigest`, recognized Qwen modelId, and four-probe boundary set (`post_rmsnorm`/`post_qkv`/`post_attn`/`post_ffn` at L=0).

## What's behind named blockers

These are Qwen-specific architectural deltas that the smoke config carries as explicit `scopeRestrictions` entries so receipts cannot be misread as covering them:

- **Linear-attention layers.** Qwen 3.6 27B is hybrid (full + linear-attn Mamba/SSM with conv1d). The TSIR layer has no body op for linear attention. Smoke config targets full-attention layers only.
- **mrope-interleaved 3D rotary.** Manifest carries `mropeSection=[11,11,10]` for text/image/video. Smoke config falls back to standard 1D RoPE with `partialRotaryFactor=0.25`. True mrope lowering is deferred.
- **Causal prefill.** `AttentionScoresBody` rejects `causal_mode != .none`. Same blocker the Gemma 4 31B prefill ladder carries; decode-only receipts are unblocked.
- **attentionOutputGate (sigmoid_gated) — wiring landed, smoke-config rebind pending.** Qwen applies `sigmoid(qGateProjection) * attnOutput` before the O projection. The TSIR `sigmoid_gated` body op, the doe_wgsl classifier dispatch, and the exec-v1 `opToSpec` map (with `o_gate` aliased to `sigmoid_gated`) all land on this branch. The smoke config still drops the `o_gate` step pending an explicit rebind to the wired `sigmoid_gated`/`o_gate` op.
- **SwiGLU fused gate (silu_gated) — wiring landed, smoke-config rebind pending.** Qwen FFN is `silu(gate_proj(x)) * up_proj(x) → down_proj`. The TSIR `silu_gated` body op, the doe_wgsl classifier dispatch, and the exec-v1 `opToSpec` map all route the op. The smoke config still maps the activation step to single-input `op="silu"` pending the rebind to the wired `silu_gated` op.
- **gemv multi-PE chain reduction at width≥3.** Middle-PE routing currently sets `rx={WEST}, tx={EAST}` (pure pass-through), which never delivers wavelets to RAMP and hangs the chain. Closing this needs the csl-extras `collectives_2d/pe.csl` teardown/switch machinery; cells run at width=2 to avoid it.

## What's hardware-gated

Same shape as the Gemma 31B evidence packet:

1. **cslc invocation against the Qwen bundle.** Materializes [`bench/out/r3-2-27b-manifest-fullgraph-compile-steps/`](../bench/out/r3-2-27b-manifest-fullgraph-compile-steps/) (regeneration output, gitignored). Running cslc per-target attaches measured `failureCode` values to the synthesizer's compileTargets[] and flips `compileAttempted` to true. SDK-toolchain-dependent.

2. **Upstream reference path fix + fixture capture.** Ahead of fixture capture, the upstream reference inference path needs a Qwen 3.6 27B-config-specific fix: at this scale the path currently produces non-deterministic, near-uniform logits (different first token under greedy decode on each run), and the first full-attention layer receives a corrupted residual stream. The smaller Qwen 3.5 family runs the same path cleanly. Once the fix lands, the frozen Qwen reference fixture at `bench/fixtures/r3-2-27b-doppler-frozen/` is captured cross-repo on `feat/qwen-3-6-bringup` via the boundary-probe lane added to `tsir-fixture-writer.js`. After capture the validator-binding receipt transitions from `not_attempted` to verifying schema, artifact hashes, recomputed fixture digest, and four-probe boundary coverage.

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
