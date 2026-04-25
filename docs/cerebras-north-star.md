# Doe Cerebras North Star checklist

This is the single Doe-local engineering checklist for the Doppler -> Doe ->
Cerebras path.

The North Star is one Doppler-authored model program, verifiable on browser
WebGPU and Cerebras WSE with one source-identity chain. The proof order is:
portability via TSIR, execution via CSL simfabric, scale via Gemma 4 31B, and
performance via like-for-like baselines.

This checklist supersedes the retired engineering checklist set removed during
the consolidation. Evidence-bundle governance docs remain separate because the
bundle packer and verifier include them directly.

## Queue

Top of queue: R2-2 -> R2-3 -> R2-4. Everything from R2-5 onward in the R2
section depends on clearing R2-1. R3 and R4 chain off R2-9 / R2-10. R1, P, and
H rows are parallelizable, but execution proof is the credibility path.

## What's left

### NS-0 - North Star

- Area: North Star.
- Status: Defined.
- Work left: Keep one Doppler-authored model program verifiable on browser
  WebGPU and Cerebras WSE with one source-identity chain. The proof chain is
  portability via TSIR (R1), execution via CSL simfabric (R2), scale via Gemma 4
  31B (R3), and performance via like-for-like baselines (R4).
- Done when: All four proof-chain receipts exist and link back to the same
  bundle hash.

### R2-1 - 3 1B simfabric blocker

- Area: 3 1B simfabric blocker.
- Status: Active blocker.
- Work left: Diagnose tiled launch `launchIndex=2` SUMMA `memcpy_d2h`
  `symbol=c` stall for 1,411,344 elements after `embed[0]` and
  `rmsnorm_prefill[1]` pass. Current evidence narrows the failure: `sim.log`
  reports idleness with the 54x54 SUMMA grid out of work, while `cs_python`
  stderr reports only the Doe 600 second command timeout. The kernel appears to
  have completed compute; host D2H hangs.
- Done when: `progress.jsonl` for `launchIndex=2` ends with
  `hostplan_launch_complete status=succeeded`, and `launchIndex=3` starts.

### R2-2 - Timeout probe

- Area: Timeout probe.
- Status: Next.
- Work left: Raise `MIN_REAL_INT4PLE_RUNTIME_TIMEOUT_MS` from 600 seconds to
  1800 seconds in `bench/tools/run_doe_csl_int4ple_transcript.py`, then rerun
  the standard regen and sim. This is the cheapest probe for whether D2H is
  just slow on simfabric for a 1.4M element f32 output.
- Done when: Tiled launch 2 either completes, proving a bandwidth-bound
  simfabric cost, or still hangs past 1800 seconds and advances to R2-3.

### R2-3 - SUMMA fence audit

- Area: SUMMA fence audit.
- Status: Conditional on R2-2 hang.
- Work left: Audit `runtime/zig/src/doe_wgsl/emit_csl_matmul.zig` for the
  SUMMA exit path on the C-tile sink PE. Check `unblock_cmd_stream` placement
  and fence ordering across row broadcast, column broadcast, and output-tile
  write phases. The sink PE may need a different unblock signal than non-sink
  PEs.
- Done when: The sink PE emits `unblock_cmd_stream` at the right semantic
  point and host D2H returns, or the audit shows the kernel side is correct and
  the issue is below Doe code.

### R2-4 - SDK 2.10 D2H repro

- Area: SDK 2.10 D2H repro.
- Status: Conditional on R2-3 clean.
- Work left: Build a minimal SUMMA D2H repro at small dimensions, such as
  `P=4`, `Mt=8`, `Kt=8`, `Nt=8`, and characterize whether the hang reproduces.
- Done when: Either the repro hangs and can be filed upstream with Cerebras, or
  it does not and the mitigation direction becomes scale-dependent chunked D2H
  or bounded residency.

### R2-5 - Remaining 3 1B launch triage

- Area: Remaining 3 1B launch triage.
- Status: Pending R2-1 unblock.
- Work left: Continue staging triage as launches reach rope, `attn_head256`,
  `gemv`, `lm_head_gemv`, sample, `kv_write`, `kv_read`, `attn_decode`, and
  `fused_ffn`. Grep `progress.jsonl` for `target_missing`,
  `phase_variant_target_missing`, `input_buffer_size_mismatch`, and runtime
  hangs on `memcpy_d2h`. Decode-phase elementwise staging is mitigated by the
  current phase-aware compile targets plus Python target remap; older
  `_compile_elementwise_decode_override` notes are historical.
