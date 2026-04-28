# Doe Cerebras North Star — Qwen 3.6 27B

One Doppler-authored Qwen 3.6 27B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Mirrors the Gemma 4 31B ladder at [`docs/cerebras-north-star.md`](cerebras-north-star.md).

**Scoped today**: the full hybrid Qwen 3.6 27B architecture at non-hardware scope: 16 full-attention layers plus 48 gated-DeltaNet SSM layers (conv1d_depthwise -> l2_normalize(q/k) -> linear_attention). WSE receipts remain hardware-gated under R3-2.

External evidence packet: [`docs/cerebras-27b-qwen-evidence.md`](cerebras-27b-qwen-evidence.md).

## Evidence layers

| Layer | Shape | Required | Status |
|---|---|---|---|
| A. Per-kernel byte-identity | Smoke | No | 2/2 pass (1L vs 64L) |
| B. 27B manifest-shape full-graph cslc compile | Manifest | Yes | **bound clean**: current receipt records `blocker.class="none"` and no accepted compile blockers. Hardware execution remains R3-2 gated. |
| C. 27B graph-shape execution receipt | Manifest, simfabric or WSE | Yes | per-kernel cells running (**10/10 pass** after sample + attn_decode emit fixes); non-hardware smoke config now includes the 48 SSM layer body sequence; WSE receipt remains R3-2 gated |

## Bound today (no hardware)

- [x] Smoke-config + architecture declared — `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json` (GQA 24:4, head_dim=256, hidden=5120, 64 layers, partial-rotary 0.25, queryKeyNorm, mropeSection=[11,11,10])
- [x] Per-kernel byte-identity (1L vs 64L) — `bench/tools/verify_qwen_3_6_27b_per_kernel_byte_identity.py`
- [x] Compile-target inventory — `bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`; see `bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json` for current target counts and blocker state.
- [x] Per-kernel simfabric cells — `bench/runners/csl-runners/qwen-3-6-27b-cells/` (10 of 10 dispatch + parity-check after sample + attn_decode emit fixes at `1d2da8337`)
- [x] TSIR `silu_gated` + `sigmoid_gated` body ops + classifier wiring + exec-v1 `opToSpec` map (`o_gate` aliased to `sigmoid_gated`)
- [x] `silu_gated` / `sigmoid_gated` host-plan bindings (paired `(gate, input) → output`) and compile params
- [x] Smoke-config rebind: `op="silu_gated"` for FFN activation + new `op="o_gate"` step between attention and o_proj, both with `inputsFrom` declaring upstream step names (commit `cc88c546a`)
- [x] 48 SSM layer smoke-config rebind: `conv1d_depthwise` -> `l2_normalize` (Q/K) -> `linear_attention` with `repeat=48`, host-plan compile params/bindings, and semantic CSL emit via the TSIR body ops
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
- [x] **`attn_prefill` manifest-shape cslc fanout** — closed by removing per-tile `pe_id` / `num_pes` specialization from `@set_tile_code`; the PE program derives tile identity through CSL `<layout>` coordinates. The manifest-shape target now compiles cleanly through the SDK driver and the Qwen full-graph compile receipt reports no accepted blockers.
- [x] **`gemv` width>=3 row reduction** — closed by routing fused GEMV through the SDK `collectives_2d` import surface already used by SUMMA. `emitFusedGemvLayout` now imports `<collectives_2d/params>`, reserves both x and y collectives task-id pairs for SDK layout validation, and passes per-tile `c2d_params`; `emit_csl_fused.zig` imports `<collectives_2d/pe>` and calls `reduce_fadds(root=width-1, partial, output, out_dim_per_pe, reduce_done_id)`. This removes the hand-rolled `reduce_color` route and relies on the SDK teardown/switch FSM without vendoring SDK source.
- [x] Causal mask + sliding-window in `attention_scores` body op
- [x] Classifier + opToSpec wiring for `silu_gated` + `sigmoid_gated` + `o_gate`; smoke config rebound
- [x] Classifier + opToSpec + host-plan binding wiring for SSM body ops: `conv1d_depthwise`, `l2_normalize`, and `linear_attention`; smoke config now dispatches the composed SSM block with `repeat=48`.
- [x] Reference interpreter for the new TSIR body ops: `tryL2Normalize`, `tryConv1DDepthwise`, `tryLinearAttention` in `runtime/zig/src/tsir/reference_interpreter.zig`. All three mirror their CSL emit math (commit `8c3bcfa6d`); wired into `run()` dispatch alongside the existing tryers.
- [x] mrope-3D kernel-side validation — `emit_csl_rope.zig` now accepts `param mrope_t_pairs / mrope_h_pairs / mrope_w_pairs: i16 = 0` and asserts `T + H + W == num_pairs` at comptime when any is non-zero (commit `1812ede97`). Kernel remains mrope-agnostic for the cos/sin math (tables generated host-side with per-section position multipliers folded in); the params surface the mrope shape for receipt attribution and let a future image/video bring-up branch inside the kernel without contract changes.
- [x] Bounded multi-token decode chain receipt — `bench/tools/aggregate_qwen_3_6_27b_multi_token_decode_receipt.py` binds `bench/out/r3-2-27b-qwen-multi-token-decode/trace.json` into a typed receipt with `smokeConfigHash` + `traceHash` + per-kernel compile-dir digests; rung-1 receipt-hash-guard enforced (commit `25dcde355`).
- [x] Real-weight pin + smoke-contract audit — `bench/tools/audit_qwen_3_6_27b_smoke_contract.py` walks `qwen-3-6-27b-smoke.json` against the live exec-v1 `opToSpec` table and against `config/qwen-3-6-27b-real-weight-fixture.json`; reports `verdict=bound` for the manifest-shape full-attention slice (37 steps, 0 violations, 10 weight-tile keys pinned; commit `25dcde355`).
- [x] Cross-backend bootstrap canary for the wired gated ops and SSM body ops — `runtime/zig/tests/wgsl/exec_v1_paired_gate_canary_test.zig` pins `silu_gated`/`sigmoid_gated`/`o_gate`/`gelu_gated` plus `linear_attention`/`conv1d_depthwise`/`l2_normalize` opToSpec dispatch and binding-shape contracts.

## Hardware-gated

- [ ] **R3-2**: Qwen 3.6 27B L1 smoke hardware receipt
- [ ] Manifest-shape hardware parity receipt — full-attention slice end-to-end on WSE, bound to Doppler reference fixture
- [ ] Speed measurement (prefill + decode tok/s)

## Acceptance bar (Layer C, scoped)

- Manifest compile targets are cslc-clean in the receipt, and per-kernel simfabric cells continue to carry bytes/digests for the non-hardware execution surface.
- For one prompt on the full hybrid architecture, post_rmsnorm/post_qkv/post_attn/post_ffn plus the SSM body-op boundaries hash-match the Doppler reference at the frozen probe points.
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
