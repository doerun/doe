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

## What's required for the Cerebras ask (three evidence layers)

CSL-related evidence in this repo lives at three distinct layers. Confusing
them is the most common source of "is the North Star done?" ambiguity. Only
Layers B and C gate the 31B hardware ask. Layer A is supporting bookkeeping.

| Layer | What it is | Shape | Required for North Star? | Live status |
| --- | --- | --- | --- | --- |
| **A. Real-canary CSL identity lane** | Per-kernel TSIR identity check: Doe-CSL output bytes match the Doppler / numpy reference for this kernel at this small input shape. | Smoke (single-PE, hidden=4, vocab=1, etc.) | **No.** Regression / identity bookkeeping. Closing it does not move the 31B hardware ask. | **24/24 `pass / pass / pass`** across 6 real kernels × 4 backends (fused_gemv, embed, lm_head_gemv, rms_norm via TSIR-CSL emit; attention_head256/512_f16kv via hand-authored bootstrap-shape CSL with zero-input → zero-output matching Doppler probes). Bootstrap canary at `bench/out/nightly-tsir-parity-canary-bootstrap-12/` reports **12/12 `pass / pass / pass`**. Promoted snapshot at `bench/out/r3-1-tsir-cross-backend/real-canary-with-transcripts/`. The TSIR-CSL emit body for `attention_scores` is now landed at `runtime/zig/src/tsir/emit_kernel_body_attention.zig` (two-pass-stable softmax) with the matching Zig oracle at `runtime/zig/src/tsir/reference_interpreter.zig:tryAttentionScores`; the canary still routes through hand-authored CSL at bootstrap shape until the 2 attention fixtures' `bodyOp` is wired to `attention_scores`. |
| **B. 31B manifest-shape full-graph compile** | Every kernel in the 31B model graph `cslc`-compiles under the WSE-3 per-PE memory budget. Prerequisite for any manifest-shape execution on simfabric or hardware. | Manifest (hidden_dim=5120, max_seq_len=4096, head_dim≈160) | **Yes.** Cannot attempt manifest-shape 31B on simfabric or hardware without all targets compiling. | **Closed at compile scope.** `bench/out/r3-1-31b-manifest-fullgraph-compile-steps/trace.json.driver-result.json` records every entry in `compile.targets` at `status: "succeeded"` — the four prior typed blockers (`csl_compile_pe_memory_exhausted` on `ple_rmsnorm`, `tiled`, `kv_write`, `kv_write_shared`) are resolved. Slot-sharded KV emit body at `runtime/zig/src/tsir/emit_kernel_body_kv.zig` is now active by manifest wiring; `runtime/zig/src/csl_host_plan_tool.zig` threads `pe_id` / `num_pes` / `slots_per_pe` for the KV path, shrinks the `tiled` per-PE block from 64 to 32, and stops propagating the `hidden_size` override into `ple_rmsnorm`. Synthesized receipt regeneration via `bench/tools/synthesize_full_graph_compile_attempt_receipt.py` against the new driver result is in flight elsewhere. |
| **C. 31B graph-shape execution receipt** | The 23 kernels chained as a graph produce tokens / logits / KV state end-to-end. Simfabric proves the orchestration; hardware proves the WSE. **This is the North Star.** | Manifest, on simfabric or WSE | **Yes.** This is the ask. | Bounded-shape decode chain runs end-to-end on simfabric: single-step at `bench/out/r3-1-31b-bounded-decode-integrated/`, multi-token via subprocess-isolated SdkRuntimes at `bench/out/r3-1-31b-multi-token-decode/receipt.json`. Manifest-shape execution NOT YET ATTEMPTED (gated by Layer B). 31B L1 smoke hardware receipt (R3-1) NOT YET RUN (gated by hardware access). |

### What we can show Cerebras today (no hardware)

- One Doppler-authored Gemma 4 31B model program with source-identity pinned
  across browser WebGPU and Cerebras WSE3 / MSL / SPIR-V backends
  (`bench/out/r3-1-tsir-bootstrap-four-backend-canary/`,
  `bench/out/r3-1-31b-doe-webgpu-parity/`).
- 31B manifest-shape compile **closed across all 23 graph kernels**: every
  entry in `compile.targets` reports `status: "succeeded"` at
  `bench/out/r3-1-31b-manifest-fullgraph-compile-steps/trace.json.driver-result.json`.
  The four prior `csl_compile_pe_memory_exhausted` targets (`ple_rmsnorm`,
  `tiled`, `kv_write`, `kv_write_shared`) are resolved via the slot-sharded
  KV emit body, the `tiled` per-PE block shrink (64 → 32), and dropping the
  `hidden_size` override forwarding into `ple_rmsnorm`. Synthesized receipt
  regeneration against the new driver result is in flight elsewhere.
- Bounded-shape multi-token decode chain executing end-to-end on simfabric
  (`bench/out/r3-1-31b-multi-token-decode/`).
- Real-weight extraction + audit against the canonical Gemma 4 31B weights
  (`bench/out/r3-1-31b-real-weight-smoke-extraction/`).
- Threshold-bracketed per-PE memory ceiling for the layer-block kernel
  (`bench/out/r3-1-31b-manifest-compile-sweep/`).

### What we need hardware for

In order:

1. **R3-1 — 31B L1 smoke hardware receipt** (`bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py --num-layers 1`).
   Proves the 31B dense runner, SDK environment, source-hash chain, and
   hardware receipt path before deeper work. Doesn't depend on Layer C.