- Done when: Every prefill and decode launch in the 3 1B HostPlan emits
  `hostplan_launch_complete status=succeeded`, with no failure-class events in
  the latest `progress.jsonl`.

### R2-6 - 3 1B CSL transcript

- Area: 3 1B CSL transcript.
- Status: Pending R2-5.
- Work left: Complete full prefill plus 8 decode steps and emit the bounded CSL
  transcript under the Gemma 3 1B hostplan bundle.
- Done when: The transcript has non-pending tokenized prompt hash, generated
  token IDs with length 8, 8 per-step logits hashes, KV state hash, and stop
  reason.

### R2-7 - 3 1B parity bind

- Area: 3 1B parity bind.
- Status: Pending R2-6.
- Work left: Bind the CSL transcript to the bundle-derived Doppler reference
  under `bench/out/doppler-reference/gemma-3-1b-doe-webgpu-export-bundle-derived/`.
- Done when: The parity receipt reports `outputParityPassed=true`,
  `tokenIdsMatch=true`, `perStepLogitsParityPassed=true`,
  `realKvCacheUsed=true`, `fullModelDepthExecuted=true`, and
  `stubStagesAbsent=true`.

### R2-8 - WebGPU reference exporter gaps

- Area: WebGPU reference exporter gaps.
- Status: Audit in parallel.
- Work left: Re-check WGSL-to-SPIR-V failure, missing per-layer weights,
  missing full prefill logits, and duplicate transcript disagreement. Some may
  already be resolved by newer BF16 broadcast and SPIR-V fixes, so audit before
  scoping new work.
- Done when: Each issue has a closed/open verdict, every open issue has a typed
  remediation ticket, and the reference transcript is authoritative and
  complete.

### R2-9 - E2B simfabric promotion

- Area: E2B simfabric promotion.
- Status: Pending 3 1B de-risk.
- Work left: Promote Gemma 4 E2B from one-layer SdkLayout smoke to full-depth
  CSL simfabric. Reuse the 3 1B HostPlan-generation path and expect another
  round of per-kernel staging triage at the larger scale.
- Done when: E2B has the same parity receipt assertions as R2-7.

### R2-10 - Cerebras hardware receipt

- Area: Cerebras hardware receipt.
- Status: Deferred.
- Work left: Run the same bundle through direct `DOE_CSL_CMADDR` or WSC
  appliance once simulator parity is green.
- Done when: A governed Cerebras hardware receipt exists under
  `bench/out/doppler-reference/` with successful execution and the same
  parity-asserted fields as R2-7.

### R3-1 - 31B evidence shape

- Area: 31B evidence shape.
- Status: Pending R2.
- Work left: Give Gemma 4 31B the same receipt and evidence shape as E2B:
  HostPlan generation, weight mapping, host I/O layout, send/receive telemetry,
  and runtime stop reason.
- Done when: The 31B simulator receipt has parity, host I/O layout,
  send/receive telemetry, and runtime-stop fields populated.

### R3-2 - 31B residency and streaming mechanics

- Area: 31B residency and streaming mechanics.
- Status: Pending R2.
- Work left: Land dense streaming machinery: layer residency, KV spill or
  partitioning, compile-artifact reuse, async send/receive, and demux/mux.
  Bounded-residency redesigns for embed, `lm_head_gemv_stable`,
  `attn_head256`, and `attn_head512` are likely needed at 31B scale even though
  the smaller 3 1B manifest scale currently compiles.
- Done when: The 31B dense simulator path runs end-to-end with bounded per-PE
  residency and no per-PE memory exhaustion in compile or driver logs.

### R3-3 - 31B hardware receipt

- Area: 31B hardware receipt.
- Status: Pending R3-1 and R3-2.
- Work left: Run governed hardware receipt for 31B on direct `cmaddr` or WSC
  appliance.
- Done when: A 31B WSE receipt exists with successful execution and parity
  fields all true.

### R4-1 - Performance baselines

- Area: Performance baselines.
- Status: Far out.
- Work left: Compare against Google A3, A3 Ultra, A4, and TPU v5e/v6e/v7 with
  identical workloads, prompts, decode budgets, and tokenization. Follow the
  strict apples-to-apples methodology in this repo's benchmark contracts.
- Done when: TTFT, prefill tokens/s, decode tokens/s, batch throughput,
  cost/token, and joules/token are published with receipts that link to the
  bundle identity chain.

### R1-1 - TSIR as source of truth

- Area: TSIR as source of truth.
- Status: Long-tail.
- Work left: Finish executable backend emitter bodies, parity harness, family
  receipts, live `integrityExtensions.lowerings[]`, and INT4 PLE operation TSIR
  coverage. The remaining live-kernel tally is branch-sensitive; record the
  exact migration count in `docs/status/tsir.md` before making a claim.
