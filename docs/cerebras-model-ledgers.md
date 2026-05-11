# Doe Cerebras model ledgers

Per-model acceptance bars and blocker queues for the Doppler -> Doe ->
Cerebras lane. This file is the active ledger for model-specific state.

Current counts and verdicts belong in receipts and generated snapshots, not in
this prose file. Refresh the status snapshot from [`cerebras.md`](cerebras.md)
when you need current pass/fail totals.

External packet and operators:

- lane front door: [`cerebras.md`](cerebras.md)
- hardware operator runbook and governance: [`cerebras-hardware-runbook.md`](cerebras-hardware-runbook.md)
- evidence bundle source: [`cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md)
- generated bundle pointer: [`cerebras-evidence-bundle-pointer.md`](cerebras-evidence-bundle-pointer.md)

## Gemma 4 31B dense

One Doppler-authored Gemma 4 31B model program, verifiable on browser WebGPU
and Cerebras WSE with one source-identity chain.

### Scope

- Primary hardware target for the first dense full-prompt HostPlan receipt.
- Dense model path, not the later Gemma 4 26B/A4B MoE efficiency lane.
- Hardware acceptance requires token/logit/KV transcript evidence bound to the
  same Doppler reference export, manifest, execution graph, weights, and input
  set.
- Full-graph compile inventory is not token-output inference evidence unless
  the inventory includes the post-layer logits path and sample consumes a typed
  logits producer.

### Current artifact fronts

- Full-graph compile attempt: `bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`
- Frozen Doppler TSIR boundary fixture: `bench/fixtures/r3-1-31b-doppler-frozen/`
- Frozen-reference validator: `bench/tools/validate_frozen_doppler_reference.py`
- Final-norm plus selected-logit splice:
  `bench/tools/run_gemma4_31b_af16_doppler_selected_logit_splice.py`
- Real-weight pin + smoke-contract audit:
  `bench/out/r3-1-31b-real-weight-smoke-extraction/{receipt,audit}.json`
- Bounded multi-token decode chain:
  `bench/out/r3-1-31b-multi-token-decode/receipt.json`

### Acceptance bar

Load-bearing for the correctness claim:

- For one prompt, prefill and generated-token IDs match the frozen Doppler
  reference at the scoped validation depth.
- Per-step logits artifacts compare under the declared Doppler tolerance policy.
- Manifest / HostPlan / CSL / reference-fixture hash chain is unbroken
  end-to-end.
- Returned hardware receipt either records the successful transcript or names a
  fail-closed hardware blocker and the last phase reached.

Regression net, parallel and not a prerequisite:

- Per-kernel manifest-shape dispatch receipts on simfabric or WSE.
- Byte/digest stability for changed kernel families.
- Cross-backend bootstrap canary receipts.

Per-kernel manifest-shape dispatch catches kernel-in-isolation pathologies
such as compiler rejection, fabric fit, dispatch timeout taxonomy, and
byte/digest instability. The end-to-end receipt catches composition,
phase-order, lm-head routing, graph completeness, and inter-kernel handoff
bugs. Neither side subsumes the other.

### Active fail-closed queue

These items gate any claim that Gemma 4 31B af16 runs real prefill/decode on
the Cerebras simulator or hardware:

1. Manifest-driven lm-head resolver must reject Q4K lm-head selection unless an
   explicit `lm_head.weight` exists, and accept tied dense F16/BF16/F32 only
   through `embed_tokens.weight`.
2. Tied dense lm-head must route through the full-vocabulary `lm_head_prefill`
   SUMMA target with one-row logits tiles and F16-to-F32 weight staging.
3. The Gemma 4 31B execution-v1 smoke graph must carry explicit final-norm /
   lm-head / sample tails for both prefill-generated and decode-generated
   tokens.
4. HostPlan lowering must reject `sample` unless the immediately preceding
   same-phase step is a compatible logits producer.
5. Real session runtime must stage real weights, bind host I/O layout, launch
   kernels, carry scheduler state, and produce generated-token/logit/KV
   transcript evidence.
6. Bounded-smoke and f16 dtype contracts must stay gate-covered until a complete
   `realSessionRuntime.status=output_ready` transcript supersedes the narrower
   per-kernel evidence.

## Qwen 3.6 27B hybrid

One Doppler-authored Qwen 3.6 27B model program, verifiable on browser WebGPU
and Cerebras WSE with the same source-identity chain discipline as Gemma.

### Scope

- Companion hardware lane after Gemma 4 31B.
- Hybrid full-attention + gated-DeltaNet SSM architecture.
- Uses model-specific dimensions, layer-body differences, and Qwen-only ops
  in HostPlan/runtime params while sharing Q4K -> f16 prefill GEMV patterning
  and receipt semantics with Gemma.
- WSE receipt remains hardware-gated.

### Current artifact fronts

- Smoke-config and architecture declaration:
  `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`
- Compile-target inventory:
  `bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`
- Per-kernel cells: `bench/runners/csl-runners/qwen-3-6-27b-cells/`
- Frozen Doppler reference validator:
  `bench/tools/validate_qwen_3_6_27b_frozen_doppler_reference.py`
- Final-norm plus selected-logit splice:
  `bench/tools/run_qwen_3_6_27b_af16_doppler_selected_logit_splice.py`
- Full-prompt hardware path:
  `bench/tools/run_qwen3_6_27b_af16_hardware_path.sh`
- Local simfabric ceiling probe:
  `bench/tools/run_qwen3_6_27b_af16_local_simfabric_ceiling.py`

### Acceptance bar

- Manifest compile targets are cslc-clean in the receipt.
- Per-kernel simfabric cells continue to carry bytes/digests for the
  non-hardware execution surface.
- For one prompt on the full hybrid architecture, the scoped attention and SSM
  boundary probes hash-match the Doppler reference.
- Manifest / HostPlan / CSL / reference-fixture hash chain is unbroken
  end-to-end.

### Active gates

- Full-prompt HostPlan hardware receipt from
  `run_qwen3_6_27b_af16_hardware_path.sh`.
- Manifest-shape hardware parity receipt for the hybrid prompt path on WSE,
  bound to the Doppler reference fixture.
- Speed measurement is a separate post-parity receipt and is not implied by
  correctness evidence.

## Shared integrity invariants

- Every receipt cites the same manifest hash; mismatches are emit-time errors.
- Compile artifacts are reused only by content hash, never filename.
- Shape substitution is a separate receipt class.
- Reference fixtures are frozen; regeneration is a digest-changing event.
- Every kernel dispatches at manifest shape before any parity claim.
- Per-class CSL kernel bytes must be model-depth invariant before a shallow run
  can stand in for a deeper parity claim.
- Materialized compile roots under
  `bench/out/*manifest-fullgraph-compile-steps/` must be regenerated after
  emitter changes before byte-identity or dispatch evidence is restated.
- Graph-to-HostPlan inventory equality is required for inference claims;
  dropping a source graph target must produce a typed unsupported result.
- `sample` is never valid as token-output evidence without a typed logits input
  from the compatible lm-head launch.

## Post-hardware optimization roadmap

Correctness-first lowering is the rule until the first returned hardware
receipt. After that receipt:

1. Extend mixed precision to still-f32 wide paths: KV cache, attention
   Q/K/V/O buffers, residual stream, RMSNorm storage, and SUMMA tiled matmul
   output.
2. Extend fused-dequant SUMMA tiled matmul, or add a Q4K -> f16 pre-pass kernel
   that materializes tiles in PE SRAM.
3. Port cross-kernel fusion into CSL emit: RMSNorm+matmul, matmul+residual,
   and gate+up+activation families behind capability flags.

## Long-tail

- TSIR-as-source-of-truth migrations: live status in [`status/tsir.md`](status/tsir.md).
- E2B control-lane diagnostics: evidence bundle and status shards carry the
  current artifact map.
- Performance baselines: require hardware receipt plus separate performance
  receipt and claim-policy review.
- Doppler-on-Doe Metal parity, second Doe model lanes, and operator-diff tools:
  track in the relevant status shard.