2. **R3-3 — Manifest-shape hardware parity receipt**: execute the 23-kernel
   graph end-to-end on the WSE, bind the transcript to the deterministic
   reference export with matching manifest / graph / weights / prompt /
   token-logit-KV artifacts. This is the actual North Star evidence. Layer B
   is now closed at compile scope, so this step is gated only on Layer C
   (manifest-shape simfabric execution receipt) and on hardware access — not
   on residency redesigns.

### One-sentence pitch

We have a single Doppler-authored Gemma 4 31B model program with identity
pinned across all four backends, all 23 manifest-shape kernels now compiling
cleanly under the WSE-3 per-PE budget, and a bounded-shape multi-token decode
chain running end-to-end on simfabric — what we need hardware for is the L1
smoke receipt, then manifest-shape end-to-end execution; the only remaining
non-hardware work is the manifest-shape simfabric execution receipt
(see "Manifest-shape simfabric proof plan" below).

## Manifest-shape simfabric proof plan

The remaining non-hardware work is producing a Layer C manifest-shape simfabric
execution receipt — the 23-kernel graph executing end-to-end at manifest shape
on simfabric, bound to the manifest hash. Layer B is closed at compile scope;
this section is the rung ladder for closing Layer C without (a) running the
full graph blindly and timing out, or (b) producing receipts that look green
but cite mismatched identity.

The plan trades full-graph wall-clock for a stack of cheaper rungs that
isolate failure modes. Every rung produces a receipt with the manifest hash
spine; promotion to the next rung is gated on the prior rung's receipt
passing schema-enforced hash checks.

### Acceptance bar (Layer C)

A manifest-shape simfabric execution receipt is closed when:

- All 23 manifest-shape kernels have **dispatched** on simfabric (not merely
  compiled), with bytes-in / bytes-out and output buffer digests recorded.
- For one prompt, prefill plus the first decoded token's logits hash matches
  the frozen Doppler reference fixture (one of the WebGPU non-determinism
  branches, frozen — not regenerated).
- The receipt's manifest / HostPlan / CSL / reference-fixture hash chain is
  unbroken end-to-end.

Multi-token continuation, full-depth (48-layer) parity, and longer prompts are
*additional* receipt classes layered on top — they do not gate the bar above.

### Rung ladder

Each rung produces a receipt under `bench/out/r3-1-31b-manifest-simfabric-*`
with explicit `receiptClass`, manifest hash citation, and `referenceFixtureHash`
where applicable. Promotion is gated on schema enforcement (rung 1).

| # | Rung | Output | Gates |
| --- | --- | --- | --- |
| 0 | Per-target compile cache | content-addressed `.elf` reuse | infra only |
| 1 | Schema-enforced hash spine | receipt-emit guard rejects mismatched hashes | every receipt below |
| 2 | Predicted simfabric wall-clock | per-graph cycle/D2H budget JSON | rung 8 launch decision |
| 3 | Per-kernel manifest-shape dispatch | one receipt per kernel: bytes-in/out + exit code | rung 4 |
| 4 | Layout receipt | bytes-in/out + buffer digest, **no oracle compare** | rung 6 (separates plumbing from numerics) |
| 5 | Frozen Doppler reference fixture | hashed transcript + activation probes | every parity rung below |
| 6 | 1-of-48-layer first-token parity (`receiptClass: manifest_shape_1L_first_token`) | first-token logits hash vs frozen reference at L=1 | rung 7 |
| 7 | Single-block parity with intra-block probes | post-rmsnorm / post-QKV / post-attn / post-FFN hash check | rung 8 |
| 8 | Full 48-layer prefill + first-token (`receiptClass: manifest_shape_first_token`) | prefill + first-token logits hash | rung 9 |
| 9 | Multi-token continuation | N-token sequence vs frozen reference branch | done |

### Refinements (where each lands on disk)

1. **Per-target compile cache (rung 0).** `bench/tools/compile_cache_manager.py`,
   driven from the steps-mode driver. Cache key = sha256 of (HostPlan target
   hash + emitted CSL hash + `compileParams`). Reuses prior `.elf` when key
   matches; runs `cslc` only on miss. Hash-key inputs are the same ones
   `bench/tools/prepack_hash_drift_guard.py` already pins, so the cache cannot
   reuse a stale artifact across a real lowering change.

2. **Schema-enforced hash spine (rung 1).** `bench/tools/_receipt_hash_guard.py`
   imported by every Doe receipt writer. Guard rejects emit when:
   (a) cited manifest hash ≠ live manifest hash for the bundle path,
   (b) `hostPlanHash` does not chain back to the manifest,
   (c) `referenceFixtureHash` is missing for any receipt with
   `receiptClass.startswith("manifest_shape")` and `comparisonMode == "parity"`.
   Existing audit-time gates in `bench/tools/prepack_hash_drift_guard.py`
   remain; this guard is the upstream catch.

3. **Predicted simfabric wall-clock (rung 2).** `bench/tools/predict_simfabric_wallclock.py`.
   Inputs: `pe_program.metadata.json` per target plus the host plan. Per
   kernel, sum (estimated D2H bytes × throughput constant) +
   (residency cycles × call count). Output:
   `bench/out/r3-1-31b-manifest-simfabric-predicted-wallclock/budget.json`.
   The throughput constant is calibrated from a single rung-3 dispatch, not
   guessed. Rung 8 will not launch unless the budget is under a configured
   ceiling in `config/manifest-simfabric-budget.json`.

