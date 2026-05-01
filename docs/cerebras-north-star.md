# Doe Cerebras North Star

One Doppler-authored Gemma 4 31B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Layer B full-graph compile is closed only for the emitted compile-target inventory. Token-output inference evidence is fail-closed until the HostPlan preserves the explicit post-layer logits path and every sample launch consumes a typed logits producer.

External evidence packet for Cerebras: [`docs/cerebras-31b-evidence.md`](cerebras-31b-evidence.md).

## Evidence layers

| Layer | Shape | Required for hardware ask | Status |
|---|---|---|---|
| A. Real-canary CSL identity | Smoke | No (regression bookkeeping) | 24/24 pass across 6 kernels × 4 backends |
| B. 31B manifest-shape full-graph compile | Manifest | Yes | **Closed for emitted compile inventory only.** Not token-output inference evidence unless the inventory includes the post-layer logits path |
| C. 31B graph-shape execution receipt | Manifest, simfabric or WSE | Yes | **Blocked fail-closed.** Sample dispatch is bound, session-tiled lm-head is the active path, and the real session remains checkpoint-stopped before transcript output |

## Bound today (no hardware)

- [x] Full-graph compile receipt — `bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`; compile evidence for the emitted target inventory, not a token-output inference receipt
- [x] Per-kernel byte-identity (1L vs 61L) — `bench/tests/test_one_layer_per_kernel_byte_identity.py` (2/2 pass, 17 shared kernels match)
- [x] Frozen 4-of-4 TSIR boundary fixture — `bench/fixtures/r3-1-31b-doppler-frozen/tsir-snapshots/` (`fixtureDigest=8cc17070fedf9c…`); greedy decode of "The color of the sky is" → "blue"
- [x] Frozen-reference validator — `bench/tools/validate_frozen_doppler_reference.py` (`schemaValid=true`, `bound=true`, `verdict="bound"`)
- [x] Multi-PE kv-axis-sharded attention emit — `runtime/zig/src/tsir/emit_kernel_body_attention.zig::emitKvAxisSharded`; identity test 13/13 pass; head_dim=512 fits per-PE SRAM
- [x] Host-side log-sum-exp stitch — `bench/tools/attention_kv_axis_sharded_stitch.py`
- [x] Wall-clock budget gate — `bench/tools/check_simfabric_budget_gate.py` (`decision=allow`); 12/12 tests pass
- [x] Bounded multi-token decode chain on simfabric — `bench/out/r3-1-31b-multi-token-decode/receipt.json`
- [x] Cross-backend bootstrap canary — 12/12 pass across `webgpu-generic`, `wse3`, `msl`, `spir-v`
- [x] Real-weight pin + smoke-contract audit — `bench/out/r3-1-31b-real-weight-smoke-extraction/{receipt,audit}.json`

## Hardware-gated

- [ ] **R3-1**: 31B L1 smoke hardware receipt (`gemma_4_31b_layer_block_smoke.py --num-layers 1`)
- [ ] **R3-3**: Manifest-shape hardware parity receipt — 23-kernel graph end-to-end on WSE, bound to Doppler reference fixture
- [ ] Speed measurement: prefill + decode tok/s (simfabric is correctness-only)

## Layer C rung ladder (manifest-shape simfabric)

| # | Rung | Status |
|---|---|---|
| 0 | Per-target compile cache | Module landed; driver wiring follow-up |
| 1 | Schema-enforced hash spine | 15/15 tests pass; wired into 6 receipt writers |
| 2 | Predicted simfabric wall-clock | 18/18 tests pass; calibration via canary proxy |
| 3 | Per-kernel manifest-shape dispatch | Runner landed; manifest-shape simfabric exceeds 1800s timeout — hardware-gated |
| 4 | Layout receipt | Runner landed; hardware-gated for same reason |
| 5 | Frozen Doppler reference fixture | **Closed**, 4-of-4 probes bound |
| 6 | 1-of-60-layer first-token parity | Per-kernel byte-identity precondition closed; sharded attention emit closed |
| 7 | Single-block parity with intra-block probes | Pending hardware |
| 8 | Full 60-layer prefill + first-token | Pending hardware |
| 9 | Multi-token continuation | Pending hardware |

Rungs are bring-up phases, not a strict prerequisite chain. Rungs 3-4
catch kernel-in-isolation pathologies (cslc reject on wse3, fabric fit,
dispatch timeout taxonomy, per-kernel byte/digest stability). Rungs 6-9
catch composition, phase-order, lm-head routing, and inter-kernel
handoff bugs (see Active fail-closed queue items 1-4 for concrete
examples that per-kernel manifest-shape dispatch passed through).
Neither side subsumes the other.

## Acceptance bar (Layer C)

Load-bearing for the correctness claim:

- For one prompt, prefill + first-token logits hash matches frozen Doppler reference at L=1.
- Manifest / HostPlan / CSL / reference-fixture hash chain unbroken end-to-end.

Regression net, parallel and not a prerequisite:

- All 23 manifest-shape kernels dispatched on simfabric, bytes/digests recorded.

Per-kernel manifest-shape dispatch is worth producing once and rerunning
on kernel change, but it cannot catch composition / phase-order /
lm-head-routing / graph-completeness bugs by construction — each probe
runs one kernel in isolation. The end-to-end hardware receipt with
hash-equal logits parity is what closes the Cerebras correctness claim;
per-kernel manifest-shape dispatch is the cheap regression catch
between hardware runs and the path to non-proxied simfabric wallclock
calibration.

## Active fail-closed queue

These items gate any claim that Gemma 4 31B af16 runs real prefill/decode on the Cerebras simulator:

