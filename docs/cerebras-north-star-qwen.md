# Doe Cerebras North Star — Qwen 3.6 27B

One Doppler-authored Qwen 3.6 27B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Mirrors the Gemma 4 31B ladder at [`docs/cerebras-north-star.md`](cerebras-north-star.md).

**Scoped today**: the 16 full-attention layers (head_dim=256, GQA 24:4). The 48 gated-DeltaNet (linear-attention SSM) layers' end-to-end coverage requires the linear-attention body op + smoke-config wiring; the body op landed on this branch (see Doe-gated below) but the smoke config still scopes to full-attention layers.

External evidence packet: [`docs/cerebras-27b-qwen-evidence.md`](cerebras-27b-qwen-evidence.md).

## Evidence layers

| Layer | Shape | Required | Status |
|---|---|---|---|
| A. Per-kernel byte-identity | Smoke | No | 2/2 pass (1L vs 64L) |
| B. 27B manifest-shape full-graph cslc compile | Manifest | Yes | **emit-spec resolved**: `attn_prefill_pe_memory_overflow` closed by kv-axis-sharded semantic pattern wiring (multi-Q body + 2D PE grid). Compile re-attempt now produces a fresh receipt class; baseline 10/15 was from the legacy `attention_tiled` route that the smoke config no longer takes. Hardware compile receipt re-baselining is hardware-gated. |
| C. 27B graph-shape execution receipt | Manifest, simfabric or WSE | Yes | per-kernel cells running (**10/10 pass** after sample + attn_decode emit fixes); follow-up: smoke-config rebind to wire silu_gated/o_gate kernels |

## Bound today (no hardware)

- [x] Smoke-config + architecture declared — `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json` (GQA 24:4, head_dim=256, hidden=5120, 64 layers, partial-rotary 0.25, queryKeyNorm, mropeSection=[11,11,10])
- [x] Per-kernel byte-identity (1L vs 64L) — `bench/tools/verify_qwen_3_6_27b_per_kernel_byte_identity.py`
- [x] Compile-target inventory — `bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py` (10 succeeded under cslc 2.10.0)
- [x] Per-kernel simfabric cells — `bench/runners/csl-runners/qwen-3-6-27b-cells/` (10 of 10 dispatch + parity-check after sample + attn_decode emit fixes at `1d2da8337`)
- [x] TSIR `silu_gated` + `sigmoid_gated` body ops + classifier wiring + exec-v1 `opToSpec` map (`o_gate` aliased to `sigmoid_gated`)
- [x] `silu_gated` / `sigmoid_gated` host-plan bindings (paired `(gate, input) → output`) and compile params
- [x] Smoke-config rebind: `op="silu_gated"` for FFN activation + new `op="o_gate"` step between attention and o_proj, both with `inputsFrom` declaring upstream step names (commit `cc88c546a`)
- [x] `causal_mode` and `sliding_window` accepted in `attention_scores` body op (commit `8e8226f4c`)
- [x] Multi-Q kv-axis-sharded body for causal-prefill — `query_seq_len > 1` widens Q to `[query_seq_len * head_dim]` and output to `[query_seq_len * (head_dim+2)]f32` (commit `6b15aae01`)
- [x] `gemv` middle-PE routing aligned with reduce-dist canonical pattern (`rx={WEST,RAMP}, tx={EAST}`; commit `d1ede0c12`)
- [x] TSIR `l2_normalize` + `conv1d_depthwise` + `linear_attention` body ops + CSL emit (commit `4fb7d8ea3`)
- [x] mrope-3D `mropeSection` plumbed through host plan rope compile params (commit `1489759c9`)
- [x] Partial-rotary `num_pairs` sourced from manifest — host-plan tool reads `partialRotaryFactor` (head_dim=256, factor=0.25 → num_pairs=32)
- [x] Wall-clock budget gate — `decision=allow` (ceiling raised 1.5× to cover Qwen prediction; Gemma still passes)
- [x] Frozen Doppler reference validator binding — `bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py` (typed-blocker when fixture absent)
- [x] External evidence doc

## Doppler-gated (cross-repo)