4. **Per-kernel manifest-shape dispatch (rung 3).** Extend
   `bench/runners/csl-runners/multi_token_decode_orchestrator.py` (or a new
   sibling `manifest_kernel_probe_runner.py`) to dispatch one kernel at
   manifest shape with manifest-shape inputs, against per-kernel Doppler
   probes from `bench/fixtures/tsir-real-doppler-transcripts/`. Receipt:
   `bench/out/r3-1-31b-manifest-simfabric-per-kernel/<kernel>.json`.

5. **Layout receipt (rung 4).** `bench/tools/run_manifest_shape_layout_receipt.py`.
   Per kernel, dispatch with manifest-shape inputs; record `inputBytes`,
   `outputBytes`, `outputDigest`, `dispatchExitCode`, `bufferAlignment`. No
   oracle compare. Failure here is plumbing (stride, layout, axis order),
   not numerics. Receipt:
   `bench/out/r3-1-31b-manifest-simfabric-layout-receipt/<kernel>.json`.

6. **Frozen Doppler reference fixture (rung 5).** `bench/fixtures/r3-1-31b-doppler-frozen/{transcript.json,activations/<layer>/<probe-point>.npy}`,
   indexed by `frozen-reference.manifest.json`. Probe points:
   `post_rmsnorm`, `post_qkv`, `post_attn`, `post_ffn` for layer L=1 (used by
   rungs 6 and 7) plus first-token logits (used by rungs 6, 8, 9). The
   fixture's digest is exported as `referenceFixtureHash` and consumed by
   the receipt-emit guard (refinement 2). Coordination note: the bundle's
   manifest needs a `referenceFixtureHash` field on the Doppler side; the
   Doe-side fixture and validator can land first.

7. **Intra-block probes (rung 7).** Add four probe-write hooks at the four
   TSIR boundary points already encoded in the per-block emit
   (`runtime/zig/src/tsir/emit_kernel_body.zig` plus the per-kernel emitters).
   Probes write `.npy` snapshots into the orchestrator's per-step scratch
   dir during dispatch; rung 7 hashes them and compares against the same
   four points in the frozen fixture (refinement 6). Same dispatch cost as a
   block-level parity run; localizes any mismatch to a single TSIR boundary.

8. **1-of-48-layer first-token rung (rung 6).** The host-plan tool already
   accepts `--num-layers`; verify in
   `runtime/zig/src/csl_host_plan_tool.zig` that 1-layer emission keeps the
   per-kernel artifacts identical to the 48-layer emission (kernel CSL is
   per-class, not per-layer-instance). Receipt class:
   `manifest_shape_1L_first_token` — explicitly *not* full-depth manifest
   parity, but a real manifest-shape first-token receipt.

### Integrity invariants (across all rungs)

- Every receipt names the same manifest hash; mismatches are emit-time errors,
  not audit findings.
- Compile artifacts are reused only by content hash, never by filename.
- Shape substitution (e.g., running `hidden_dim=1024` instead of `5120`) is a
  separate receipt class — never promoted to manifest-shape parity.
- The reference fixture is *frozen*: regeneration is a fixture-version event
  (new digest, new manifest field), not a silent refresh.
- Every kernel in the manifest graph dispatches at manifest shape at least
  once (rung 4) before any parity claim is made — canary coverage at
  bootstrap shape does not substitute.

### What this plan does not include

- Hardware execution receipts (R3-1, R3-3) — those remain hardware-gated.
- Performance claims — every rung is a correctness/identity receipt; timing
  data appears only as the predicted-wall-clock budget input, not as a
  performance claim.
- Real-weight numerical parity beyond the frozen reference branch — the
  WebGPU-non-determinism convention (frozen reference vs regenerated) is the
  only valid comparison mode here.

## Queue

Immediate action: R3-1 (31B L1 smoke hardware receipt, time-boxed). Conditional
follow-up: R3-1 L61 chain if L1 returns clean. Roadmap thereafter: R3-2
streaming mechanics, R3-3 full hardware parity receipt. R2 remains the
control/debug lane, not the load-bearing proof sequence. R1 TSIR and metadata
work can proceed in parallel. The credibility path is a 31B dense hardware
receipt backed by explicit bundle identity, compile evidence, streaming
residency evidence, and parity or typed blockers — but only step 1 is "next";
steps 2-5 are sequenced behind it, not all simultaneously active.

Parallel no-hardware work has produced a stack of bounded receipts that
strengthen the ask before hardware access, kept below the hardware-claim line.
The current bundle has a manifest-shape compile-attempt receipt and threshold
sweep (`bench/out/r3-1-31b-manifest-compile-attempt/`,
`bench/out/r3-1-31b-manifest-compile-sweep/`), plus a measured full-graph
compile attempt over the steps-mode targets
(`bench/out/r3-1-31b-manifest-fullgraph-compile-steps/trace.json.driver-result.json`,
`bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`). The full-graph
driver result now records every entry in `compile.targets` at
`status: "succeeded"`; synthesized receipt regeneration against the new
driver result is in flight elsewhere. It also has a
bounded KV/decode chain (`bench/out/r3-1-31b-bounded-decode-integrated/`) and a
multi-token decode chain that runs end-to-end on simfabric via
subprocess-isolated SdkRuntimes
(`bench/out/r3-1-31b-multi-token-decode/receipt.json`,
`bench/runners/csl-runners/multi_token_decode_orchestrator.py` driving
`bench/runners/csl-runners/chain_step_adapter.py`). The earlier
single-process multi-runtime simfabric blocker is resolved by the
subprocess-per-(kernel,step) design. Real-weight smoke-contract extraction and
audit are now in hand at
`bench/out/r3-1-31b-real-weight-smoke-extraction/{receipt,audit}.json`. TSIR
bootstrap identity covers WebGPU, WSE3, MSL, and SPIR-V at
`bench/out/r3-1-tsir-bootstrap-four-backend-canary/`, with real-kernel
coverage still narrower. Doe-WebGPU capture-graph parity still ties Doe's
WebGPU lane and Doppler's reference transcript to the same `modelId`
(`bench/out/r3-1-31b-doe-webgpu-parity/`). None of these prove Gemma 4 31B
inference on Cerebras — that still requires a WSE hardware receipt — but each
closes a stated unknown and ships as either an in-hand receipt or a typed
blocker.

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