1. **Landed in source:** manifest-driven lm-head resolver rejects Q4K lm-head selection unless an explicit `lm_head.weight` exists, and accepts tied dense F16/BF16/F32 only through `embed_tokens.weight`.
2. **Landed in source:** tied dense lm-head routes through the full-vocabulary `lm_head_prefill_stable` SUMMA target with one-row logits tiles and F16-to-F32 weight staging.
3. **Landed in source:** the Gemma 4 31B execution-v1 smoke graph carries explicit final-norm / lm-head / sample tails for both prefill-generated and decode-generated tokens.
4. **Landed in source:** HostPlan lowering rejects `sample` unless the immediately preceding same-phase step is a compatible logits producer; compute after same-phase sample also fails closed.
5. **Partially landed runtime step:** real session runtime stages real weights, binds host I/O layout, launches serial checkpointed kernels, and carries scheduler state. The latest historical deep scratch trace is `bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt81.json`; it is checkpoint-stopped and has no token/logit/KV transcript. **Active front:** frozen Doppler sky prompt, not the generic two-token stress path. The active run uses prompt `The color of the sky is`, Doppler prompt-token hash `85b8d0e590815c3e97f346806977853e3d0528a232fd7c781d1e9cfcb92a8b55`, expected first generated token `9503` (`blue`), and decode step-1 stop token `106`, with a fresh frozen-sky checkpoint/session tree. The generic launch-2 tiled_31b Q4K row-split remains plumbing evidence for the compact GEMV route and durable tile reuse; the acceptance target is the complete frozen-sky generated-token/logits/lm-head/sample/KV transcript.
6. **Partially landed artifact step:** the f16 CSL dtype contract and bounded-smoke schema are gate-covered. The gate now accepts a complete `realSessionRuntime.status=output_ready` transcript as the end-to-end prefill/decode evidence path, superseding stale per-kernel lm-head evidence only after generated token IDs, lm-head dispatch records, and KV digests are present. The current bounded receipt still records `inferenceEvidenceGate.dispatch_evidence_lm_head_unbound` because no token/logit/KV transcript exists yet.
7. **Landed in source:** focused fail-closed tests cover sample-without-logits, invalid lm-head dtype selection, prefill/decode feedback shape, f16 dtype contract drift, and blocked-receipt bounded evidence emission.

## Integrity invariants

- Every receipt cites the same manifest hash; mismatches are emit-time errors.
- Compile artifacts reused only by content hash, never filename.
- Shape substitution (e.g., `hidden_dim=1024` instead of 5120) is a separate receipt class.
- The reference fixture is frozen — regeneration is a digest-changing event, not a silent refresh.
- Every kernel dispatches at manifest shape (rung 4) before any parity claim.
- Graph-to-HostPlan inventory equality is required for inference claims; dropping a source graph target must produce a typed unsupported result.
- `sample` is never valid as token-output evidence without a typed logits input from the compatible lm-head launch.

## Optimization roadmap (post-hardware)

These land after the first hardware receipt. Today's lowering is correctness-first f32; each item below is a known leverage point.

### 1. Mixed precision (bf16/f16 storage, f32 accums)

Switch CSL emit from all-f32 to mixed precision: bf16 (preferred over f16 for softmax range safety) for KV cache, attention Q/K/V/O buffers, residual stream, RMSNorm storage; keep f32 for softmax max/sum reductions and matmul accumulators. Halves KV memory, roughly doubles attention `slots_per_pe` budget for head_dim=512 sharded routing, matches the WSE-3 silicon design point. Touches `body_emit.requireElem` assertions, `kv_write` cache buffer types, `gemv` dequant output type, RoPE/GeLU up-cast for `math.exp`/`tanh` transcendentals. Q4K weights on disk unchanged.

### 2. Fused-dequant SUMMA tiled matmul (or Q4K pre-pass kernel)

On prefill, the SUMMA tiled matmul (`compile/tiled/`) ingests f32 A/B/C tiles, so host dequantizes Q4K → f32 in CPU memory and pushes f32 over the memcpy fabric — 4× more bandwidth than necessary. Two design options: (a) emit a fused-dequant variant that ingests Q4K `u8` bytes in `B_tile` and dequants per inner-product step, or (b) a one-time Q4K → f32 pre-pass kernel materializing f32 tiles in PE SRAM, amortized across subsequent matmul launches. Decode GEMV path already does (a).

### 3. Cross-kernel fusion in CSL emit

CSL emit today keeps RMSNorm, matmul, residual, gate/up/gelu, and RoPE as separate kernels. Doppler/WebGPU runtime ships fused twins — rmsnorm+matmul (saves a hidden-state SRAM round-trip), matmul+residual (saves the residual broadcast pass), gate+up+gelu (collapses three FFN dispatches into one; ~47% prefill dispatch reduction projected on the Doppler side). Port these as new CSL emit body variants behind capability flags, mirroring the WGSL fused kernel registry. Highest leverage on prefill where dispatch count dominates wall-clock.

## Long-tail (housekeeping, not on critical path)

- **R1-x**: TSIR-as-source-of-truth migrations. Live-kernel tally tracked in `docs/status/tsir.md`.
- **R2-x**: 3 1B / E2B control-lane diagnostics. Closed or non-load-bearing.
- **R4-1**: Performance baselines vs A3/A3 Ultra/A4/TPU v5e/v6e/v7. Far out, depends on hardware receipt + perf receipt.
- **P-x**: Doppler-on-Doe Metal parity, second Doe model, `doe-gpu diagnose` operator-diff.
- **H-x**: Python file sharding, status-shard splits, Doppler reference regen.