- [x] Doppler end-to-end coherent output for Qwen 3.6 27B — root cause was the attention output gate routing `outputGateType="swish"` to `silu` instead of HF Qwen3_5's hardcoded `sigmoid(gate)` (sign-preserving silu vs unconditionally-positive sigmoid → sign-flipped post-attention output for tokens with negative gate values, cascading to nearly-uniform logits at scale). Fixed in Doppler `feat/qwen-3-6-bringup` commit `fc04ec5c`. Diagnostic produced by `bench/tools/hf_qwen_3_6_27b_l0_post_attn_diff.py`: L=0 SSM rel_l2≈0.030 (precision noise); L=3 full-attention pre-fix rel_l2≈1.365 with mean per-token correlation ≈ -0.96 (sign-flip pattern), post-fix rel_l2≈0.068.
- [x] Frozen 4-of-4 TSIR boundary fixture capture — `bench/fixtures/r3-2-27b-doppler-frozen/` covers L=3 (first full-attention layer in Qwen 3.6 27B's `linear×3 → full` pattern; rung-7 contract probe enum `post_rmsnorm/post_qkv/post_attn/post_ffn` is fully populated for that layer). Captured by re-running Doppler `tools/run-program-bundle-reference.js --tsir-fixture-dir` post-sigmoid-fix; frozen via `bench/tools/freeze_qwen_3_6_27b_doppler_reference.py`. Validator binds: `verdict=bound`, `fixtureDigest=9c57150e98a95f6f...`, schema-valid (commit `2b6e3fbe3`).

## Doe-gated (no hardware)

- [x] **`attn_prefill` `linker_pe_memory_overflow`** — closed end-to-end. `emit_csl_semantic_ops.zig::emitAttnPrefillKvAxisShardedLayout` + `emitAttnPrefillKvAxisShardedPe` register `attention_prefill_kv_axis_sharded` as a semantic pattern; the pe_program delegates to `emit_kernel_body_attention.zig::emitKvAxisSharded` with multi-Q causal-prefill (head_dim=256, query_seq_len=8, causal). `csl_host_plan_tool.zig` supplies `width=height=512`, `kv_len=max_seq_len`, `slots_per_pe=ceilDiv(max_seq_len, num_pes)` compile params. `emit_csl_exec_v1.zig::opToSpec` routes `attention_prefill_kv_axis_sharded` to that pattern (allow_prefill=true, allow_decode=false). The smoke config's prefill attention step now uses `op="attention_prefill_kv_axis_sharded"` / `kernelKey="attn_prefill_kv_axis_sharded"`; `namedBlocker="attn_prefill_pe_memory_overflow"` removed. Regression in `tests/wgsl/exec_v1_paired_gate_canary_test.zig` pins layout exports + multi-Q body fragments. Per-PE working set ~ 32 KiB (Q stripe + K/V stripes + partials buffer) under WSE-3 48 KiB budget.
- [x] **`gemv` width>=3 row reduction** — closed by routing fused GEMV through the SDK `collectives_2d` import surface already used by SUMMA. `emitFusedGemvLayout` now imports `<collectives_2d/params>` and passes per-tile `c2d_params`; `emit_csl_fused.zig` imports `<collectives_2d/pe>` and calls `reduce_fadds(root=width-1, partial, output, out_dim_per_pe, reduce_done_id)`. This removes the hand-rolled `reduce_color` route and relies on the SDK teardown/switch FSM without vendoring SDK source.
- [x] Causal mask + sliding-window in `attention_scores` body op
- [x] Classifier + opToSpec wiring for `silu_gated` + `sigmoid_gated` + `o_gate`; smoke config rebound
- [x] Reference interpreter for the new TSIR body ops: `tryL2Normalize`, `tryConv1DDepthwise`, `tryLinearAttention` in `runtime/zig/src/tsir/reference_interpreter.zig`. All three mirror their CSL emit math (commit `8c3bcfa6d`); wired into `run()` dispatch alongside the existing tryers.
- [x] mrope-3D kernel-side validation — `emit_csl_rope.zig` now accepts `param mrope_t_pairs / mrope_h_pairs / mrope_w_pairs: i16 = 0` and asserts `T + H + W == num_pairs` at comptime when any is non-zero (commit `1812ede97`). Kernel remains mrope-agnostic for the cos/sin math (tables generated host-side with per-section position multipliers folded in); the params surface the mrope shape for receipt attribution and let a future image/video bring-up branch inside the kernel without contract changes.
- [x] Bounded multi-token decode chain receipt — `bench/tools/aggregate_qwen_3_6_27b_multi_token_decode_receipt.py` binds `bench/out/r3-2-27b-qwen-multi-token-decode/trace.json` into a typed receipt with `smokeConfigHash` + `traceHash` + per-kernel compile-dir digests; rung-1 receipt-hash-guard enforced (commit `25dcde355`).
- [x] Real-weight pin + smoke-contract audit — `bench/tools/audit_qwen_3_6_27b_smoke_contract.py` walks `qwen-3-6-27b-smoke.json` against the live exec-v1 `opToSpec` table and against `config/qwen-3-6-27b-real-weight-fixture.json`; reports `verdict=bound` for the manifest-shape full-attention slice (37 steps, 0 violations, 10 weight-tile keys pinned; commit `25dcde355`).
- [x] Cross-backend bootstrap canary for the wired gated ops — `runtime/zig/tests/wgsl/exec_v1_paired_gate_canary_test.zig` pins `silu_gated`/`sigmoid_gated`/`o_gate`/`gelu_gated` opToSpec dispatch + binding-shape contract (commit `22b16c7cc` + `25dcde355`). Canaries for the newly-landed `linear_attention`/`conv1d_depthwise`/`l2_normalize` body ops gate on the reference-interpreter follow-up above.

## Hardware-gated

- [ ] **R3-2**: Qwen 3.6 27B L1 smoke hardware receipt
- [ ] Manifest-shape hardware parity receipt — full-attention slice end-to-end on WSE, bound to Doppler reference fixture
- [ ] Speed measurement (prefill + decode tok/s)

## Acceptance bar (Layer C, scoped)

- All cslc-clean kernels dispatched on simfabric, bytes/digests recorded.
- For one prompt on the 16 full-attention layers, post_rmsnorm/post_qkv/post_attn/post_ffn at L=0 hash matches Doppler reference.
- Manifest / HostPlan / CSL / reference-fixture hash chain unbroken end-to-end.

## Integrity invariants

Same as Gemma:

- Every receipt cites the same manifest hash; mismatches are emit-time errors.
- Compile artifacts reused only by content hash.
- Shape substitution is a separate receipt class.
- Reference fixture is frozen — regeneration is a digest-changing event.
- Every kernel dispatches at manifest shape before any parity claim.

## Long-tail

- **Optimization roadmap** (post-hardware): same three items as Gemma's north star (mixed precision, fused-dequant SUMMA, cross-kernel fusion). Wedge already shipped on Gemma side.
- **End-to-end SSM coverage**: the linear-attention body op landed in this branch, but promoting from "full-attention slice" to "full Qwen 3.6 27B end-to-end" still needs (a) the smoke config rewired to dispatch `linear_attention` for the 48 SSM layers, (b) the conv1d + l2_normalize body ops composed into the SSM block in the host plan, and (c) full SSM-block parity across the composed host-plan path.