3. **31B real-weight smoke-shape.** `bench/out/gemma-4-31b-real-weights/`
   now validates under `config/gemma-4-31b-real-weight-fixture.json`; the
   extractor records `pre_feedforward_layernorm.weight` as the explicit
   projection substitute and `skip-with-layout-metadata` for linear-attention
   layers. Next promotion is rerunning the 31B smoke receipts with
   `--weights-dir`; the claim remains `real_weight_smoke_shape`.
4. **31B manifest-shape streaming.** Land the `headDim=160`, hidden-dim 5120,
   streaming-residency, async send/receive, KV policy, and compile-artifact
   reuse mechanics. This is the point where 31B becomes a manifest-shape
   execution target rather than a smoke-shape dense runner.
5. **31B hardware parity receipt.** Bind the hardware transcript against the
   deterministic reference export with matching manifest, graph, weights,
   prompt/input, token/logit/KV artifacts, and explicit `hardware_success` or
   typed blocker taxonomy.

### No-hardware evidence ladder

These receipts are the best local work before endpoint access or a
Cerebras-assisted run. They should be included in the bundle only with explicit
claim boundaries.

| Item | Status | Current evidence | Work left |
| --- | --- | --- | --- |
| Manifest-shape compile attempt receipt | Done as typed blocker; threshold bracketed | `bench/out/r3-1-31b-manifest-compile-attempt/receipt.json` records `failed_typed` at `size=4096` with the exact `.bss` / task-table / `.data.hi` overflow and `.bss/.filters` address overlap. `bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json` brackets the per-PE memory threshold to `(2624, 2688]`. Full-graph compile receipt: `bench/out/r3-1-31b-full-graph-compile-attempt/receipt.json`. | Redesign per-PE residency for manifest shape, then rerun compile and hardware execution. |
| Cross-backend TSIR matrix | All three lanes (reference + Doe-WebGPU + CSL simfabric) closed at canary scope | `bench/out/r3-1-tsir-bootstrap-four-backend-canary/nightly-tsir-parity-canary.json` records bootstrap identity over `webgpu-generic`, `wse3`, `msl`, and `spir-v`. Live bootstrap canary at `bench/out/nightly-tsir-parity-canary-bootstrap-12/nightly-tsir-parity-canary.json` reports **12/12 `pass / pass / pass`** (Zig TSIR oracle, Doe-WebGPU, CSL simfabric all green). Real-kernel WebGPU, WSE3, MSL, and SPIR-V fixture files exist under `bench/fixtures/tsir-real-entries/` (24 entries: 6 kernels × 4 backends); bootstrap-input fixtures for the four uncovered real kernels exist at `bench/fixtures/tsir-bootstrap-inputs/`; six per-kernel Doppler transcripts with reference output values + inline probe hashes now exist at `bench/fixtures/tsir-real-doppler-transcripts/`. Canary extracts the inline `kernelProbe.hash` from each transcript when `--doppler-kernel-probes-dir` is omitted. `bench/tools/doe_parity.py` routes by manifest-entry `kernelRef` prefix (not positional kernel name), threads `kernelProbe.outputElementCount` into the Doe-WebGPU dispatcher, and writes receipts at `<args.kernel>.parity.json` so the canary finds them. Promoted real-canary snapshot at `bench/out/r3-1-tsir-cross-backend/real-canary-with-transcripts/nightly-tsir-parity-canary.json` now reports **24/24 `pass / pass / pass`**. The TSIR-CSL emit body for `attention_scores` landed at `runtime/zig/src/tsir/emit_kernel_body_attention.zig` (two-pass-stable softmax, no causal/softcap, literal scale source) with the matching Zig oracle interpreter at `runtime/zig/src/tsir/reference_interpreter.zig:tryAttentionScores`; canary closure for the 2 attention kernels still routes through hand-authored CSL at bootstrap shape (zero in → zero out, hashes match Doppler probes) pending a fixture rewire that materializes the `attention_scores` semantic body in `bench/fixtures/tsir-real-entries/`. | Author the `attention_scores` semantic body for the 2 real attention fixtures so the canary exercises the TSIR-CSL emit path instead of hand-authored CSL. |
| Bounded KV/decode simfabric receipt | Done at bounded shape; multi-token chain runs end-to-end via subprocess isolation | `bench/out/r3-1-31b-bounded-decode-integrated/receipt.json` chains `kv_write` -> `attention_decode` -> `sample` at width=4 (head_dim=32, vocab_chunk=1024). The prior simfabric_multi_runtime_unsupported blocker recorded at `bench/out/r3-1-31b-multi-token-decode/receipt.json` is resolved via the subprocess-isolated decode loop: each (kernel, step) tuple now spawns a fresh `cs_python_singularity.sh` process running `bench/runners/csl-runners/chain_step_adapter.py`, with state shuttled across boundaries as `.npy` files. End-to-end verified at `--num-steps 2`; trace records distinct per-step logits digests + sampled tokens. | Bind to a real-weight reference once available; promote to longer step counts when needed. |
| Doe-WebGPU parity against Doppler | Partial; identity-chain match landed | `bench/out/r3-1-31b-doe-webgpu-parity/parity-receipt.json` ties Doppler's 31B inference transcript and Doe's WebGPU capture graph (`graphSha256=4fdf8ca08...`, 1 shader, 1 submission) to the same `modelId`. Two-way local lane sanity confirmed. | Author a Doe-side end-to-end inference runner against the bundle to produce token-sequence parity (logits/KV digest agreement, not just modelId match). |
| 31B real-weight pinning and Doppler reference | Pinned; smoke-contract extraction and audit pass | `bench/out/r3-1-31b-real-weights/pin.json` pins HuggingFace revision `439edf5652646a0d1bd8b46bfdc1d3645761a445`. `bench/out/r3-1-31b-real-weight-smoke-extraction/receipt.json` materializes the smoke-contract slices; `bench/out/r3-1-31b-real-weight-smoke-extraction/audit.json` passes with `weightSetSha256=21ac25cb0e8bd071ca6f37fb7a147158f689b9993082c5d4a5ec74c91571d4d0` and records the manifest/fixture layer-count boundary. Doppler 31B reference transcript at `bench/out/r3-1-31b-doppler-reference/reference.json`. | Rerun 31B smoke receipts with `--weights-dir`; real-weight Cerebras execution and Doppler <-> Doe numerical parity remain hardware/downstream work. |

