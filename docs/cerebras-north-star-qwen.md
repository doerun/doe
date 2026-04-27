# Doe Cerebras North Star — Qwen 3.6 27B

One Doppler-authored Qwen 3.6 27B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Mirrors the Gemma 4 31B ladder at [`docs/cerebras-north-star.md`](cerebras-north-star.md).

**Scoped today**: the 16 full-attention layers (head_dim=256, GQA 24:4). The 48 gated-DeltaNet (linear-attention SSM) layers are explicitly out of scope until that body op lands; smoke config carries the restriction as `scopeRestrictions`.

External evidence packet: [`docs/cerebras-27b-qwen-evidence.md`](cerebras-27b-qwen-evidence.md).

## Evidence layers

| Layer | Shape | Required | Status |
|---|---|---|---|
| A. Per-kernel byte-identity | Smoke | No | 2/2 pass (1L vs 64L) |
| B. 27B manifest-shape full-graph cslc compile | Manifest | Yes | **10/15 succeeded, 1 failed (`attn_prefill` PE-memory overflow), 4 alias-not-attempted** |
| C. 27B graph-shape execution receipt | Manifest, simfabric or WSE | Yes | per-kernel cells running (**9/10 pass**); 3 known emit bugs |

## Bound today (no hardware)

- [x] Smoke-config + architecture declared — `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json` (GQA 24:4, head_dim=256, hidden=5120, 64 layers, partial-rotary 0.25, queryKeyNorm)
- [x] Per-kernel byte-identity (1L vs 64L) — `bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py` (2/2 pass)
- [x] Compile-target inventory — `bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py` (10 succeeded under cslc 2.10.0)
- [x] Per-kernel simfabric cells — `bench/runners/csl-runners/qwen-3-6-27b-cells/` (9 of 10 dispatch + parity-check)
- [x] TSIR `silu_gated` + `sigmoid_gated` body ops — schema, emit body, reference interpreter, tests
- [x] Partial-rotary `num_pairs` sourced from manifest — host-plan tool reads `partialRotaryFactor` (head_dim=256, factor=0.25 → num_pairs=32)
- [x] Wall-clock budget gate — `decision=allow` (ceiling raised 1.5× to cover Qwen prediction; Gemma still passes)
- [x] Frozen Doppler reference validator binding — `bench/tests/test_validate_frozen_qwen_3_6_doppler_reference.py` (skip-when-absent)
- [x] External evidence doc

## Doppler-gated (cross-repo)

- [ ] Doppler end-to-end coherent output for Qwen 3.6 27B (audited as garbage earlier; status unverified on current `feat/qwen-3-6-bringup` head)
- [ ] Frozen 4-of-4 TSIR boundary fixture capture (post_rmsnorm/post_qkv/post_attn/post_ffn at L=0) — waits on Doppler coherence

## Doe-gated (no hardware)

- [ ] `attn_prefill` `linker_pe_memory_overflow` — per-PE residency redesign (same blocker Gemma's prefill ladder carries)
- [ ] `sample` kernel: writes last PE's local index instead of global argmax
- [ ] `gemv` kernel: width≥3 middle-PE pass-through deadlock (`rx={WEST}, tx={EAST}` never delivers wavelets to RAMP)
- [ ] `attn_decode` kernel: missing `.activate = reduce_task_id` annotation on `@fmovs(&incoming, reduce_in)`
- [ ] Causal mask in `attention_scores` body op (Gemma carries it too)
- [ ] Classifier + opToSpec wiring for `silu_gated` + `sigmoid_gated` (body ops exist; smoke config drops `o_gate` and maps SwiGLU's gate-mul to plain `silu`)
- [ ] Bounded multi-token decode chain receipt
- [ ] Real-weight pin + smoke-contract audit
- [ ] Cross-backend bootstrap canary for Qwen-specific ops

## Hardware-gated

- [ ] **R3-2**: Qwen 3.6 27B L1 smoke hardware receipt
- [ ] Manifest-shape hardware parity receipt — full-attention slice end-to-end on WSE, bound to Doppler reference fixture
- [ ] Speed measurement (prefill + decode tok/s)

## Out-of-scope today (named blockers in evidence packet)

The current Qwen north star covers the full-attention slice only. To promote to full Qwen 3.6 27B end-to-end:

- [ ] TSIR `linear_attention` body op + emit + reference interpreter (covers the 48 gated-DeltaNet layers)
- [ ] TSIR `conv1d` body op (depthwise, kernel size 4 — Mamba-family standard)
- [ ] L2-normalize body op (DeltaNet Q/K pre-attention)
- [ ] mrope-interleaved 3D rotary (manifest carries `mropeSection=[11,11,10]`; current fallback is 1D RoPE)

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
- **Linear-attention SSM lowering** is the largest piece of out-of-scope work; promotion to full-model coverage requires it.
