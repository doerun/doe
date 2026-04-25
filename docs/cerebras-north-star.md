# Doe Cerebras North Star checklist

This is the single Doe-local engineering checklist for the Doppler -> Doe ->
Cerebras path.

The North Star is one Doppler-authored model program, verifiable on browser
WebGPU and Cerebras WSE with one source-identity chain. The product target is
Gemma 4 31B dense on Cerebras hardware. Smaller E2B / 3 1B lanes remain
control fixtures for debugging, regression isolation, and bounded simfabric
checks; they are no longer the required proof order before the 31B hardware
ask.

This checklist supersedes the retired engineering checklist set removed during
the consolidation. Evidence-bundle governance docs remain separate because the
bundle packer and verifier include them directly.

## Queue

Immediate action: R3-1 (31B L1 smoke hardware receipt, time-boxed). Conditional
follow-up: R3-1 L61 chain if L1 returns clean. Roadmap thereafter: R3-2
streaming mechanics, R3-3 full hardware parity receipt. R2 remains the
control/debug lane, not the load-bearing proof sequence. R1 TSIR and metadata
work can proceed in parallel. The credibility path is a 31B dense hardware
receipt backed by explicit bundle identity, compile evidence, streaming
residency evidence, and parity or typed blockers — but only step 1 is "next";
steps 2-5 are sequenced behind it, not all simultaneously active.

## 31B-first execution plan

This section orders 31B work into three buckets. The narrative reorder
(31B-primary, E2B-control) does not weaken existing E2B evidence — E2B
real-weight smoke and manifest-shape evidence remain valid claims; they just
stop being the prerequisite story for the 31B hardware ask. CLAIM_SCOPE
content for E2B may be reordered but should not be demoted in substance.

### Immediate action (time-boxed)

1. **31B L1 smoke hardware receipt.** Run
   `bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py` with
   `--num-layers 1`, small `--size`, and direct `--cmaddr` or WSC. This proves
   the 31B dense runner, SDK environment, source hashes, and hardware receipt
   path before deeper streaming work. Materially improves the bundle (not just
   taxonomy) once the receipt exists.

### Conditional follow-up (gated on step 1)

2. **31B L61 smoke-shape chain.** Run the same runner with
   `--num-layers 61` at smoke shape. This is not manifest-shape 31B, but it
   proves the dense full-layer-count control flow and residual stream shape. On
   local simfabric, it is cheap enough to kick while the hardware ask is being
   prepared; on hardware, attempt after step 1 returns clean.

### Roadmap (sequenced, not concurrently active)

3. **31B real-weight smoke-shape.** Materialize
   `bench/out/gemma-4-31b-real-weights/` under the contract in
   `config/gemma-4-31b-real-weight-fixture.json`, then rerun L1/L2/L4/L8/L61
   receipts with `--weights-dir`. This is the first numerical 31B scale proof,
   still labeled `real_weight_smoke_shape`.
4. **31B manifest-shape streaming.** Land the `headDim=160`, hidden-dim 5120,
   streaming-residency, async send/receive, KV policy, and compile-artifact
   reuse mechanics. This is the point where 31B becomes a manifest-shape
   execution target rather than a smoke-shape dense runner.
5. **31B hardware parity receipt.** Bind the hardware transcript against the
   deterministic reference export with matching manifest, graph, weights,
   prompt/input, token/logit/KV artifacts, and explicit `hardware_success` or
   typed blocker taxonomy.

### Overnight local evidence plan

This plan is for stronger local smoke-shape evidence on the current 64-core /
128GB unified-memory host. It should not be described as production-grid 31B
prefill/decode evidence. The production-grid path remains hardware-only.

**Phase 0 — now, parallel, <=10 minutes**

- Land/verify the SDK invocation wrapper so SdkLayout calls use the singularity
  path when the SDK direct-rootfs path cannot resolve `/cb` / microcode sources.