- Done when: Every kernel in the live HostPlan is sourced from a TSIR semantic
  function through `tsir.emit_kernel_body`, and no hand-maintained CSL bodies
  remain for the live path.

### R1-2 - Remaining hand-maintained kernels

- Area: Remaining hand-maintained kernels.
- Status: Long-tail.
- Work left: Migrate tiled matmul, `attn_head256`, `attn_decode`, `gemv`,
  `lm_head_gemv`, rope, `fused_ffn`, sample, and embed/gather into TSIR-backed
  emission. Follow the current wrapper recipe: extract live names, build a TSIR
  semantic function, and delegate through the configured kernel-body emitter.
- Done when: All listed kernels emit via TSIR and the corresponding handwritten
  live-path CSL body emitters are deleted.

### R1-3 - Structured HostPlan metadata

- Area: Structured HostPlan metadata.
- Status: Mostly done.
- Work left: Keep `pe_program.metadata.json`, `layout.metadata.json`, and
  `compile/targets.metadata.json` as the primary path. Regex parsers stay only
  as backstops for legacy artifacts that predate the metadata sidecars. Plan
  deletion after fixtures and `bench/out` artifacts are regenerated against the
  post-metadata host-plan tool.
- Done when: The active HostPlan executor has zero dependency on CSL text regex
  parsing and metadata sidecars are required, not optional.

### R1-4 - Three-tier evidence gate

- Area: Three-tier evidence gate.
- Status: Partly done.
- Work left: Keep pipeline-executed, simulator-success, and numeric-parity
  tiers separate. Wire reference comparison so per-step logits and KV state
  from the CSL transcript are compared against the Doppler reference and
  `numericParity.status` is populated.
- Done when: The simulator evidence gate reports a non-unknown
  `numericParity.status` for every R2-6 transcript run and the promotion path
  is documented.

### R1-5 - Stale reduction pattern test

- Area: Stale reduction pattern test.
- Status: Housekeeping.
- Work left: Update or delete the old reduction-pattern WGSL test that still
  asserts the pre-semantic-emitter RMSNorm lowering shape. The current semantic
  RMSNorm path uses the Gemma offset contract and no longer matches that old
  fixture.
- Done when: `zig build test-wgsl` exits 0 with no failure for the reduction
  pattern RMSNorm test.

### P-1 - Doppler-on-Doe Metal parity

- Area: Doppler-on-Doe Metal parity.
- Status: Product/debug.
- Work left: Run the reference model through Doe-Metal and compare output to
  Doppler's Dawn execution.
- Done when: The reference model produces tokens with task-level agreement
  under Doe-Metal vs Doppler/Dawn.

### P-2 - Second Doe model

- Area: Second Doe model.
- Status: Product/debug.
- Work left: Add a second model beyond the current Gemma path to avoid
  overfitting the proof chain to one graph shape.
- Done when: A second model has portability and execution receipts at minimum.

### P-3 - Operator diff and doe-gpu diagnose

- Area: Operator diff and `doe-gpu diagnose`.
- Status: Product/debug.
- Work left: Finish JS/native semantic handoff, capture extraction, Doe-side
  first-divergence integration, repro bundles, and packaging.
- Done when: `doe-gpu diagnose <model> <device>` produces a first-divergence
  report and runnable repro bundle on real model/device pairs.

### H-1 - Python sharding

- Area: Python sharding.
- Status: Housekeeping.
- Work left: Split donor files: `int4ple_compile_target_sim_runner.py`,
  `run_doe_csl_int4ple_transcript.py`, and
  `int4ple_hostplan_execution_plan.py`. Planned seams are simulator
  orchestration, runtime materialization, receipt assembly, and transcript
  binding.
- Done when: All three donor files stay under the 1200-line benchmark/tooling
  cap and focused tests remain green.

### H-2 - Status shard splits

- Area: Status shard splits.
- Status: Housekeeping.
- Work left: Keep `docs/status/cerebras-csl.md` split as new cycles land. The
  live shard is near the 1200-line cap in this checkout; split before adding
  more simulator-loop history.
- Done when: Live shards stay under the cap and archive history remains
  addressable from the live shard.

### H-3 - Doppler reference regen

- Area: Doppler reference regen.
- Status: Ongoing.
- Work left: Regenerate the bundle-derived reference whenever the bundle's
  identity chain changes: model program bundle, manifest, weight set, or
  tokenized prompt.
- Done when: The R2-7 parity bind always uses a reference whose bundle identity
  matches the current bundle.
