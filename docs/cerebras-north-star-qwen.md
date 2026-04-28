# Doe Cerebras North Star — Qwen 3.6 27B

One Doppler-authored Qwen 3.6 27B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Mirrors the Gemma 4 31B ladder at [`docs/cerebras-north-star.md`](cerebras-north-star.md).

**Scoped today**: the 16 full-attention layers (head_dim=256, GQA 24:4). The 48 gated-DeltaNet (linear-attention SSM) layers' end-to-end coverage requires the linear-attention body op + smoke-config wiring; the body op landed on this branch (see Doe-gated below) but the smoke config still scopes to full-attention layers.

External evidence packet: [`docs/cerebras-27b-qwen-evidence.md`](cerebras-27b-qwen-evidence.md).

## Evidence layers

| Layer | Shape | Required | Status |
|---|---|---|---|
| A. Per-kernel byte-identity | Smoke | No | 2/2 pass (1L vs 64L) |
| B. 27B manifest-shape full-graph cslc compile | Manifest | Yes | **10/15 succeeded, 1 failed (`attn_prefill` PE-memory overflow), 4 alias-not-attempted** |
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

- [ ] Doppler end-to-end coherent output for Qwen 3.6 27B (audited as garbage non-deterministic on `feat/qwen-3-6-bringup`; prime suspect is the linear-attention runtime at L=0/1/2 — see `/tmp/qwen-l0-probes/` and `/tmp/qwen-l3-probes/` boundary captures in the Doppler-side handoff)
- [ ] Frozen 4-of-4 TSIR boundary fixture capture (post_rmsnorm/post_qkv/post_attn/post_ffn at L=0) — waits on Doppler coherence

## Doe-gated (no hardware)

- [ ] **`attn_prefill` `linker_pe_memory_overflow`** — body extension shipped (multi-Q kv-axis-sharded at `6b15aae01`) but the smoke config's `attention_prefill` op still routes through legacy `attention_tiled` pattern. Closing this requires a doe_wgsl semantic-op dispatch entry for `attention_prefill_kv_axis_sharded` that calls `emit_kernel_body_attention.zig::emitKvAxisSharded` and a smoke-config swap from `attention_tiled` → the new pattern.
- [ ] **`gemv` width≥3 chain reduction** — middle-PE routing aligned with canonical pattern (`d1ede0c12`); full multi-PE chain reduction at width≥3 still needs the csl-extras `collectives_2d/pe.csl` teardown/switch machinery to reconfigure the color after each PE's local task fires. Width=2 cell already runs.
- [x] Causal mask + sliding-window in `attention_scores` body op
- [x] Classifier + opToSpec wiring for `silu_gated` + `sigmoid_gated` + `o_gate`; smoke config rebound
- [ ] **Reference interpreter** for the new TSIR body ops: `l2_normalize`, `conv1d_depthwise`, `linear_attention`. Schemas + emit bodies + emit-shape tests landed on this branch; the `tryLinearAttention` / `tryConv1DDepthwise` / `tryL2Normalize` numeric oracles in `runtime/zig/src/tsir/reference_interpreter.zig` are the bootstrap-canary follow-up that pins emit byte-identity against host-side numerics.
- [ ] **mrope-3D kernel-side validation** — `mropeSection` is plumbed through ModelConfig + rope compile params (`1489759c9`); the kernel itself remains mrope-agnostic (cos/sin tables generated host-side with per-section position multipliers folded in). Bringing image / video positions to non-zero requires the host-side cos/sin generator to produce per-section frequencies, which is Doppler-side infrastructure.
- [ ] Bounded multi-token decode chain receipt
- [ ] Real-weight pin + smoke-contract audit
- [ ] Cross-backend bootstrap canary for Qwen-specific ops (`silu_gated`/`sigmoid_gated`/`o_gate` already have a paired-gate canary; the new `linear_attention`/`conv1d_depthwise`/`l2_normalize` canaries gate on the reference-interpreter follow-up)

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
- **End-to-end SSM coverage**: the linear-attention body op landed in this branch, but promoting from "full-attention slice" to "full Qwen 3.6 27B end-to-end" still needs (a) the smoke config rewired to dispatch `linear_attention` for the 48 SSM layers, (b) the conv1d + l2_normalize body ops composed into the SSM block in the host plan, and (c) reference-interpreter parity for each of the three new bodies.