- Kick `gemma_4_31b_layer_block_smoke.py --num-layers 61 --size 1024` as the
  cheapest full-layer-count 31B smoke probe. If it works, the receipt proves
  31B dense layer-block chaining at smoke shape today.

**Phase 1 — next 1-3 hours, code work**

- Add a 31B prefill/decode smoke runner as a sibling to the layer-block smoke
  runner, rather than overloading the existing layer-block receipt. Required
  fields:
  - decode loop after prefill/layer-block chain
  - KV state initialization/update/readback across decode steps
  - greedy sample step
  - stop-reason emission
  - per-step logits digests
  - generated token-id sequence
- Open questions to resolve before implementation:
  - the current 31B smoke runner stops at residual-stream output, not
    logits-shaped output
  - an lm-head/logits stage must be wired or stubbed as explicitly unsupported
  - KV write/read may need new smoke kernels or a reduced smoke contract; do
    not silently claim KV coverage until receipts include real KV state

**Phase 2 — overnight matrix, bounded concurrency**

- Run an evidence matrix only after one L61 and one decode-smoke cell establish
  per-process RSS, CPU use, and wall time. Candidate axes:
  - `--num-layers`: 1, 8, 26, 61
  - `decode_steps`: 0, 1, 4, 8
  - `weights`: synthetic always; real only if
    `bench/out/gemma-4-31b-real-weights/` exists and validates
  - `--size`: 1024, 2048
- Concurrency policy:
  - one memory-heavy WebGPU/reference job at a time
  - start CSL/simfabric at 4-8 concurrent cells, then raise only if measured
    RSS and CPU leave headroom
  - do not run 32-48 simfabric cells by default; use that only after
    measurement shows each cell is genuinely small and not I/O/SDK bound
  - keep all cells independent and write per-cell logs, receipts, and failure
    taxonomies; one failed cell must not cancel the matrix

**Claim scope**

The output of this plan is "31B kernel composition plus smoke decode mechanics
work end-to-end on bounded simfabric inputs." It is not "31B production-grid
prefill/decode works on simfabric." Receipt `CLAIM_SCOPE` must say that
explicitly. The kernel keys exercised may overlap the production path, but the
per-PE residency and grid scale do not.

### E2B control-lane policy

E2B remains useful as the smaller control lane for reproducing failures and
checking that bundle tooling still works. It should not block the 31B hardware
ask unless a failure is clearly shared by both models. Existing E2B claims
(real-weight smoke, manifest-shape evidence, attention-core diagnostic) stay
valid and should remain in CLAIM_SCOPE — the demotion is in narrative
ordering, not in claim substance.

## What's left

### NS-0 - North Star

- Area: North Star.
- Status: Defined.
- Work left: Keep one Doppler-authored model program verifiable on browser
  WebGPU and Cerebras WSE with one source-identity chain. The proof chain is
  portability via TSIR (R1), 31B dense hardware execution (R3), bounded
  simfabric/control diagnostics (R2), and performance via like-for-like
  baselines (R4).
- Done when: All four proof-chain receipts exist and link back to the same
  bundle hash.

### R2-1 - 3 1B simfabric blocker

- Area: 3 1B simfabric blocker.
- Status: Control-lane diagnostic; root cause identified.
- Work left: The R2-4 sweep against canonical `csl-extras gemm-collectives_2d`
  proved simfabric scales ~O(P^3) for SUMMA d2h: P=4 (4 s) → P=8 (15 s) →
  P=16 (92 s) → P=32 (948 s) → P=54 extrapolates to ~110 min per launch. The
  earlier "kernel completed compute, host D2H hangs" framing was wrong; both
  compute and d2h are gated on simfabric throughput, and the d2h call is the
  observable symptom rather than the root cause. Doe code matches canonical
  structurally (R2-3); no Doe-side fix exists. Mitigation = hardware path
  (R2-10 / R3-x). This stays useful for bounded simfabric diagnostics at
  P≤16 and SDK issue isolation, but does not block the 31B hardware evidence
  path.