### Hardware risks after local evidence

If the no-hardware ladder is green, the remaining risk is no longer "do the
kernels mean the right thing?" It is whether the composed 31B program survives
real WSE execution.

| Risk | Mitigation before hardware | Closed by |
| --- | --- | --- |
| Full-shape per-PE residency overflows once lifetimes, scratch, KV, and host IO compose | Typed compile blockers are now known: manifest prefill width and full KV cache residency overflow per-PE memory in `.bss`, task table, and `.data.hi` | Redesign, clean compile, then hardware compile/run receipt |
| Fabric or collective behavior differs at production grid | Small-grid simfabric checks; CSL route/collective audit; stage L1 -> L61 -> decode | WSE execution at target grid |
| Host runtime wiring has symbol, offset, size, launch-order, or appliance-driver mismatch | Structured HostPlan metadata; pointer/hash-linked bundle; A3 already reached real 31B embed before the simfabric d2h wall | Hardware receipt with d2h outputs |
| KV state works in isolation but fails across decode steps | Bounded decode chain is proven; multi-token chain runs end-to-end on simfabric via subprocess-isolated SdkRuntimes (chain_step_adapter.py shuttles `.npy` state across kernel/step boundaries) | Hardware decode transcript with real-weight binding |
| Real weights are hash-valid but mapped with wrong shard/order/scale convention | 31B weight pin is complete for source identity; Doe/Cerebras execution with those weights is still open | Doppler <-> Doe hardware parity bind |
| Manifest-shape numerics drift from smoke-shape numerics | TSIR identity-chain receipts exist; bootstrap and real-kernel Doe-WebGPU numerical status is closed; manifest-shape and CSL numerical status remain deferred | Hardware logits/token diff |
| SDK/runtime version differs between local bundle and Cerebras run | Record `cslc`, SDK, driver, manifest, and bundle hashes in the ask | Returned receipt with matching versions |
| Correctness runs but throughput is not useful | Stage perf after correctness; capture launch timing and token latency separately | Hardware performance receipt |
| Receipt exists but cannot support a claim | Predefine required receipt fields: bundle hash, commit, prompt, weights, graph, HostPlan, logits/tokens/KV digests | Verifier-clean returned receipt |

### Remaining no-hardware evidence gaps

These are the highest-value local gaps after the in-hand receipts above. They
are useful because they either tighten a typed blocker, raise the local oracle
quality, or make the next Cerebras-returned receipt easier to validate.

