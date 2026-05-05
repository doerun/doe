# Doe Cerebras evidence ledger

One Doppler-authored Gemma 4 31B model program, verifiable on browser WebGPU and Cerebras WSE with one source-identity chain. Layer B full-graph compile is closed only for the emitted compile-target inventory. Token-output inference evidence is fail-closed until the HostPlan preserves the explicit post-layer logits path and every sample launch consumes a typed logits producer.

External evidence packet for Cerebras: bundle archive built via [`docs/cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md), governance + claim scope in [`docs/hardware-validation-appendix.md`](hardware-validation-appendix.md). Lane front door: [`docs/cerebras.md`](cerebras.md).

## Evidence layers

| Layer | Shape | Required for hardware ask | Status |
|---|---|---|---|
| A. Real-canary CSL identity | Smoke | No (regression bookkeeping) | 24/24 pass across 6 kernels × 4 backends |
| B. 31B manifest-shape full-graph compile | Manifest | Yes | **Closed for emitted compile inventory only.** Not token-output inference evidence unless the inventory includes the post-layer logits path |
| C. 31B graph-shape execution receipt | Manifest, simfabric or WSE | Yes | **Blocked fail-closed.** Sample dispatch is bound, session-tiled lm-head is the active path, and the real session remains checkpoint-stopped before transcript output |

## Bound today (no hardware)

- [x] Full-graph compile receipt — `bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`; compile evidence for the emitted target inventory, not a token-output inference receipt
- [x] Per-kernel byte-identity (Gemma 1L vs 61L) — `bench/tests/test_one_layer_per_kernel_byte_identity.py` (2/2 pass, 17 shared kernels match)
- [x] Per-kernel byte-identity (Qwen 1L vs 64L) — `bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py` (2/2 pass, 15 shared kernels match)
- [ ] Qwen frozen-reference validator — `bench/tests/test_validate_frozen_qwen_3_6_doppler_reference.py` remains fail-closed because the frozen Qwen reference manifest is missing the L=0 probes
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

## Layer C milestone queue (manifest-shape simfabric)

| Milestone | Status |
|---|---|
| Per-target compile cache | Module landed; driver wiring follow-up |
| Schema-enforced hash spine | 15/15 tests pass; wired into 6 receipt writers |
| Predicted simfabric wall-clock | 18/18 tests pass; calibration via canary proxy |
| Per-kernel manifest-shape dispatch | Runner landed; manifest-shape simfabric exceeds 1800s timeout — hardware-gated |
| Layout receipt | Runner landed; hardware-gated for same reason |
| Frozen Doppler reference fixture | **Closed**, 4-of-4 probes bound |
| 1-of-60-layer first-token parity | Per-kernel byte-identity precondition closed; sharded attention emit closed |
| Single-block parity with intra-block probes | Pending hardware |
| Full 60-layer prefill + first-token | Pending hardware |
| Multi-token continuation | Pending hardware |

These are bring-up phases, not a strict prerequisite chain. Per-kernel
manifest-shape dispatch and layout-receipt steps catch kernel-in-isolation
pathologies (cslc reject on wse3, fabric fit, dispatch timeout taxonomy,
per-kernel byte/digest stability). The 1-of-60 / single-block /
full-60-layer / multi-token-continuation steps catch composition,
phase-order, lm-head routing, and inter-kernel handoff bugs (see Active
fail-closed queue items 1-4 for concrete examples that per-kernel
manifest-shape dispatch passed through). Neither side subsumes the other.

## Acceptance bar (Layer C)

Load-bearing for the correctness claim:

- For one prompt, prefill + generated-token IDs match the frozen Doppler
  reference at L=1, and per-step logits artifacts compare under the declared
  Doppler tolerance policy.
- Manifest / HostPlan / CSL / reference-fixture hash chain unbroken end-to-end.

Regression net, parallel and not a prerequisite:

- All 23 manifest-shape kernels dispatched on simfabric, bytes/digests recorded.

Per-kernel manifest-shape dispatch is worth producing once and rerunning
on kernel change, but it cannot catch composition / phase-order /
lm-head-routing / graph-completeness bugs by construction — each probe
runs one kernel in isolation. The end-to-end hardware receipt with exact
generated-token parity, logits digest/tolerance evidence, lm-head dispatch
evidence, and KV-cache digests is what closes the Cerebras correctness claim;
per-kernel manifest-shape dispatch is the cheap regression catch between
hardware runs and the path to non-proxied simfabric wallclock calibration.

## Active fail-closed queue

These items gate any claim that Gemma 4 31B af16 runs real prefill/decode on the Cerebras simulator:

1. **Landed in source:** manifest-driven lm-head resolver rejects Q4K lm-head selection unless an explicit `lm_head.weight` exists, and accepts tied dense F16/BF16/F32 only through `embed_tokens.weight`.
2. **Landed in source:** tied dense lm-head routes through the full-vocabulary `lm_head_prefill_stable` SUMMA target with one-row logits tiles and F16-to-F32 weight staging.
3. **Landed in source:** the Gemma 4 31B execution-v1 smoke graph carries explicit final-norm / lm-head / sample tails for both prefill-generated and decode-generated tokens.
4. **Landed in source:** HostPlan lowering rejects `sample` unless the immediately preceding same-phase step is a compatible logits producer; compute after same-phase sample also fails closed.
5. **Partially landed runtime step:** real session runtime stages real weights, binds host I/O layout, launches checkpointed kernels, and carries scheduler state. The latest historical deep scratch trace is `bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt81.json`; it is checkpoint-stopped and has no token/logit/KV transcript. **Active front:** the compact non-chat Doppler parity target `<bos>sky color is`, backed by `bench/out/doppler-reference/gemma-4-31b-af16-bos-raw-sky-color-is-prefill-decode2/doppler_int4ple_reference_export.json` and live session tree `bench/out/r3-1-31b-af16-hostplan-session-bos-raw-sky-color-is-fast-embed512`. The frozen-sky session/checkpoint tree is preserved as historical acceptance state, but the live simfabric lane moved to the compact BOS sky target to reach complete generated-token/logits/lm-head/sample/KV transcript evidence first. The generic launch-2 tiled_31b Q4K row-split remains plumbing evidence for durable tile reuse; concurrent Q4K shard attempts stall at `SdkRuntime.run()` on this simfabric host, so the active compact lane uses one Q4K shard and the validated height-4 output PE row tile via `--session-prefill-q4k-gemv-output-pe-rows`. Clean retries can use the explicit `--session-embed-roi-hidden-per-pe` embed ROI override, which is budget-checked and recorded in the ROI spec. **Landed in source:** `tiled_31b` now lowers as explicit `prefill_q4k_gemv` in HostPlan/simulator-plan metadata, compile-source materialization, runtime scheduling, execution-plan transforms, receipts, and the f16 dtype contract. The run that stopped at L5 can resume only after regenerating the session artifacts so the checkpoint sees the canonical pattern and the RoPE/attention logical-layout bridges.
6. **Partially landed artifact step:** the f16 CSL dtype contract and bounded-smoke schema are gate-covered. The gate now accepts a complete `realSessionRuntime.status=output_ready` transcript as the end-to-end prefill/decode evidence path, superseding stale per-kernel lm-head evidence only after generated token IDs, lm-head dispatch records, and KV digests are present. The current bounded receipt still records `inferenceEvidenceGate.dispatch_evidence_lm_head_unbound` because no token/logit/KV transcript exists yet.
7. **Landed in source:** focused fail-closed tests cover sample-without-logits, invalid lm-head dtype selection, prefill/decode feedback shape, f16 dtype contract drift, and blocked-receipt bounded evidence emission.

## Current compiler hardening state

The `tiled_q4k_gemv_batched_runtime` substitution has been promoted into an explicit prefill Q4K GEMV contract in source. The accepted regenerated state is a HostPlan/compiler target whose pattern name, Q4K materialization transform, shape parameters, compile-target hash, simulator plan entry, launch receipt, checkpoint metadata, and f16 numerical contract all agree without runner-side inference from `tiled_31b`.

The live Gemma `<bos>sky color is` session remains the first proof path. Regenerate the HostPlan/session artifacts, resume from the checkpointed L4 state with `--allow-checkpoint-canonicalization-drift` plus runner-drift allowance when needed, and keep the generated-token/logits/lm-head/sample/KV transcript gate as the evidence target rather than replacing it with a narrower kernel-only receipt. Qwen 3.6 27B af16 is the second model target for the same contract: model-specific dimensions, layer-body differences, and Qwen-only ops stay in HostPlan/runtime params, while Q4K -> f16 prefill GEMV patterning and receipt semantics stay shared.

## Integrity invariants

- Every receipt cites the same manifest hash; mismatches are emit-time errors.
- Compile artifacts reused only by content hash, never filename.
- Shape substitution (e.g., `hidden_dim=1024` instead of 5120) is a separate receipt class.
- The reference fixture is frozen — regeneration is a digest-changing event, not a silent refresh.
- Every kernel dispatches at manifest shape (per-kernel manifest-shape dispatch step) before any parity claim.
- Per-class CSL kernel bytes must be numLayers-invariant before an L=1 run can stand in for a full-depth parity claim.
- Materialized compile roots under `bench/out/*manifest-fullgraph-compile-steps/` must be regenerated after emitter changes before byte-identity or dispatch evidence is restated.
- Graph-to-HostPlan inventory equality is required for inference claims; dropping a source graph target must produce a typed unsupported result.
- `sample` is never valid as token-output evidence without a typed logits input from the compatible lm-head launch.

## Optimization roadmap (post-hardware)

These land after the first hardware receipt. Correctness-first lowering is the rule today, with two shipped exceptions: the `fused_gemv_dequant` f16 lane (full f16 storage / Q4K dequant / accumulator / output for narrow-output GEMV used by decode + lm-head + dense GEMV ops, via `runtime/zig/src/doe_wgsl/emit_csl_fused.zig::emitForElem(.f16)`) and the RMSNorm f16 output pack (`runtime/zig/src/doe_wgsl/emit_csl_rmsnorm_pack.zig` plus the single-buffer pack module `runtime/zig/src/tsir/emit_csl_f16_pack.zig`). Each item below targets the wide-output kernels and activation buffers that remain f32 today.

### 1. Mixed precision (bf16/f16 storage, f32 accums)

Extend the `fused_gemv_dequant` f16 lane (already shipped) to the still-f32 wide paths: KV cache, attention Q/K/V/O buffers, residual stream, RMSNorm storage, and the SUMMA tiled matmul output. bf16 preferred over f16 for softmax range safety; f32 stays for softmax max/sum reductions and SUMMA matmul accumulators. Halves KV memory, roughly doubles attention `slots_per_pe` budget for head_dim=512 sharded routing, matches the WSE-3 silicon design point. Touches `body_emit.requireElem` assertions, `kv_write` cache buffer types, `tiled_matmul` / `tiled_matmul_q4k_dequant_b` output types, RoPE/GeLU up-cast for `math.exp`/`tanh` transcendentals. Q4K weights on disk unchanged.

### 2. Fused-dequant SUMMA tiled matmul (or Q4K pre-pass kernel)

The SUMMA tiled matmul has two emitted variants: the plain f32 path (`tiled_matmul` → `runtime/zig/src/doe_wgsl/emit_csl_matmul.zig`), where the host dequantizes Q4K → f32 in CPU memory and pushes f32 over the memcpy fabric (4× more bandwidth than necessary), and the fused-dequant Q4K-byte ingestion variant (`tiled_matmul_q4k_dequant_b` → `runtime/zig/src/doe_wgsl/emit_csl_matmul_q4k.zig`), which decodes Q4K bytes per broadcast step into a still-f32 `B_tile`. The decode GEMV is end-to-end f16 already via the `fused_gemv_dequant` f16 lane. Outstanding work: extend f16 to the SUMMA `B_tile` and output once item 1 widens the activation lane, and / or land option (b) — a one-time Q4K → f16 pre-pass kernel materializing tiles in PE SRAM amortized across subsequent matmul launches.

### 3. Cross-kernel fusion in CSL emit

CSL emit today keeps RMSNorm, matmul, residual, gate/up/gelu, and RoPE as separate kernels. Doppler/WebGPU runtime ships fused twins — rmsnorm+matmul (saves a hidden-state SRAM round-trip), matmul+residual (saves the residual broadcast pass), gate+up+gelu (collapses three FFN dispatches into one; ~47% prefill dispatch reduction projected on the Doppler side). Port these as new CSL emit body variants behind capability flags, mirroring the WGSL fused kernel registry. Highest leverage on prefill where dispatch count dominates wall-clock.

## Long-tail (housekeeping, not on critical path)

- **R1-x**: TSIR-as-source-of-truth migrations. Live-kernel tally tracked in `docs/status/tsir.md`.
- **R2-x**: 3 1B / E2B control-lane diagnostics. Closed or non-load-bearing.
- **R4-1**: Performance baselines vs A3/A3 Ultra/A4/TPU v5e/v6e/v7. Far out, depends on hardware receipt + perf receipt.
- **P-x**: Doppler-on-Doe Metal parity, second Doe model, `doe-gpu diagnose` operator-diff.
- **H-x**: Python file sharding, status-shard splits, Doppler reference regen.