- Done when: Documented above; the issue is no longer load-bearing for any
  promotion gate.

### R2-2 - Timeout probe

- Area: Timeout probe.
- Status: Closed.
- Work left: None. The probe ran with the 1800 s bump and surfaced a third
  outcome the original done-when criterion did not admit: the launch neither
  completes nor deadlocks within budget; it would complete given hours rather
  than seconds. The R2-4 sweep then confirmed simfabric scales ~O(P^3) for
  SUMMA d2h, so 1800 s was insufficient for P=54 (~110 min extrapolated) but
  sufficient for P≤16. The probe answered the question.
- Done when: Closed by R2-4 sweep finding (`bench/runners/r2_4_summa_sweep.py`,
  6-cell sweep, 2026-04-25).

### R2-3 - SUMMA fence audit

- Area: SUMMA fence audit.
- Status: Closed.
- Work left: None. Audit complete: diff against canonical
  `csl-extras-202604101435-6/examples/benchmarks/gemm-collectives_2d/pe.csl`
  showed Doe matches structurally, including `unblock_cmd_stream` placement on
  the exit task. No fence primitive exists in the canonical SUMMA pattern
  either. The sink PE does NOT need a different unblock signal; the issue is
  below Doe code (simfabric throughput, R2-1 / R2-4).
- Done when: Closed (audit performed, kernel side verified correct).

### R2-4 - SDK 2.10 D2H repro

- Area: SDK 2.10 D2H repro.
- Status: Closed.
- Work left: Sweep complete (`bench/runners/r2_4_summa_sweep.py`, 6-cell
  P×Mt grid against canonical sources). Findings:
  - Trigger axis: PE-count P (per-PE bytes scale linearly when P held).
  - Scaling: ~O(P^3) per doubling (P=8→16: 6.1×; P=16→32: 10.3×).
  - Not a deadlock: P=32 succeeds at 15.8 min when given 20-min timeout.
  - Doe-exact (P=54) extrapolates to ~110 min per launch; full transcript
    (~183 launches) is non-viable on simfabric regardless.
  - Mitigation: hardware path (R2-10 / R3-x). Optional: file an SDK perf
    report with Cerebras (it is not a Doe defect).
- Done when: Closed (2026-04-25 sweep). Optional SDK upstream report remains
  follow-up; not gating.

### R2-5 - Remaining 3 1B launch triage

- Area: Remaining 3 1B launch triage.
- Status: Control-lane diagnostic.
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

### R2-5a - Local simulator evidence acceleration

- Area: Local simulator evidence acceleration.
- Status: Planned control-lane accelerator; not on the 31B hardware critical
  path.
- Work left: Improve local simfabric iteration throughput without pretending it
  solves full-grid transcript cost:
  1. Add durable HostPlan checkpoints keyed by bundle hash, manifest hash,
     graph/hostplan hash, compile-target hashes, launch identity, symbol shape,
     byte count, and sha256.
  2. Add `--checkpoint-dir`, `--resume-from-checkpoint`, and
     `--stop-after-launch` to the HostPlan transcript runner so late-launch
     triage can resume from the last validated D2H outputs instead of replaying
     the whole prefix.
  3. Measure one representative sim run with `/usr/bin/time -v`, `pidstat`,
     and, when available, `perf stat` before tuning CPU affinity or thread
     controls.
  4. Keep compile-artifact cache reuse keyed by source/params/target hash, then
     add process-pool execution only for independent sweeps.
  5. Treat CPU affinity, SDK env knobs, and process counts as measured tuning,
     not default policy.
- Done when: A failed late HostPlan launch can be reproduced from a verified
  checkpoint manifest, the runner refuses stale checkpoints with explicit
  identity mismatch errors, and bounded sweeps can opt into process-pool
  execution without changing receipt semantics.

### R2-6 - 3 1B CSL transcript