| Gap | Current state | Next evidence |
| --- | --- | --- |
| Manifest compile threshold | Closed as an eight-point sweep: `size=1024,2048,2560,2624` pass; `size=2688,2816,3072,4096` fail. Threshold bracketed to `(2624, 2688]`. See `bench/out/r3-1-31b-manifest-compile-sweep/sweep-summary.json`. | Bracket is now a 64-token window — sufficient evidence; further narrowing optional. |
| Full inference graph compile | Closed at compile scope: `bench/out/r3-1-31b-manifest-fullgraph-compile-steps/trace.json.driver-result.json` records every target in `compile.targets` at `status: "succeeded"` (steps-mode materialization driven by `runtime/zig/zig-out/bin/doe-csl-host-plan-tool --mode steps`). The four prior typed blockers (`ple_rmsnorm`, `tiled`, `kv_write`, `kv_write_shared`) were all `csl_compile_pe_memory_exhausted` and are now resolved: slot-sharded KV emit body landed at `runtime/zig/src/tsir/emit_kernel_body_kv.zig` behind `Config.kv_cache_pe_strategy = .slot_sharded`; `runtime/zig/src/csl_host_plan_tool.zig` wires the strategy and threads `pe_id` / `num_pes` / `slots_per_pe` through `@set_tile_code`, shrinks `tiled` per-PE block from 64 to 32, and routes `ple_rmsnorm` so it does not propagate the manifest-shape `hidden_size` override (matching the rmsnorm pattern). The 2D KV layout (`width=num_heads × height=pe_grid_height`) keeps each PE under the WSE-3 38 KB working budget mirrored from `runtime/zig/src/targets/wse3.zig`. Synthesized receipt regeneration via `bench/tools/synthesize_full_graph_compile_attempt_receipt.py` against the new driver result is in flight elsewhere. | Bind to real-weight inputs once Task 8 (`extract_gemma4_31b_weight_slices.py`) lands; promote the synthesized receipt to a runtime/numerical receipt only after a hardware execution round. |
| TSIR kernel coverage | Bootstrap canary covers `fused_gemv`, `gather`, `rms_norm`. Input fixtures now exist at `bench/fixtures/tsir-bootstrap-inputs/` for the TSIR-covered kernels; real-kernel realization fixtures exist under `bench/fixtures/tsir-real-entries/`. Per-kernel Doppler transcripts and inline probe hashes exist at `bench/fixtures/tsir-real-doppler-transcripts/`; real-canary with transcripts now reports **24/24 `pass / pass / pass`** across the 6 real kernels × 4 backends (4 TSIR-lowerable kernels — `fused_gemv`, `embed`, `lm_head_gemv`, `rms_norm` — plus 2 attention kernels — `attention_head256_f16kv`, `attention_head512_f16kv` — closed via hand-authored bootstrap-shape CSL with all-zero output matching the Doppler probes). Bootstrap canary at `bench/out/nightly-tsir-parity-canary-bootstrap-12/` reports **12/12 `pass / pass / pass`** (gather closed by dual-mode `gather_sim_runner.py` + bootstrap-shape CSL kernel). Hand-written CSL at `bench/out/csl-real-canary-source/<kernel>/{layout.csl,pe_program.csl}`; cslc compile-dirs at `bench/out/csl-real-canary-compile/<kernel>/<kernel>/`; sim runners at `bench/runners/csl-runners/<kernel>_sim_runner.py`. The rmsnorm body uses one Newton-Raphson refinement on `math.sqrt` (CSL `math.sqrt` is hardware-approximation, not IEEE 754) so the f32 output hashes bit-for-bit to the numpy reference probe. The `attention_scores` TSIR-CSL emit body is now landed at `runtime/zig/src/tsir/emit_kernel_body_attention.zig` (two-pass-stable softmax; no causal/softcap; literal scale source) with the matching Zig oracle at `runtime/zig/src/tsir/reference_interpreter.zig:tryAttentionScores`, so manifest-shape attention is now lowerable through TSIR — only the canary fixture rewire remains. | Materialize the `attention_scores` semantic body into the 2 attention fixtures under `bench/fixtures/tsir-real-entries/` and re-run the canary against the TSIR-CSL emit path instead of the hand-authored CSL. |
| TSIR backend coverage | Closed at bootstrap and real-fixture inventory scope. `runtime/zig/src/targets/msl.zig` and `runtime/zig/src/targets/spir_v.zig` exist; bootstrap pipeline enumerates `webgpu-generic`, `wse3`, `msl`, and `spir-v`; matching real-kernel fixture files are present under `bench/fixtures/tsir-real-entries/`. | Materialize the CSL lane so `wse3` stops being identity-only evidence and becomes simfabric execution evidence. |
| TSIR numerical statuses | All three lanes closed at canary scope. **Real-kernel CSL lane: 24/24 `pass`** across all 6 kernels × 4 backends (the 2 attention kernels closed via hand-authored bootstrap-shape CSL; the 4 TSIR-lowerable kernels closed via TSIR-CSL emit + cslc + simfabric dispatch). **Bootstrap CSL lane: 12/12 `pass`** (gather closed by `gather_sim_runner.py` dual-mode rewrite + bootstrap-shape CSL kernel). `bench/tools/doe_parity.py:run_backend()` takes `(backend, kernel, inputs_path)` and dispatches: WebGPU lane subprocesses to `bench/tools/run_doe_webgpu_kernel_dispatch.mjs`; CSL lane subprocesses through `runtime/zig/tools/cs_python_singularity.sh <kernel>_sim_runner.py` against the per-kernel compile-dir under `bench/out/csl-real-canary-compile/<kernel>/<kernel>/`. `_CSL_REJECTED_KERNELS` is now an empty frozenset — CSL deferral only fires when (a) `DOE_PARITY_CSL_CHANNEL_LOCKED` env / `/tmp/doe-csl-channel.lock` is set, or (b) the per-kernel runner / compile-dir is absent. The `attention_scores` TSIR-CSL emit body and matching Zig oracle interpreter both landed (see "TSIR kernel coverage" row); the remaining gap is the canary fixture rewire so the attention rows score against TSIR-emit output instead of hand-authored CSL. | Wire the 2 attention fixtures' `bodyOp` to `attention_scores` so the canary's per-kernel CSL output flows through `emit_kernel_body_attention.zig`, then promote the canary numerical-status receipt. Manifest-shape TSIR-CSL numerical parity beyond canary scope is no longer gated on the emit body but still requires per-kernel residency work. |
| KV decode/sample | Bounded single-step chain at `bench/out/r3-1-31b-bounded-decode-integrated/` (kv_write -> attention_decode -> sample, token id `1913`). Multi-token orchestrator at `bench/runners/csl-runners/multi_token_decode_orchestrator.py` now drives the chain via subprocess isolation: one `cs_python_singularity.sh` subprocess per (kernel, step) running `bench/runners/csl-runners/chain_step_adapter.py`, with state shuttled across boundaries as `.npy` files. Each subprocess instantiates exactly one SdkRuntime, sidestepping the prior simfab_api.cc:163 multi-runtime assertion. Verified end-to-end at `--num-steps 2`. | Bind to a real-weight reference once available; promote to longer step counts when needed. |
| Doe-WebGPU vs Doppler parity | Identity-chain match at `bench/out/r3-1-31b-doe-webgpu-parity/parity-receipt.json`. End-to-end runner landed at `bench/tools/run_doe_webgpu_program_bundle_inference.mjs` — loads the Program Bundle, boots `doe-gpu/node-webgpu`, ingests the WGSL closure, attempts shader-module + compute-pipeline creation per declared kernel, walks declared `host_entrypoint` phases, and writes `bench/out/r3-1-31b-doe-webgpu-inference/transcript.json` with bundle identity + per-module compile/pipeline status. Token-sequence + KV digest fields are deferred with explicit reasons (the `host_entrypoint` constrained-JS evaluator lives in Doppler's runtime and has not been ported into Doe yet). | Port the `host_entrypoint` evaluator only as a separate receipt class so provider bootstrap does not imply token-loop parity. |
| Real-weight Doppler reference | Real-weight pin complete; `weightsDirPresent` flipped to true via symlink. The smoke-contract decisions are explicit in `config/gemma-4-31b-real-weight-fixture.json`. Extraction and audit pass at `bench/out/r3-1-31b-real-weight-smoke-extraction/{receipt,audit}.json`; audit records the fixture-driven layer-count boundary and the smoke-contract hash. | Rerun the 31B smoke receipts with `--weights-dir`, then promote any real-weight numerical claim only if the receipt explicitly binds the smoke-contract audit. |
| Manifest-shape numerical parity | No longer gated on the `attention_scores` emit body — that landed at `runtime/zig/src/tsir/emit_kernel_body_attention.zig` with the matching Zig oracle at `runtime/zig/src/tsir/reference_interpreter.zig:tryAttentionScores`, so manifest-shape attention is now lowerable through TSIR. Remaining gates: extend the bounded decode chain to manifest shape and promote an oracle-bound receipt. | Extend bounded decode to manifest shape and promote a manifest-shape oracle/parity receipt against the new attention emit body + interpreter. |
| Deployment-shape width generator | Closed: `bench/tools/derive_deployment_widths.py` consumes the threshold sweep and emits `bench/out/r3-1-31b-deployment-widths/derived-widths.json`; the receipt carries the ceiling, recommended widths, and `claim.notWhat` boundary. | Use the derived widths as the input set for the next residency/streaming compile attempts. |
| TSIR semantic schema attention | Closed: `attention_scores` is in the `bodyOp` enum at `config/doe-tsir-semantic.schema.json:96`; `query_sequence` axis role and `attention_scores` conditional schema are present. The TSIR-CSL emit body landed at `runtime/zig/src/tsir/emit_kernel_body_attention.zig` and the Zig oracle landed at `runtime/zig/src/tsir/reference_interpreter.zig:tryAttentionScores`. | Author the `attention_scores` semantic body materialization for the 2 real attention fixtures under `bench/fixtures/tsir-real-entries/` so the canary exercises the TSIR-CSL emit path and the oracle scores against non-zero inputs. |

### Local risk mitigations

These are not new proof claims; they reduce the odds of stale or unverifiable
artifacts when the next bundle or returned hardware receipt is handled.

| Risk | Mitigation |
| --- | --- |
| `cslc` version drift between local bundle and Cerebras environment | Add explicit SDK / `cslc` version metadata to `BUNDLE_META.json` and verify it on returned receipts. |
| TSIR or `doe_wgsl` edits invalidate emitted hashes | Closed: `bench/tools/prepack_hash_drift_guard.py` reads the stable pinned subset of the packer's `INCLUDE_FILES` allow-list, computes sha256, and compares against `bench/fingerprints/prepack-fingerprints.json`. Gate-regenerated timing/capture receipts remain covered by `run_cerebras_evidence_bundle.py`; the guard covers promoted/config/doc evidence. Run with `--update-baseline` to accept intentional drift; default mode fails non-zero on drifted hashes, new include paths, or removed baseline paths. The baseline file is the source of truth for the current pinned set. |
| Cluster B fixture regen drift | Put `gemma-3-1b-doe-csl-hostplan/{host-plan,doppler-program-bundle}.json` regen behind a nightly check. |
| Heavy WebGPU and heavy CSL jobs contend for the same RADV render node | Document the runner exclusion or add a slot lock around `/dev/dri/renderD128` users. |
| Returned hardware receipt is hard to bind manually | Closed: `bench/tools/verify_returned_hardware_receipt.py` ingests either a packed `.tar.gz` evidence bundle or an unpacked directory plus a returned hardware receipt JSON, validates the receipt against `config/doe-csl-int4ple-hardware-receipt.schema.json`, and binds the receipt's `sourceProgram.programBundle.{path,sha256}`, `hardwareRun.sdkVersion.{sdkVersionLabel,cslcSha256}`, and `bundleProvenance.gitCommit` against the bundle's `BUNDLE_META.json` identity anchors. Emits a structured `returned-hardware-bind.json` with `verdict` ∈ `{bound, not_bound}`, `mismatches[]`, `schemaErrors[]`, and `pinned` identity fields. `--require-hardware-success` exits non-zero when `hardwareRun.status != "hardware_success"`; default keeps typed-blocked returns advisory so a structured binding report still lands. |
| A3 partial trace is hard to read | Closed: `bench/out/overnight/20260425T175736Z/cells/csl-31b-L001-decode-truncated-size1024/hostplan-after-script-location-bind-fix/PROVENANCE.json` carries a structured summary (`summary.headline = "embed launch completed; rmsnorm_prefill stalled at d2h"`, `summary.lastSucceededLaunch`, `summary.lastObservedLaunch`, `summary.stallClassification = "simfabric_d2h_stall"`, `summary.stallTaxonomyReference` pointing at R2-1/R2-4). Validates clean against `config/doe-provenance.schema.json`. |
| Real-weight pin references a local absolute path | Closed: `bench/out/r3-1-31b-real-weights/PROVENANCE.json:reviewerNotes.{howToObtainSource,howToReproduceLocally}` records the HuggingFace `google/gemma-4-31B-it` revision (`439edf5652646a0d1bd8b46bfdc1d3645761a445`), the RDRR conversion variant (`text-q4k-ehf16-af32`), the shard-hash and manifest-hash verification path against `file_hashes.txt`, and the `--weights-dir` substitution for the bundler-host absolute path. Validates clean against `config/doe-provenance.schema.json`. |
| Scratch files still originate at repo root | Mostly closed: `runtime/zig/tools/cs_python_singularity.sh` honors `DOE_CSL_SCRATCH_CWD` and `cd`s before invoking `cslc` / sim, so scratch lands inside the named workspace dir instead of the repo root. Wired into `bench/tools/doe_parity.py`, `bench/runners/csl-runners/multi_token_decode_orchestrator.py`, `bench/tools/generate_overnight_31b_matrix.py`, and `bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py` (csl_env() defaults to `bench/out/scratch/gemma4-e2b-manifest-attention-core/`). The remaining sim runners (`{rms_norm,gather,fused_gemv,embed,lm_head_gemv,attention_*,kv_*,sample,rope,gelu,...}_sim_runner.py`) inherit the env from their parent; if invoked directly without a wrapper, scratch still leaks. `.gitignore` covers `sim_stats.json`, `sim.log`, `simconfig.json`, `plan.json`, `io_port-*.json`, `transformer_layer_shape-*.json`, `gemma4_e2b_manifest_attention_core-*.json`, `stage3_*-compile-errors.txt`, `wio_flows_tmpdir.*/`, `executables/`, and `Relu` as defense in depth. | Add `DOE_CSL_SCRATCH_CWD` defaults to any sim runner that's invoked outside a wrapper (or refuse to run without a scratch cwd). |
| Ad-hoc `PROVENANCE.json` files drift | Closed: `config/doe-provenance.schema.json` defines the canonical shape (required `schemaVersion`, `artifactKind`, `promotedAt`, `purpose`, `claim.{scope,notWhat}`; optional `produced`, `promoted`, `reviewerNotes`). `bench/tools/validate_provenance_files.py` walks `bench/out/` and validates every PROVENANCE.json against the schema; emits `bench/out/provenance-validation/report.json`. The generated report is the source of truth for the current file count and validation status. |
| External bundle can still be packed dirty | Closed: `bench/tools/pack_cerebras_validation_archive.py` refuses dirty trees by default; the self-check uses `--allow-dirty` only for its scratch archive roundtrip, and `bench/tools/prepare_cerebras_validation_bundle.sh` calls the packer without that override. |

### Overnight local evidence plan

This plan is for stronger local smoke-shape evidence on the current 64-core /
128GB unified-memory host. It should not be described as production-grid 31B
prefill/decode evidence. The production-grid path remains hardware-only.

**Phase 0 — current parallel preflight**

- Land/verify the SDK invocation wrapper so SdkLayout calls use the singularity
  path when the SDK direct-rootfs path cannot resolve `/cb` / microcode sources.
- Kick `gemma_4_31b_layer_block_smoke.py --num-layers 61 --size 1024` as the
  cheapest full-layer-count 31B smoke probe. If it works, the receipt proves
  31B dense layer-block chaining at smoke shape today.

**Phase 1 — code work**

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
  proved simfabric scales superlinearly for SUMMA d2h as PE count grows. The
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
- Work left: None. The probe ran with the extended timeout and surfaced a third
  outcome the original done-when criterion did not admit: the launch neither
  completes nor deadlocks within budget. The R2-4 sweep then confirmed
  simfabric scales superlinearly for SUMMA d2h, so the production-grid path is
  not locally viable on simfabric. The probe answered the question.
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
  - Scaling: superlinear per PE-count increase.
  - Not a deadlock: larger cells eventually succeed when given enough budget.
  - Doe-exact full transcript is non-viable on simfabric regardless.
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
  (`stopReason=max-tokens`). These are the source-side
  receipts the R2-7 parity bind would consume; the Doe-CSL side is gated on
  the live blocker in the next bullet.
- Live blocker for KV-side evidence at 31B: the truncated CSL prefill+decode
  path (`run_doe_csl_int4ple_transcript.py --max-layers 1` against the new
  31B bundle) now clears the earlier tokenized-prompt sentinel and sibling
  workspace-bind failures. The 2026-04-25 late A3 partial run completed
  `launch[0] target=embed` and reached `launch[1] target=rmsnorm_prefill`,
  including h2d for `input` and `weight`, kernel launch, and d2h for
  `output` with `elements=102144`. The run was stopped there because the
  d2h event stalled without reaching completion, matching the R2-1/R2-4
  local simfabric scaling verdict. Evidence path:
  `bench/out/overnight/20260425T175736Z/cells/csl-31b-L001-decode-truncated-size1024/hostplan-after-script-location-bind-fix/trace.json.progress.jsonl`.
  Until hardware or a smaller bounded receipt records `cacheWriteCount > 0`,
  slide 16's "structurally enabled but not yet executed" row for `kv_write` /
  `kv_read` stays unbacked.

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