- Area: 3 1B CSL transcript.
- Status: Control-lane diagnostic. Not load-bearing for the 31B hardware ask;
  R2-7 parity bind is execution-target-agnostic and can consume hardware or
  bounded-subset evidence instead.
- Work left: Complete full prefill plus 8 decode steps and emit the bounded CSL
  transcript under the Gemma 3 1B hostplan bundle.
- Done when: The transcript has non-pending tokenized prompt hash, generated
  token IDs with length 8, 8 per-step logits hashes, KV state hash, and stop
  reason.

### R2-7 - 3 1B parity bind

- Area: 3 1B parity bind.
- Status: Control-lane diagnostic. Execution-target-agnostic — the Doe-CSL
  transcript can come from simfabric (when feasible at bounded subset),
  hardware, or a future host-side functional interpreter, as long as the
  bundle identity chain matches.
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

### R2-9 - E2B control promotion

- Area: E2B control promotion.
- Status: Control lane.
- Work left: Promote Gemma 4 E2B from one-layer SdkLayout smoke to full-depth
  CSL/simfabric or hardware control receipt when it helps reproduce failures at
  smaller scale. Do not make this a prerequisite for 31B hardware access.
- Done when: E2B can reproduce or exclude 31B-adjacent failures with a smaller
  receipt, and its evidence is labeled as a control fixture rather than the
  product target.

### R2-10 - Cerebras-assisted bundle path

- Area: Cerebras-assisted bundle path.
- Status: Active external path.
- Work left: Circulate the evidence bundle or request direct endpoint access.
  The bundle path is not blocked by full-grid simfabric parity: Cerebras can run
  the pinned bundle internally and return a hardware receipt, or provide
  `DOE_CSL_CMADDR` / WSC access so Doe runs the governed runner. The
  singularity-wrapper fix landed 2026-04-25
  (`runtime/zig/tools/cs_python_singularity.sh` plus
  `runtime/zig/tools/csl_sdk_driver.py` discovery patch and per-tool
  `select_cs_python` updates) flips the paint-flow Cluster A bundle gates
  from FAIL to PASS — verified for
  `gemma4-e2b-manifest-shape-attention-core`. Cluster B (stale fixture)
  gates still need `gemma-3-1b-doe-csl-hostplan/{host-plan,doppler-program-bundle}.json`
  regen before a clean-tree bundle gate hits 31/31.
- Done when: A returned receipt binds manifest, graph, weights, prompt/input,
  compile artifacts, execution target, and either `hardware_success` or a typed
  hardware/runtime blocker.

### R3-1 - 31B evidence shape

- Area: 31B evidence shape.
- Status: Primary path; immediate-action item (L1 smoke, time-boxed).
- Work left: Give Gemma 4 31B the primary evidence shape: L1 smoke hardware
  receipt (immediate, time-boxed), L61 smoke-shape chain receipt (conditional
  on L1 clean), real-weight smoke-shape receipt when weights are available,
  host I/O layout, send/receive telemetry, runtime stop reason, and explicit
  claim scope. E2B mirrors this as a control lane (substance preserved, not
  demoted). The 31B smoke runner has byte-equivalent argparse parity with the
  E2B smoke runner (verified 2026-04-25), so tier-1 is operationally shippable
  today on the same terms — the gating dependency is hardware access, not
  runner readiness.
- Done when: 31B receipts exist for L1 and L61 smoke-shape hardware execution,
  with bundle identity and runtime-stop fields populated. Simfabric-side L1 and
  L61 smoke-shape receipts landed 2026-04-25
  (`bench/out/r3-1-31b-l1-dry/trace.json`,
  `bench/out/r3-1-31b-l61-smoke/trace.json`) with `passed=True`,
  `numLayersChained=1` and `61` respectively, max abs err 0 against per-layer
  reference. Hardware-side equivalents pending R2-10 / endpoint access.
- Source-side reference also landed 2026-04-25 (afternoon): Lane A1 produced
  the first 31B Doppler program bundle (`gemma-4-31b-program-bundle.json` +
  `reference.json` under
  `bench/out/overnight/<utc>/cells/wg-31b-doppler-reference-bundle/`), and
  Lane A2 ran the 31B Doppler/WebGPU prefill+8-decode reference end-to-end
  (~8 min wallclock, `stopReason=max-tokens`). These are the source-side
  receipts the R2-7 parity bind would consume; the Doe-CSL side is gated on
  the live blocker in the next bullet.
- Live blocker for KV-side evidence at 31B: the truncated CSL prefill+decode
  path (`run_doe_csl_int4ple_transcript.py --max-layers 1` against the new
  31B bundle) reaches `executor_bootstrap_complete` with all 162 launches
  resolved after the residual-symbol fix landed, but fails at embed
  `launch[0]` with `[Errno 2] No such file or directory:
  'not_captured_by_doppler_program_bundle'`. The string is a sentinel emitted
  at `bench/tools/run_doe_csl_int4ple_transcript.py:629` when
  `find_tokenized_prompt_artifact()` cannot locate a captured tokenized
  prompt in the program bundle; the HostPlan generator then propagates the
  sentinel as a real path. Fix direction: sentinel-aware HostPlan generator
  that skips the prompt-tokenize launch (or substitutes a synthetic-prompt
  path) when the bundle does not carry a captured artifact. Until that
  lands, slide 16's "structurally enabled but not yet executed" row for
  `kv_write` / `kv_read` stays unbacked.

### R3-2 - 31B residency and streaming mechanics

- Area: 31B residency and streaming mechanics.
- Status: Primary path.
- Work left: Land dense streaming machinery: layer residency, KV spill or
  partitioning, compile-artifact reuse, async send/receive, and demux/mux.
  Bounded-residency redesigns for embed, `lm_head_gemv_stable`,
  `attn_head256`, and `attn_head512` are likely needed at 31B scale even though
  the smaller control lanes compile.
- Done when: The 31B dense hardware path runs end-to-end with bounded per-PE
  residency and no per-PE memory exhaustion in compile or driver logs.

### R3-3 - 31B hardware receipt

- Area: 31B hardware receipt.
- Status: Primary path.
- Work left: Run governed hardware receipt for 31B on direct `cmaddr` or WSC
  appliance. Start with L1 smoke and L61 smoke-shape, then promote to
  real-weight smoke-shape and manifest-shape streaming after the corresponding
  mechanics land.
- Done when: A 31B WSE receipt exists with successful execution and parity
  fields all true for the claim tier being asserted.

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
- Status: Long-tail; incremental progress.
- Work left: Finish executable backend emitter bodies, parity harness, family
  receipts, live `integrityExtensions.lowerings[]`, and INT4 PLE operation TSIR
  coverage. The remaining live-kernel tally is branch-sensitive; record the
  exact migration count in `docs/status/tsir.md` before making a claim. As of
  2026-04-25 (`212a46868`), `tsir/reference_interpreter.zig` covers
  `residual_add` and `gelu_gated` in addition to the prior `fused_gemv`,
  `rms_norm`, `gather`, `identity`, and `simple_reduction` cases (7 of 11
  transcript bodyOps now have a host-side parity oracle). `kv_write` /
  `kv_read` deferred — read-write binding semantics need a convention pick
  for whether `inputs[]` extends to read-write slots or a separate
  `prior_state[]` parameter is added to `run()`. Real-pipeline-v0 fixture
  coverage extended same day to include `runtime/zig/tests/tsir/real/rmsnorm/`
  and `runtime/zig/tests/tsir/real/fused_gemv/` (promoted from bootstrap with
  `frontendVersion="frontend-real-pipeline-v0"`); manifest entries
  regenerated under `bench/fixtures/tsir-real-entries/` for both
  `webgpu-generic` and `wse3` backends. Six real-pipeline-v0 kernel
  fixtures total (rmsnorm, fused_gemv, embed, lm_head_gemv,
  attention_head256_f16kv, attention_head512_f16kv).
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
