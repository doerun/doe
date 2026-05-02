# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

Current queue summary lives in `docs/cerebras-north-star.md`. Older entries
below are historical status, including the WS4 memory-blocker framing. The
active Gemma 4 31B af16 blocker is real-session token/logit/KV transcript
completion.

Sharding follow-up: owner Doe Cerebras; split
`bench/runners/csl-runners/gemma4_31b_af16_session_runtime.py` by moving
checkpoint identity and transcript artifact assembly into focused modules.

Contract note: `doe-transcript-parity-report` schema v2 makes generated-token
exact parity and logits comparison status explicit. `max_abs` is the Doppler
tolerance-backed logits gate unless a reference export declares
`sha256_exact`.

## 2026-05-02 — Cross-depth byte-identity restored after compile-root rematerialization

Gemma 4 31B and Qwen 3.6 27B cross-depth byte-identity are green again after
rematerializing the stale upstream compile roots. Gemma 1L-vs-61L is 2/2 pass
with 17 shared kernels matching; Qwen 1L-vs-64L is 2/2 pass with 15 shared
kernels matching.

Root cause was stale generated artifacts, not a numLayers-dependent emitter.
The stale `bench/out/r3-1-31b-manifest-fullgraph-compile-steps/compile/` root
was generated before emitter changes such as `sample/pe_program.csl` moving to
the bounded-smoke local-argmax form and `rope/pe_program.csl` gaining
multimodal-rope params. Regeneration policy: materialized compile roots under
`bench/out/*manifest-fullgraph-compile-steps/` must be regenerated after
emitter changes before byte-identity or dispatch evidence is restated.

The active `<bos>sky color is` L=1 simfabric transcript can now count toward
rung 6 if it reaches generated-token/logits/lm-head/KV output readiness. Qwen
still remains separately fail-closed on the frozen reference manifest missing
the L=0 probes.

## 2026-05-01 — Layer C acceptance bar split: end-to-end load-bearing, per-kernel manifest-shape regression net

`docs/cerebras-north-star.md` Layer C acceptance bar now separates the
load-bearing correctness items (end-to-end prefill + generated-token IDs
matching the frozen Doppler reference at L=1; per-step logits artifacts
comparing under the declared Doppler tolerance policy; manifest / HostPlan
/ CSL / reference-fixture hash chain unbroken) from the regression-net
artifact (all 23 manifest-shape kernels dispatched on simfabric,
bytes/digests recorded). The rung ladder also carries a one-paragraph
note that rungs 3-4 and rungs 6-9 catch different bug classes and
neither subsumes the other.

The reframing is grounded in the Active fail-closed queue items 1-4 in
the same doc: lm-head dtype resolver, tied-dense lm-head routing,
missing prefill/decode tails in the smoke graph, and HostPlan accepting
`sample` without a logits producer. All four are composition /
phase-order / symbol-resolution bugs that per-kernel manifest-shape
dispatch passed through by construction (each probe runs one kernel in
isolation with its own inputs).

Operational consequence: per-kernel manifest-shape dispatch on
simfabric is no longer a hard prerequisite for the end-to-end Cerebras
correctness claim. It remains worth producing once and rerunning on
kernel change for regression coverage and for tightening the simfabric
wallclock calibration off the 8x3 canary proxy. The end-to-end
hardware receipt with exact generated-token parity, logits digest/tolerance
evidence, lm-head dispatch evidence, and KV-cache digests is what closes the
correctness ask.

## 2026-05-01 — Active end-to-end front: frozen Doppler sky prompt, decode step 1

Diagnostic smaller-target receipt now exists for one raw prefill token plus
one real decode step. `bench/tools/export_doppler_int4ple_reference.mjs`
emits schema-valid `producer.runtime=doppler_node_webgpu` receipts and the
reference-export schema now admits the Doppler KV byte-digest proof under
`kvCacheEvidence`. The generated diagnostic receipt is
`bench/out/doppler-reference/gemma-4-31b-af16-raw1-prefill-decode1/doppler_int4ple_reference_export.json`;
it uses `--no-chat-template`, prompt `The`, tokenized prompt `[818]`,
`decodeStepsRequested=2`, generated tokens `[236774, 236780]`, and
`kvCacheEvidence.status=output_ready`. This is a shrink-wrapped
prefill+decode diagnostic target; it does not supersede the frozen Doppler
sky acceptance target unless the active gate is deliberately retargeted.

The arithmetic probe split is explicit: raw `4**4=` is four prompt tokens
`[236812, 1018, 236812, 236784]`, but the Doppler greedy continuation repeats
the pattern (`[236812, 236784, 236812, 236784]`) rather than producing
`256`. The gated receipt is
`bench/out/doppler-reference/gemma-4-31b-af16-raw-4pow4-prefill-decode/doppler_int4ple_reference_export.json`.
The semantically useful arithmetic receipt is the chat-template run
`bench/out/doppler-reference/gemma-4-31b-af16-chat-4pow4-prefill-decode/doppler_int4ple_reference_export.json`;
it has 17 prompt tokens and generated tokens
`[236812, 1018, 236812, 578, 236743, 236778, 236810, 236825]`, rendering
`4**4 = 256`, with `kvCacheEvidence.status=output_ready`.

The preferred small non-chat diagnostic is now BOS plus compact raw sky text:
`<bos>sky color is`. It has four prompt tokens
`[2, 16012, 2258, 563]` and the two-step Doppler receipt
`bench/out/doppler-reference/gemma-4-31b-af16-bos-raw-sky-color-is-prefill-decode2/doppler_int4ple_reference_export.json`
generates `[3730, 236761]`, rendering ` blue.`, with
`kvCacheEvidence.status=output_ready`. This keeps the chat wrapper out
while preserving a sane model start token and a short, checkable answer.
The seven-token `<bos>The color of the sky is` receipt remains available at
`bench/out/doppler-reference/gemma-4-31b-af16-bos-raw-sky-prefill-decode2/doppler_int4ple_reference_export.json`.

Real 31B HostPlan session active front is now the small non-chat Doppler
parity target `<bos>sky color is`, using the Doppler receipt
`bench/out/doppler-reference/gemma-4-31b-af16-bos-raw-sky-color-is-prefill-decode2/doppler_int4ple_reference_export.json`
as the generated-token/logits/KV oracle and the simfabric session tree
`bench/out/r3-1-31b-af16-hostplan-session-bos-raw-sky-color-is`. The
frozen-sky session/checkpoint tree is preserved as historical acceptance
state, but the live simfabric lane moved to the compact BOS sky target to
reach complete prefill+decode transcript evidence first.

The earlier generic two-token launch-2 tiled_31b Q4K projection remains
plumbing evidence only. It proved that the full 512x512 SUMMA sim
dispatch can be swapped for a smaller real Q4K GEMV fabric dispatch with
f16 output through `chain_step_adapter.py --split-d2h-rows`, reusable
tile output validation, and missing row/output tile replay. It is not
the acceptance target by itself.

The chunked-export D2H row-split pattern is established for the
rms_norm f16 output as 21 D2H-addressable chunks in
`runtime/zig/src/doe_wgsl/emit_csl_rmsnorm_pack.zig`. A simpler
single-buffer f16 pack landed for the TSIR emit lane in the new
`runtime/zig/src/tsir/emit_csl_f16_pack.zig` and is wired into
`runtime/zig/src/tsir/emit_kernel_body.zig::emitCslRmsNorm`. For the
tiled_31b Q4K projection, the current faster path is height-4 f16
row-split copyback from the GEMV sink column. A single-tile runtime
probe validated `output_pe_rows=4` with four row-split D2H rows and a
448-element f16 tile output; the session runner exposes it as
`--session-prefill-q4k-gemv-output-pe-rows`. Sharded batch adapters are
recorded in the batch manifest, but this simfabric host stalls
concurrent Q4K shards at `SdkRuntime.run()`, so the active compact run keeps
one Q4K shard with durable partial reuse. The Q4K shard count remains
explicit as `--session-prefill-q4k-gemv-jobs` so embed ROI and lm-head
tile parallelism stay separate from this simulator D2H envelope.
The session runner now also exposes
`--session-embed-roi-hidden-per-pe` for clean retries of the embed ROI
launch; it is guarded by a per-PE buffer budget check and records the
override in the embed ROI spec instead of changing the chunking silently.
Checkpoint resume now has an explicit
`--allow-checkpoint-runner-drift` mode for orchestration-only runner
edits; it still validates manifest/config/compile-target identity and
all persisted buffer hashes before loading completed launches.

Checkpoint storage decoupled from runtime working buffers in
`bench/runners/csl-runners/int4ple_checkpoint.py`: the hardlink path
is replaced with always-copy so per-row D2H rewrites cannot
retroactively mutate earlier checkpoint bytes. Pinned by
`bench/tests/test_int4ple_checkpoint.py::test_source_buffer_rewrite_does_not_mutate_checkpoint`.
The frozen-sky embed ROI adapter now also writes spec-hash-bound partial
checkpoints after each sublaunch, so launch 0 can resume before the
full activation buffer is assembled. Q4K tile reuse validation, Q4K
shard planning, and embed ROI partial checkpoint round-trips are pinned
by focused tests in
`bench/tests/test_int4ple_hostplan_runtime_timeout.py`.

## 2026-05-01 — real-session transcript evidence becomes the bounded-smoke gate path

The inference evidence gate now treats a complete
`realSessionRuntime.status=output_ready` transcript as the authoritative
token-output evidence path for bounded Gemma 4 31B af16 prefill/decode. A
complete transcript must match the requested decode count, carry generated
token IDs, per-step logits digests, lm-head dispatch records, and
runtime-captured KV-cache digests.
Incomplete or malformed `output_ready` transcripts fail closed instead of
falling back to per-kernel evidence.

The HostPlan streaming front door and bounded-smoke receipt builder now pass
real-session transcript evidence into the gate. Once the resumable simfabric
session reaches `output_ready`, stale or incomplete manifest-shape per-kernel
lm-head evidence no longer blocks the end-to-end prefill/decode receipt. Until
that transcript exists, current checkpoint-stopped and not-executed traces
remain blocked by explicit runtime/transcript blockers.

## 2026-04-30 — session-tiled lm-head becomes the active simfabric path

The canonical real-prompt session now has a one-decode root with a `hostplan_session_checkpoint_prefix_reuse_receipt` proving the reused prefix.
It resumed through real `ple_embed` launch 16 and validated explicit
`--session-embed-roi-jobs` groups with serialized checkpoint writes.

The active simfabric strategy moved from per-kernel lm-head aggregate-first to making lm-head tiling part of the real HostPlan session. Existing partial-only per-kernel workers were stopped after durable tile receipts; they did not touch `lm_head_prefill_stable.json` or `summary.json`.

The HostPlan executor now exposes explicit `dense_gemv_width_tiled_session` mode: a session `lm_head_prefill_stable` launch is intercepted after real activation and weight staging, dispatched through dense-GEMV width-row tiles, host-reduced into the session logits buffer, and presented to the next session launch. Launch receipts can carry `inputBuffers` for receipt-local input->output edges; tile partial receipts can carry `receiptIdentity` with `sessionStepId`, `sessionStateSha256`, `inputActivationSha256`, launch index, and target name; transcripts preserve lm-head `dispatchMode`, `sessionTileIdentity`, and tile coverage beside logits digests.

This is source and harness infrastructure only until a real prompted session run reaches `output_ready`. The bounded-smoke receipt remains blocked on `dispatch_evidence_lm_head_unbound`; sample remains bound.

## 2026-04-30 — lm-head D2H envelope and width-row tiling

The generic chain-step adapter now emits `phase:*` breadcrumbs around SDK load/run, H2D, launch, D2H, and stop. For Gemma `lm_head_prefill_stable`, those breadcrumbs show the full `width=160,height=512` manifest target and smaller `height>1` row blocks reach `launch_complete` and then wedge in SDK D2H with zero output bytes.

The real simfabric envelope found on this host is `height=1` with hidden-width tiles below the failing full width: `width=120,height=1` writes a real `partial.npy`, while `width=128,height=1` and full `width=160,height=1` wedge at D2H. The manifest runner now keeps lm-head evidence classes contract-visible: `monolithic_full_fabric`, `dense_gemv_width_tiled`, `dense_gemv_row_tiled`, and future `resident_weight_session` evidence do not share a silent gate path. Routine refresh keeps the monolithic path unless a tile mode is explicitly requested. Tiled receipts carry phase events, tile-shape D2H safety metadata, coverage, compile identity, weight input scope, and host-reduction metadata. The tiled planner clamps hidden-width chunks under the current simfabric element-count guard and only probes unsafe shapes through explicit diagnostic sweep mode.
Width-row tiling can now resume only from verified tile partial receipts that match the tile command, input hashes, compile identity, output hash, and shape-safety metadata; bare partial files still do not count. Coverage separates receipts on disk from verified reusable, fresh-emitter, and accepted partials; stale receipt files cannot inflate progress.

The SDK wrapper now defaults Singularity/Apptainer temp and cache paths to `bench/out/scratch/csl-container/` so SIF extraction does not consume tmpfs space. Failed tmpfs rootfs extraction sandboxes were cleared before the next lm-head evidence attempt.

The full `lm_head_prefill_stable` governed receipt is still not bound. The official summary now records `dispatchMode=dense_gemv_width_tiled`, `blocker=dense_gemv_width_tile_dispatch_budget_exhausted`, `tileD2HMode=single_region_copyback`, `maxRowTileHeight=1`, and verified height-1 SDK partials; `sample` was refreshed against the regenerated HostPlan hash and remains bound.

Diagnostic height-16 split-D2H tiles now carry durable `phase-trace.log` breadcrumbs and still wedge at `memcpy_d2h_start`; the dense-GEMV emitter now passes `pe_y`, gates command stream completion to row 0, and assigns row-specific reduction colors, but multi-row dense-GEMV tiles are not claim-eligible until a receipt proves D2H copyback completes.

Focused coverage lives in `bench/tests/test_manifest_kernel_probe_runner.py` and `bench/tests/test_int4ple_hostplan_runtime_timeout.py`. Follow-up: split `manifest_kernel_probe_runner.py` materialization/receipt helpers and shard `manifest_dense_gemv_tiles.py`; both exceed the Python tooling cap.

## 2026-04-30 — f16 dtype gate v2 and checkpoint 81 evidence

`config/doe-csl-dtype-contracts.json` schema version 2 requires Gemma
`q4k-ehf16-af16` and Qwen `q4k-eaf16` f16 CSL contracts to declare activation,
KV, output, lm-head/logits/sample, accumulation, and kernel-class dtype
surfaces, including Qwen q/k norm, causal prefill, gated FFN, convolution,
linear-attention/DeltaNet, SSM, and recurrence-carry obligations.

The Gemma and Qwen af16 per-kernel summaries were refreshed without inventing
evidence. Sample is bound for both models. Gemma `lm_head_prefill_stable` now
uses the dense-GEMV sink-column D2H region contract in per-kernel and session
launch adapters, but the full manifest compile still times out before writing
output bytes. A row-shard lm-head compile/run proves the smaller fabric path
can produce real output; full token-output evidence now needs compile-time
lm-head tiling plus aggregate tile receipts. Qwen remains blocked too.

`bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json` validates the
v2 `cslDtypeContract`; its only dispatch gate reason is
`dispatch_evidence_lm_head_unbound`, with session and transcript blockers
still present.

The real Gemma HostPlan checkpoint resume advanced to `bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt81.json`.
That scratch trace is `checkpoint_stopped`; it is not transcript evidence and
does not bind the final_norm -> lm_head -> sample path.

`bench/out/r3-cross-model-parity/receipt.json` was refreshed with Gemma/Qwen af16 lanes required; it remains `unbound` on Gemma budget and Qwen hash-spine blockers.

## 2026-04-30 — Doe/Cerebras af16 contract and PLE SUMMA routing land

Doe now has an explicit Cerebras CSL dtype contract registry at
`config/doe-csl-dtype-contracts.json`, validated by
`config/doe-csl-dtype-contracts.schema.json` and wired through
`config/schema-targets.json`. The Gemma `q4k-ehf16-af16` and Qwen
`q4k-eaf16` contracts declare `hostPlanActivationDtype=f16`,
`fallbackPolicy=forbid_implicit_af32`, f16 activation/KV/output transport,
f32 logits/sample comparison where the kernels require it, and
weightsRef identity preservation for shared Q4K packs.

The Gemma af16 streaming trace and bounded-smoke receipt builder now carry
`cslDtypeContract` next to the Doppler `dtypeProfile`; existing unpromoted
bounded evidence cannot promote until the current per-kernel gate binds
lm-head dispatch. The checked-in bounded receipt remains blocked by the
inference evidence gate, not promoted by the contract metadata.

Runtime staging now accepts f16 SUMMA A/B tiling and f16 constant state without
silently widening to af32. The Zig HostPlan tool routes af16 compile-target
metadata to f16 bindings and moved binding metadata into
`runtime/zig/src/csl_host_plan_bindings.zig` so
`runtime/zig/src/csl_host_plan_tool.zig` stays under the Zig source line cap.

Real-session PLE routing now records each layer's own PLE gather, projection,
and norm buffers instead of chaining layer outputs across the PLE batch. The
fresh checkpoint probe under the patched runner at
`bench/out/scratch/gemma4_31b_af16-checkpoint-f16-e2e-plefix` has persisted
real `ple_proj` launch receipts for layers 0 through 3, with the latest trace
at
`bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt64.json`.
The layer 0 and layer 1 traces are
`bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt61.json`
and
`bench/out/scratch/gemma4_31b_af16_hostplan_streaming.f16-e2e-plefix.ckpt62.json`.
That clears the previous `transform_field_missing:sourceCols` blocker for the
first PLE SUMMA projection handoff. The run remains checkpoint-stopped before
token/logit/KV transcript completion. The manifest-shape per-kernel summary
now preserves the bound sample receipt and the blocked lm-head receipt; until
lm-head binds, bounded-smoke evidence remains fail-closed.

Tracked sharding follow-up: Owner Doe Cerebras runner. Next split targets are
to move HostPlan execution-plan materialization out of
`bench/runners/csl-runners/int4ple_hostplan_execution_plan.py`, to move the
HostPlan runtime subprocess/checkpoint launch loop out of
`bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`, to move the
Gemma af16 session scheduler helpers out of
`bench/runners/csl-runners/gemma4_31b_af16_session_runtime.py`, and to move
the Gemma af16 front-door trace assembly out of
`bench/runners/csl-runners/gemma4_31b_af16_hostplan_streaming_runner.py`.

## 2026-04-30 — HostPlan launch-step D2H stalls now fail closed

Checkpoint resume reached the next HostPlan launch and entered the
`launch_step_memcpy_d2h` phase for the resumed output copyback. D2H here means
device-to-host: SDK runtime memory is being copied back into a host CPU buffer.
That scratch resume was interrupted and remains non-promoted evidence.

`int4ple_compile_target_sim_runner.py` now applies
`--launch-timeout-seconds` to the HostPlan launch-step subprocess path. A
timeout writes an `int4ple_launch_step_receipt` with
`blockers=["launch_step_timeout"]`, records `hostplan_launch_timeout` in the
progress log, and returns a typed runtime blocker instead of leaving the
front-door runner parked in the copyback path. The Gemma 4 31B af16 streaming
front door exposes the same flag through the real-session runtime. The default
launch-step bound is raised for resumed D2H copyback attempts, while `0`
continues to disable the bound for an explicitly unbounded run.

This is a fail-closed execution taxonomy improvement only. It does not bind
the current lm-head/sample per-kernel evidence, and it does not promote the
scratch checkpoint-resume attempt to token/logit/KV transcript evidence.

Tracked sharding follow-up: Owner Doe Cerebras runner. Next split targets are
to move the HostPlan runtime subprocess/checkpoint launch loop out of
`bench/runners/csl-runners/int4ple_compile_target_sim_runner.py`, and to move
the Gemma af16 weight-key resolution helpers out of
`bench/runners/csl-runners/gemma4_31b_af16_session_runtime.py`.

## 2026-04-30 — Gemma 4 31B af16 bounded-smoke blocker taxonomy follows session runtime

The bounded-smoke synthesizer now carries `realSessionRuntime` through the
HostPlan streaming trace summary and reports
`real_session_runtime_not_output_ready` when the session-runtime contract is
present but has not produced a token/logit/KV transcript. The legacy
`combined_session_runtime_absent` blocker remains only for older traces that
do not carry a real-session block.

Focused coverage now expects the current per-kernel evidence gate to report
`dispatch_evidence_lm_head_unbound` for the checked-in af16 target inventory:
the lm-head target is present, but no lm-head dispatch receipt is bound. A
current dry runner trace reaches `realSessionRuntime.status=ready_not_executed`
with scheduler bound, executor validator passed, execution plan planned, and
sample feedback bound; the remaining local blockers are per-kernel evidence and
the explicit lack of SDK execution.

A bounded `--execute --stop-after-launch 0` checkpoint run now reports
`realSessionRuntime.status=checkpoint_stopped`, with SDK bootstrap ready for
tensor movement and runtime status `stopped_at_checkpoint`. The top-level trace
still remains blocked because per-kernel evidence is not bound and the run
intentionally stops before transcript completion.

## 2026-04-29 — Gemma 4 31B af16 token-output contract gate lands

The Gemma 4 31B execution-v1 smoke graph now carries explicit
`final_norm -> lm_head -> sample` tails for both prefill-generated and
decode-generated tokens. The lm-head route no longer treats tied F16
`embed_tokens.weight` as a Q4K `lm_head.weight`; the runner-side resolver
accepts tied dense F16/BF16/F32 embeddings only for the dense lm-head path and
rejects Q4K lm-head selection unless an explicit Q4K `lm_head.weight` exists.

HostPlan lowering now allows `sample` in prefill or decode only after an
immediately preceding same-phase logits producer, and rejects compute after a
same-phase sample. The tied dense route uses the full-vocabulary
`lm_head_prefill_stable` SUMMA compile target; the generated target for the
31B smoke graph covers the vocabulary with one-row logits tiles.

Focused coverage now includes sample-without-logits, explicit prefill/decode
logits tails, compute-after-sample rejection, invalid tied-F16-vs-Q4K lm-head
selection, and prefill/decode dispatch expansion. `zig build test-wgsl`,
`zig build csl-host-plan-tool`, and the focused Python runner/receipt tests
pass locally.

The remaining open gate is runtime/evidence: stage real weights, bind host
I/O, run the serial HostPlan with KV state and sample feedback, then
regenerate HostPlan-derived receipts. Older pre-logits HostPlan families stay
superseded for token-output inference claims.

## 2026-04-29 — Gemma 4 31B af16 token-output evidence is fail-closed

The Gemma 4 31B af16 HostPlan family that ends at `sample` without an explicit
logits producer is superseded for inference claims. Receipts derived from that
inventory remain compile/front-door evidence for the emitted targets, but they
are not token-output prefill/decode evidence.

The active queue is now contract-first:

- add a manifest-driven lm-head resolver that distinguishes real Q4K
  `lm_head.weight` from tied F16 `embed_tokens.weight`;
- add the F16 dense tied-lm-head path and padded embedding handling before
  using tied embeddings for logits;
- make post-prefill and post-decode final-norm / lm-head / sample paths
  explicit in execution-v1 and HostPlan lowering;
- require every `sample` launch to consume a typed compatible logits producer,
  with dtype, shape, and layout checked before receipts bind;
- extend the real session runtime to stage weights, bind host I/O, launch the
  serial HostPlan, carry KV cache, feed sampled tokens forward, and emit
  transcript logits/tokens;
- regenerate downstream HostPlan, compile, per-kernel, streaming, and bounded
  inference artifacts after the contract lands.

The corresponding queue and invariants are tracked in
`docs/cerebras-north-star.md`. This is not a runner paper-over: the upstream
graph-to-HostPlan inventory and sample-logits contracts must fail closed before
any generated-token evidence can be promoted.

## 2026-04-29 — CSL emulator covers remaining 31B compile-target semantics

`bench/tools/run_csl_webgpu_emulator.mjs` now recognizes every compile target
in the current Gemma 4 31B af16 CSL bundle: tiled SUMMA matmul, RoPE, tiled
prefill attention, decode attention, Q4K fused GEMV, KV cache write, and
sample. The CPU semantic backend executes each family against raw fixture H2D
buffers, including PE-local flash-attention state for `compute`/`finalize` and
Q4K byte dequantization for fused GEMV. Result receipts now expose hashes for
source-defined internal state under `execution.state`. The WebGPU backend has
matching generated WGSL for the same families and creates hidden GPU buffers
for source-defined attention state when explicit `--backend webgpu` execution
is available.

The real 31B bundle still blocks at H2D fixture binding when no Doppler/RDRR or
raw fixtures are supplied; this is an input-materialization blocker, not an
unsupported CSL semantic in the source inspector.

## 2026-04-29 — Gemma 4 31B af16 session runner sharding follow-up

`bench/runners/csl-runners/gemma4_31b_af16_hostplan_streaming_runner.py`
now carries the CLI front door, weightsRef staging, dispatch expansion,
real-session scheduler, runtime-config materialization, host I/O layout
emission, and trace assembly. This exceeds the Python benchmark-tooling shard
threshold.

Owner: Doe Cerebras runner. Next split target:
`bench/runners/csl-runners/gemma4_31b_af16_session_runtime.py` should own the
real-session scheduler, weight mappings, host I/O layout, runtime-config
writing, serial launch binding, KV schedule, and sample feedback assembly.
The existing streaming runner should keep CLI parsing, refresh orchestration,
and final trace aggregation.

## 2026-04-29 — CSL emulator records D2H artifacts and simple element-wise bodies

`bench/tools/run_csl_webgpu_emulator.mjs` now accepts `--d2h-out-dir` and writes
each `memcpy_d2h` payload as a byte artifact, with the file path, byte length,
and sha256 recorded on the operation receipt. This gives emulator parity checks
a concrete file surface instead of forcing every consumer to trust only the
inline hash.

The source inspector also recognizes the simple DOE-emitted `element_wise`
identity body used by the current 31B `ple_residual` target:
`output[idx] = input[idx] * 1.0`. The semantic runs on both CPU and generated
WGSL/WebGPU backends under the explicit `elementwise_identity` label.

## 2026-04-29 — E2B attention-core receipt drift fixed

`bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py` now invokes the
shape runner with absolute repo paths when running through the SDK Python
wrapper. This prevents the container scratch CWD from turning
`bench/runners/csl-runners/gemma4_e2b_manifest_attention_core.py` into a
nonexistent scratch-relative path. Blocked shape-run fallbacks also carry the
schema-required shape fields and `executedRun.numericalParity.comparison`, so a
real SDK failure remains a valid blocked receipt instead of corrupting the
schema gate.

The E2B manifest-shape attention-core receipt, Doppler capture-to-CSL lowering
receipt, and E2B model runtime receipt were regenerated from the fixed path.
The model receipt now links the current attention-core and lowering artifact
hashes, and `bench/tools/validate_e2b_receipt_links.py` passes.

## 2026-04-29 — Restricted CSL WebGPU emulator runner lands

`bench/tools/run_csl_webgpu_emulator.mjs` now consumes
`csl_webgpu_emulator_input` artifacts and emits
`config/csl-webgpu-emulator-result.schema.json` receipts. The runner models the
ordered host operation graph, binds raw fixture H2D files by device symbol,
tracks per-symbol hashes, and executes supported launches on either the CPU
semantic backend or the Doe Node WebGPU backend when requested and available.

The supported CSL source subset is explicit: `gather`, `residual_add`, `gelu`,
`rms_norm`, and no-op `sys_mod.unblock_cmd_stream()` launches. Missing fixtures,
unsupported operation kinds, unsupported CSL source, and unimplemented
Doppler/RDRR materialization all produce blocked receipts with typed blockers;
the runner does not fabricate tensor inputs or promote a receipt to simulator or
hardware parity.

## 2026-04-29 — CSL WebGPU emulator input contract lands

`config/csl-webgpu-emulator-input.schema.json` now defines the source-preserving
input bundle for a future CSL-source-to-WebGPU semantic emulator. The contract
binds the existing HostPlan bundle surface (`host-plan.json`,
`runtime-config.json`, `simulator-plan.json`), per-target `layout.csl` and
`pe_program.csl` source hashes, the synthesized `csl_operation_graph`, and
optional Doppler Program Bundle / RDRR manifest / reference transcript identity.

`bench/tools/build_csl_webgpu_emulator_input.py` builds that artifact from an
existing CSL bundle plus driver result. The status is explicitly
`input_contract_only_not_execution`: no WebGPU execution, CSL simfabric parity,
or hardware claim is created by this artifact. It gives the upcoming emulator
a normalized source contract instead of requiring it to infer layout, launches,
copy regions, and source hashes from scattered files.

## 2026-04-29 — Gemma 4 31B af16 bounded inference smoke contract

`bench/tools/synthesize_gemma4_31b_af16_bounded_inference_smoke_receipt.py`
now emits the Gemma 4 31B af16 bounded simulator-smoke receipt at
`bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json`.

The receipt is schema-validated by
`config/doe-gemma4-31b-af16-bounded-inference-smoke.schema.json` and
hash-links the af16 Doppler manifest, the af16 frozen Doppler fixture, the
af16 HostPlan compile receipt, and the current manifest-shape per-kernel
summary. It records the caller-selected prefill/decode budget and the exact
blocked taxonomy instead of inventing a CSL token sequence. The source-side
blockers for incomplete weight-symbol mapping and stale dry-run per-kernel
summaries are now cleared in the runner trace; the receipt carries the
remaining host/runtime blockers from the streaming trace.

`bench/runners/csl-runners/gemma4_31b_af16_hostplan_streaming_runner.py`
now owns the Gemma 4 31B af16 real-inference front door: it resolves
`weightsRef` to the primary weight pack, checks shard presence, resolves all
execution-v1 weight symbols, expands the prefill/decode schedule, and exposes
the af16 per-kernel refresh command. The trace records all 31B af16 shards as
present and every required weight key as resolved, with explicit policy
records for architecture-disabled PLE projection-norm inputs and 31B
linear-attention layers that intentionally lack `v_proj`. The current
per-kernel summary is dry-run-only; when a refresh is requested and the SDK
container cannot launch, the bounded receipt reports the SDK preflight
failure rather than treating the stale dry-run summary as the active source
blocker. The remaining runtime blocker is the combined session executor that
binds cross-kernel tensors and KV cache state and emits the token/logit/KV
transcript.

`bench/runners/csl-runners/manifest_kernel_probe_runner.py` now supports
source-preserving refresh controls for future reruns: `--jobs` runs
independent kernel probes in parallel, `--resume` reuses existing non-dry-run
dispatch receipts with the current HostPlan hash when they are already bound
or reached the timeout taxonomy, and
`--schedule heavy-first` orders targets by metadata-estimated manifest-shape
I/O size so large kernels can start before smaller probes. The Gemma af16
front door passes those controls through via `--refresh-jobs`,
`--refresh-resume`, `--refresh-schedule`, and
`--refresh-timeout-seconds`. `--cmaddr` remains the explicit real-fabric path;
custom `--host-plan`, `--compile-root`, and `--refresh-out-dir` remain the way
to run a shape-reduced debug lane without mixing it with the manifest-shape
claim receipts.

The first SDK-capable refresh exposed source-side probe issues that are now
fixed in the runner path. `bench/runners/csl-runners/chain_step_adapter.py`
packs logical `f16` tensors through 32-bit memcpy words because this SDK rejects
16-bit memcpy calls. `rope` / `rope_partial` are in-place kernels, so the shared
rung-2/rung-4 classifier treats `input` as the output symbol for those kernels;
the predictor, layout receipt, and probe runner now agree on the same d2h
contract. The summary entries now carry `dispatchTimedOut` so timeout taxonomy
is visible without opening each per-kernel receipt. Existing refreshed receipts
under `bench/out/r3-1-31b-af16-manifest-simfabric-per-kernel/` predate those
fixes; rerun the refresh command on the SDK-capable host to replace the
dispatch-exit blockers with current evidence.

## 2026-04-28 — Evidence runner blocks stale attention-core receipts

`bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py` now removes the
per-shape output JSON before each SDK subprocess launch and records a typed
failure code when the subprocess cannot produce a fresh receipt. This prevents
an old successful `bench/out/manifest-shape/attention-core/*.json` file from
being loaded after the current SDK invocation fails.

On this host the E2B attention-core lane records
`sdk_container_launch_not_permitted`, so the Cerebras evidence-bundle driver
correctly reports that E2B bundle lane as blocked instead of reusing stale
success evidence. The Gemma 4 31B and Qwen 3.6 27B cross-model compile/parity
receipts remain separate: `bench/out/r3-cross-model-parity/receipt.json`
binds Gemma at 23/23 and Qwen at 19/19 with no accepted compile blockers.

## 2026-04-28 — Qwen cross-model prehardware gate bound with clean compile receipt

The Qwen 3.6 27B compile-step bundle at
`bench/out/r3-2-27b-manifest-fullgraph-compile-steps/` has a current
driver result whose compile section succeeds for every target. The previous
typed blockers for `ssm_linear_attention` and
`attn_prefill_kv_axis_sharded` are closed in the receipt.

The host-plan tool now resolves the checked-in simulator driver correctly
from repo-root invocations. `ssm_linear_attention` shards
`linear_state` with `value_dim_per_pe`, and
`attn_prefill_kv_axis_sharded` derives PE identity from CSL `<layout>`
coordinates rather than per-tile `@set_tile_code` params. `gemv` is
cslc-clean at Qwen shape after the fused GEMV layout reserved both x and y
collectives task-id pairs for SDK `collectives_2d` validation.

`bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`
now fails closed on stale driver coverage and writes `blocker.class="none"`
when all measured compile verdicts succeed. The joint Gemma/Qwen gate at
`bench/tools/aggregate_cross_model_parity.py` consumes those per-model
compile summaries and writes
`bench/out/r3-cross-model-parity/receipt.json` with `verdict=bound`.

## 2026-04-28 — Qwen SSM body ops bound into exec-v1 smoke config

The Qwen 3.6 27B non-hardware scope now covers the hybrid architecture rather
than only the 16 full-attention layers. The smoke config dispatches the
gated-DeltaNet SSM body sequence with `repeat=48`: `conv1d_depthwise`,
`l2_normalize` for Q/K rows, then `linear_attention`.

The exec-v1 `opToSpec` table routes all three ops to semantic CSL patterns.
`emit_csl_semantic_ops.zig` delegates each PE program to the existing TSIR
body emitters, so the route shares the same math pinned by
`reference_interpreter.zig`: causal depthwise conv, row L2 normalization, and
the shared-norm DeltaNet linear-attention state update. The host-plan tool now
emits compile params and binding metadata for the three SSM body kernels, and
the paired-gate canary pins the new op mapping plus body-program fragments.

## 2026-04-28 — Qwen fused GEMV row reduction switches to collectives_2d

The Qwen 3.6 27B `gemv` width>=3 non-hardware blocker is closed at the Doe
emit surface. The fused GEMV layout no longer hand-configures a `reduce_color`
east-west route. It imports `<collectives_2d/params>`, passes per-tile
`c2d_params` to the PE program, and the PE program imports
`<collectives_2d/pe>` and calls `reduce_fadds` with root `width - 1`.

This keeps SDK source out of the repository while using the SDK's existing
teardown/switch FSM through the normal cslc import path, matching the SUMMA
collectives integration pattern already carried by tiled matmul. The Qwen GEMV
cell fixture mirrors the emitter shape, and the WGSL structural canary pins
that `fused_gemv_dequant` emits collectives imports rather than manual
`@set_color_config` routes.

## 2026-04-27 — Qwen 3.6 27B Doe-side trio lands; typed-blocker chain pinned

The `feat/qwen-3-6-bringup` branch now carries the parallel of the Gemma
4 31B Doe-side evidence trio, all sitting on top of the SUMMA wedge merge:

1. **Smoke config.** `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`
   mirrors the Gemma 4 31B smoke shape with Qwen's actual numbers: GQA
   24:4, head_dim=256, hidden=5120, intermediate=17408, 64 layers,
   partial-rotary 0.25, queryKeyNorm, attentionOutputGate=swish, SwiGLU
   FFN. `scopeRestrictions` block names three explicit blockers
   (linearAttentionLayers, mropeInterleaved, causalAttentionPrefill).
2. **Synthesizer.** `bench/tools/synthesize_qwen_3_6_27b_full_graph_compile_attempt_receipt.py`
   imports the Gemma synthesizer's residency/classifier helpers and
   only carries Qwen-specific defaults + claim text + scopeRestrictions
   lift from the smoke config. Pre-bundle preflight verified: exits 2
   with the host-plan-tool invocation pointer.
3. **Per-kernel byte-identity test.**
   `bench/tests/test_qwen_3_6_one_layer_per_kernel_byte_identity.py`
   exercises the 1L == 64L per-kernel CSL byte-identity property. Skips with
   typed pointer when the upstream Qwen compile root is absent.
4. **Validator binding test.**
   `bench/tests/test_validate_frozen_qwen_3_6_doppler_reference.py`
   binds the (model-agnostic)
   `bench/tools/validate_frozen_doppler_reference.py` to the Qwen
   fixture path. Skips with typed cross-repo pointer naming the Doppler
   `run-program-bundle-reference.js --tsir-fixture-dir` invocation that
   produces the fixture.

**Trio now exercises the bundle end-to-end at honest scope.** The
smoke config was revised this tick to use ops the host-plan tool
recognizes today (single-input `silu` for FFN activation; the `o_gate`
step is dropped entirely rather than mapped to a non-gated stand-in).
`scopeRestrictions` was extended with `attentionOutputGate` and
`swigluFfnFusedGate` named-blocker entries so the receipts cannot be
misread as covering Qwen's actual gated forms — those need
`silu_gated` / `sigmoid_gated` `KernelPattern` variants + classifier
wiring + opToSpec entries to land before the smoke config can carry
the gated ops. The audit-named TSIR emit-body work is already done on
this branch (see emit_kernel_body_gated.zig); the doe_wgsl classifier
surface is the open downstream blocker.

With the revised smoke config, all three trio legs now run:

- `doe-csl-host-plan-tool` materializes a 15-target Qwen bundle at
  `bench/out/r3-2-27b-manifest-fullgraph-compile-steps/`;
- the per-kernel byte-identity test passes after rematerializing the compile
  root from the current emitter;
- the synthesizer emits
  `bench/out/r3-2-27b-full-graph-compile-attempt/receipt.json` with
  `compileTargetCount=15`, `compileAttempted=true`,
  `compileSucceededCount=10`, `compileFailedCount=1`,
  `scopeRestrictions` lifted from the smoke config.

cslc 2.10.0 ran against each compile dir; 10/11 unique kernels return
`Compilation successful` (embed, rmsnorm, tiled, rope_partial,
residual, silu, gemv, kv_write, attn_decode, sample). The 1 failure is
`attn_prefill` with `failureCode=linker_pe_memory_overflow` — the
same per-PE-residency blocker the Gemma 4 31B prefill ladder carries.
Decode path is fully cslc-clean. The 4 phase-specialized kernel
variants (rmsnorm_prefill/_decode, residual_prefill/_decode) share
CSL byte-identically with their base kernels (verified by the byte-
identity test) and therefore inherit the base verdicts; they are
recorded as `not_attempted` in the receipt's per-target list pending
explicit alias-resolution in the synthesizer.

The rope kernel's `compileParams` now read `head_dim=256, num_pairs=32`
— validating the partial-rotary wiring delta this tick: at Qwen's
manifest `partialRotaryFactor=0.25`, the canonical formula
`head_dim * factor / 2 = 32` rides through correctly (was previously
the kernel-default 64).

Open follow-ups (to make the receipts cite Qwen's actual gated forms,
not stand-ins):
The validator-binding test still depends on Doppler-side capture
(separate cross-repo branch `feat/qwen-3-6-bringup` in the doppler
tree), which is named in the test's typed-skip pointer.

- `silu_gated` / `sigmoid_gated` through the classifier + opToSpec
  chain (KernelPattern variants in emit_csl_classify.zig + WGSL
  pattern-detection branches + opToSpec entries + emit dispatch
  through emit_kernel_body_gated.zig). The TSIR-side work landed on
  this branch; only the doe_wgsl surface remains. Doe-side; unblocks
  the smoke config carrying the actual gated ops.
- Doppler `feat/qwen-3-6-bringup`: capture a deterministic Qwen
  inference run + the TSIR boundary-probe fixture
  (`bench/fixtures/r3-2-27b-doppler-frozen/`).
- cslc invocation against the Qwen bundle (driver-result.json) so the
  synthesizer's `compileAttempted` flips to true and per-target
  failureCode values get attached. Same SDK toolchain dependency the
  Gemma 31B receipts have.
- mropeInterleaved lowering (Qwen-only; deferred until 1D-rotary smoke
  receipts pass).
- Linear-attention layer body op (Qwen 3.6 hybrid; named blocker in
  smoke scopeRestrictions; deferred).
- Causal prefill in `AttentionScoresBody` (shared with Gemma; deferred
  until the prefill simfabric ladder lands).

## 2026-04-27 — Fused-dequant SUMMA wedge (Q4K-input) compiles + executes on simfabric with parity

The `feat/fused-dequant-summa` branch lands the on-PE Q4_K_M dequant SUMMA
wedge end-to-end:

1. **Emitter.** `runtime/zig/src/doe_wgsl/emit_csl_matmul_q4k.zig` produces
   CSL where the B operand is broadcast as raw Q4K bytes and dequanted on
   each PE before the SUMMA fmac inner loop. Layout export at
   `emit_csl_layout.zig::emitMatmulQ4kLayout` types B as `[*]u8` (storage
   index 1). Classifier branch `tiled_matmul_q4k_dequant_b` recognizes the
   pattern (`emit_csl_classify.zig`).
2. **Cell parity.** `bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/run.py`
   drives `cs_python` with cliff-distributed Q4K bytes and compares against
   canonical Doppler dequant + host matmul. Cell receipt
   `bench/out/r2-q4k-fused-dequant-summa/wedge-q4k/receipt.json` records
   `verdict=pass` at P=2 Mt=8 Kt=256 Nt=8 with parity within float32
   precision.
3. **Bound dispatch receipt.** `bench/out/r3-1-31b-multi-token-decode-q4k/`
   carries `mode=compile_and_execute`, hash-links the cell receipt and
   cslc invocation, and records the structural fabric-byte ratio
   (`baselineFabricBytes_f32_dense / wedgeFabricBytes_q4k_block256`).
   `cellParityPassed=true`. Receipt synthesizer
   `bench/tools/synthesize_q4k_summa_dispatch_receipt.py` carries three
   modes: `pending`, `compile_and_execute`, `dispatch`.
4. **Validation gate.** `bench/tests/test_q4k_summa_receipt_parity.py`
   pins the baseline witness, the wedge structural invariants, and the
   compile_and_execute milestone (cell parity flag + tile shape). Dispatch
   parity tests skip until a multi-token decode chain re-runs with
   `b_dtype=.q4k_block256`.

What this is not: not a speed claim (simfabric is correctness-only); not
hardware; not yet bound to Gemma 4 31B's full compile sweep shape. The
small SUMMA cell proves the mechanism. Promotion to manifest-shape SUMMA
is named in the dispatch receipt's `remainingForFullClaim`.

## 2026-04-26 — Rung 3 calibration lands; rung 6 closes for head_dim=256; rung 8 launch gate flips to allow

Three landings against the manifest-shape simfabric proof plan in
`docs/cerebras-north-star.md`:

1. **Rung 3 calibration via canary-proxy.** Manifest-shape simfabric (246x236
   fabric, ~58k PEs) does not finish a single-kernel dispatch in tractable
   wall-clock on local hosts; the rung-3 `manifest_kernel_probe_runner` times
   out at the chain_step_adapter 1800s timeout. New tool
   `bench/tools/derive_canary_proxy_calibration.py` derives a
   `bytesPerCycle` + `perPatternCyclesPerCall` calibration from the per-kernel
   `bench/out/csl-real-canary-compile/<kernel>/scratch/sim_stats.json` files
   that the bootstrap canary lane already produces (8x3 fabric, ~14
   simulated tiles, finishes in <1s). Receipt class
   `manifest_shape_per_kernel_dispatch_proxy` carries
   `calibrationSource: canary_proxy` and a `claim.notWhat` block naming
   exactly what this is not (manifest-shape evidence). 7/7 tests in
   `bench.tests.test_derive_canary_proxy_calibration`. Replace with a real
   manifest-shape rung-3 dispatch sha256 once hardware execution lands
   (R3-1 / R3-3).

2. **Rung 8 launch gate flips to `allow`.** Rerunning
   `bench/tools/predict_simfabric_wallclock.py` with the canary-proxy
   throughput config produces `calibrated=True`, `bytesPerCycle=0.00449`,
   `grandPredictedCycles=205,502,778`, prefill+decode=
   103,040,639+102,462,139. `config/manifest-simfabric-budget.json` now
   carries the calibration receipt's sha256 in `calibrationStatus` plus
   ceilings at 1.5x predicted. `bench/tools/check_simfabric_budget_gate.py`
   decision: `allow` (was: `deny`). Test
   `test_bootstrap_ceiling_in_repo_denies_with_default_budget_shape` was
   asserting the in-repo ceiling carried the bootstrap token; split into
   two tests covering the uncalibrated-budget and bootstrap-token-in-ceiling
   paths so the in-repo ceiling can carry a real calibration.

3. **Rung 6 partial close: attention canary head_dim=256 routes through
   TSIR-CSL emit body.** New Zig executable
   `runtime/zig/src/main_emit_tsir_attention_canary.zig` (build via
   `zig build emit-tsir-attention-canary`) emits the attention CSL via
   `runtime/zig/src/tsir/emit_csl.zig:emitSemanticFunction`. New sim runner
   `bench/runners/csl-runners/attention_head256_f16kv_tsir_sim_runner.py`
   dispatches via `cs_python` against the cslc-compiled output. Bootstrap
   inputs (Q/K/V all-zero) produce sha256
   `5f70bf18a086007016e948b04aed3b82103a36bea41755b6cddfaf10ace3c6ef` --
   exact match to the Doppler probe at
   `bench/fixtures/tsir-real-doppler-transcripts/attention_head256_f16kv.doppler-transcript.json`.
   Same identity, different emit path. Three real cslc-rejection bugs
   fixed in `emit_csl.zig` (memcpy_params not forwarded; per-binding
   `@export_name` missing; layout-level params not forwarded to PE) and
   one in `emit_kernel_body_attention.zig` (`f32 = 1` rejected as
   comptime_int; switched to `{e}` formatter). 972/972 tests in
   `zig build test-wgsl`.

   head_dim=512 stays on hand-authored canary CSL: the TSIR-emit kernel's
   full `[kv_len * head_dim] = [15 * 512]` f32 K/V tensor (60 KB per PE
   for K + 60 KB for V) blows the WSE-3 single-PE 48 KB SRAM budget at
   width=1. Closing it needs either multi-PE distribution along the kv
   axis or a zero-input-elide mode in the attention emit body.

Cross-repo work (Doppler tree, separate from this commit set): the
rung-5 Doppler reference fixture data path landed
`src/inference/pipelines/text/tsir-fixture-writer.js` plus
`tools/run-program-bundle-reference.js --tsir-fixture-dir` so a Doppler
inference run captures activations at the four TSIR boundary points
(`post_rmsnorm`, `post_qkv`, `post_attn`, `post_ffn`) as `.npy` files.
A 31B node-surface partial run captured 3 of 4 boundary tensors at
L=0 before being killed (Gemma 4 31B has a chat-template / tokenizer
bug separate from the fixture path; user is debugging in another
thread). Doe-side `bench/tools/build_frozen_doppler_reference_manifest.py`
assembles the fixture into a rung-5 manifest the validator binds.

Open follow-ups:

- Doppler chat-template debug (cross-repo, gates re-running the fixture
  capture).
- Once 4-of-4 .npy files are captured at L=1, build the manifest and
  validate it; downstream rungs 6/7/8/9 then bind.
- Rung 6 dispatch and rung 8 dispatch at manifest shape: gated on
  hardware execution since manifest-shape simfabric is wall-time
  prohibitive (each kernel invocation alone exceeds the 1800s
  chain_step_adapter timeout).
- Rung 9 manifest-shape multi-token orchestrator (the named
  `stateful_multi_token_runner_absent` blocker in
  `bench/out/r3-1-31b-bounded-multi-token-decode/receipt.json`).
- attention_head512_f16kv TSIR-CSL emit body: multi-PE distribution
  along the kv axis or zero-input-elide.

## 2026-04-25 (late+2) — Evidence gate drops E2B INT4 PLE lane from the ship bundle

`bench/tools/run_cerebras_evidence_bundle.py` no longer runs the E2B INT4 PLE
bounded-reference / blocked-Doe-transcript / parity-bind / hardware-preflight
lane as part of the external bundle gate. That lane was a mixed control-fixture
surface and had become inconsistent with the 31B-first evidence story.

E2B remains a control fixture through the manifest-shape, attention-core,
RDRR/int4ple structural, and receipt-link gates. The typed blocked execution
slot moves to the 31B A3 partial HostPlan evidence promoted under stable
`bench/out/r3-1-*` paths; it is described strictly as partial typed-blocked
execution evidence, not decode/KV or parity evidence.

While refreshing the gate, C12 exposed a stale raw-`math.sqrt` CSL contract
violation. The TSIR CSL RMSNorm emitter and reduction lowering now emit and use
the `sqrt_nr` Newton-refined wrapper, and the self-check no longer audits dated
overnight/deprecated int4ple generated outputs as if they were live production
sources. Final bundle gate verdict after the lane removal and C12 fix:
`passed` (23/23, 0 skipped).

## 2026-04-25 (late+1) — HostPlan execution metadata fails closed on structured artifacts

`bench/runners/csl-runners/int4ple_hostplan_execution_plan.py` no longer
regex-scrapes `layout.csl` or `pe_program.csl` to infer exported symbols,
per-PE arrays, pointer-backed symbol aliases, or compile-time constants. The
execution planner now accepts only structured metadata:

- inline `compileTargets[].metadata.bindings` emitted by the Zig HostPlan path;
- `layout.metadata.json` sidecars for exported device variables/functions;
- `pe_program.metadata.json` sidecars for variables, exported backing symbols,
  and compile-time constants.

If those artifacts are absent, the planner reports the existing typed blockers
(`layout_exports_missing`, symbol-not-exported, unresolved launch function)
instead of silently reconstructing the contract from generated CSL source. New
tests cover both sides: sidecar-only targets still plan without CSL source, and
source-only targets now fail closed.

## 2026-04-25 (late) — 31B truncated HostPlan clears prompt/wrapper blockers, stops at expected simfabric D2H wall

A3 31B truncated HostPlan now reaches real CSL execution instead of failing on
artifact plumbing. Two concrete blockers cleared:

- `bench/tools/run_doe_csl_int4ple_transcript.py` now materializes the Program
  Bundle tokenized prompt from Doppler's bundled tokenizer when the bundle did
  not capture a `tokenizedPrompt` artifact. The emitted
  `program_bundle_tokenized_prompt.u32` is checked against Program Bundle
  `prefillTokens` and `prompt.tokenIdsHash` before the HostPlan is built.
- `runtime/zig/tools/cs_python_singularity.sh` now binds the workspace root
  derived from the wrapper's script location, not the transient SDK workdir.
  This makes sibling Program Bundle shards under `/home/x/deco/doppler/...`
  visible inside `cs_python` / Singularity subprocesses.

Partial A3 evidence:

- Output dir:
  `bench/out/overnight/20260425T175736Z/cells/csl-31b-L001-decode-truncated-size1024/hostplan-after-script-location-bind-fix/`
- Progress log:
  `bench/out/overnight/20260425T175736Z/cells/csl-31b-L001-decode-truncated-size1024/hostplan-after-script-location-bind-fix/trace.json.progress.jsonl`
- Observed boundary: `launchIndex=0 target=embed` completed successfully after
  all 28 embed ROI sublaunches. `launchIndex=1 target=rmsnorm_prefill` then
  completed constructor/load/run, copied `input` and `weight` h2d, launched the
  kernel, and entered d2h for `output` with `elements=102144`.
- The run was stopped deliberately after the progress log stayed at that d2h
  event for several minutes. This matches the R2-1/R2-4 simfabric
  superlinear-throughput finding; continuing A3 on local simfabric would not be
  a credible way to reach decode/KV evidence.

Claim discipline: this backs 31B Program Bundle tokenization, SDK wrapper
binding, embed execution, and the first post-embed 31B HostPlan launch reaching
real I/O. It does **not** back full 31B prefill+decode, `kv_write`/`kv_read`,
sample, per-step logits, token-id sequence capture, or positive parity. Slide
16's KV row remains "structurally enabled but not yet executed" until a
hardware run or smaller bounded receipt records `cacheWriteCount > 0`.

## 2026-04-25 (afternoon) — 31B-primary pivot, R2 verdict closure, singularity wrapper, L1+L61 receipts, overnight matrix

A multi-decision turn. Pinning here so tomorrow's session does not re-derive.

### Strategic reframe

- **31B is the product target; E2B is the test fixture.** Existing E2B claims
  (real-weight smoke, manifest-shape evidence, attention-core diagnostic) stay
  valid in CLAIM_SCOPE — the demotion is in narrative ordering, not in claim
  substance. Recorded in `docs/cerebras-north-star.md` Queue + 31B-first
  execution plan sections.
- **Bundle path (b) breaks the simfabric-vs-hardware chicken-and-egg.** Path
  (b) (Cerebras-assisted bundle run) does NOT require simfabric parity to
  unlock; the existing bundle is sufficient to circulate. R2-6 does NOT gate
  R2-10; R2-7 parity bind is execution-target-agnostic. The 14-failure bundle
  gate regression is real but not load-bearing for the 31B hardware ask.

### R2 closure verdicts

R2-4 SDK 2.10 D2H sweep against canonical
`csl-extras-202604101435-6/examples/benchmarks/gemm-collectives_2d/`
(`bench/runners/r2_4_summa_sweep.py`):

| Cell | P | Mt | Total C | Run sec | Result |
|------|---|----|---------|---------|--------|
| baseline | 4 | 14 | 12.5KB | 3.9 | success |
| tile-up | 4 | 22 | 30KB | 9.7 | success |
| count-up-1 | 8 | 14 | 50KB | 15.1 | success |
| count-up-2 | 16 | 14 | 197KB | 92.2 | success |
| count-up-3 | 32 | 14 | 787KB | 948.1 | success (20-min timeout) |
| doe-exact | 54 | 22 | 5.6MB | extrapolated ~110min | timed out |

Findings: trigger axis is PE-count P; per-PE bytes scale linearly when P held
constant; scaling is ~O(P^3) per doubling (P=8→16: 6.1×; P=16→32: 10.3×). NOT
a deadlock; just simfabric superlinear scaling. R2-1's earlier "kernel
completed compute, host D2H hangs" framing was wrong; both compute and d2h
are gated on simfabric throughput. R2-2 (timeout probe) closed insufficient,
not failed. R2-3 (SUMMA fence audit) closed: Doe matches canonical
structurally. R2-4 closed with the sweep above. R2-5/R2-6/R2-7 relabeled to
"Control-lane diagnostic" so the Queue (R2 demoted) and per-item sections
agree.

### Singularity wrapper landed

Root-caused a class of bundle-gate failures to `cs_python` on this host
preferring `--direct-rootfs` mode, which does NOT bind `/cbcore` for cslc
subprocesses. Paint flow then fails with `Could not find source code for
"/cbcore/src/sdk/ucode/io_port.csl"`. Fix:

- `runtime/zig/tools/cs_python_singularity.sh`: Doe-local wrapper that
  invokes `singularity exec` with the canonical SIF binds. Falls back to
  the SDK default cs_python when singularity is not available.
- `runtime/zig/tools/csl_sdk_driver.py`: `infer_cs_python_from_cslc` prefers
  the wrapper when both singularity (or apptainer) and a SIF are available.
- `bench/tools/run_gemma4_e2b_manifest_shape_attention_core.py`: same
  preference inside its `select_cs_python`.

Validation: `gemma4-e2b-manifest-shape-attention-core` flipped FAIL → PASS
under the wrapper. The 14-failure bundle gate cluster splits into two:
paint-flow (singularity-fixable, attention-core type) and stale-fixtures
(regen-fixable, int4ple-blocked-transcript type with missing
`gemma-3-1b-doe-csl-hostplan/host-plan.json` and
`doppler-program-bundle.json`). The patch addresses the first cluster, not
the second.

### 31B simfabric receipts: L1 and L61 landed

First-ever full Gemma 4 31B 61-layer execution end-to-end on simfabric.

| Cell | numLayersChained | Compile | Run | numericalParity | Receipt |
|------|------------------|---------|-----|-----------------|---------|
| L1 | 1 | 262.2ms | 7167.9ms | passed=True, max_abs_err=0 | `bench/out/r3-1-31b-l1-dry/trace.json` |
| L61 | 61 | 237.5ms | 395310.3ms | passed=True, max_abs_err=0 (all 61 layers) | `bench/out/r3-1-31b-l61-smoke/trace.json` |

Per-layer L61 timing flat-consistent: min 4.8s, mean 6.5s, max 7.9s. No
SUMMA-style scaling pathology in the smoke shape — the smoke's bounded
per-PE byte count keeps simfabric viable at L61 / 61 layers. Captured under
R3-1 done-when in `docs/cerebras-north-star.md`; hardware-side equivalents
remain pending R2-10 / endpoint access.

### Overnight matrix infrastructure landed

User-authored `bench/runners/overnight_evidence_matrix.py` (289 LOC):
bounded-concurrency, lane-aware (webgpu_heavy=1, csl_heavy=2, light=8),
per-cell isolation, resume that skips already-succeeded cells, JSON-driven
matrix, 5-state status taxonomy including `missing_receipt` (catches "exit 0
but no receipt written"), full test coverage. Agent-authored
`bench/tools/generate_overnight_31b_matrix.py` templates the standard 31B
sweep into the orchestrator's matrix shape with stable zero-padded IDs and
per-cell `expectSuccessReceiptPath` paths under `cells/<id>/`.

### TSIR-as-truth incremental progress

Commit `212a46868` adds `tryResidualAdd` and `tryGeluGated` to the reference
interpreter (`runtime/zig/src/tsir/reference_interpreter.zig`). 7 of 11
transcript bodyOps now have a host-side parity oracle (was 5). `kv_write` /
`kv_read` deferred — the read-write binding semantics need a convention pick
for whether `inputs[]` extends to read-write slots or a separate
`prior_state[]` parameter is added to `run()`. R1-1 done-when updated.

### WebGPU re-run finding (separate thread)

`bench/tools/run_doe_webgpu_shared_contract.py` re-run for Gemma 3 1B today
flipped to `status=failed` with blocker `Logits has no finite candidate
logits after masking the pad token` — NaN/Inf upstream in decode, NOT the
SPIR-V emitter issue B1/B2 fixed earlier this cycle. The `-real` path
(Apr 24 18:19, post-B2) still succeeds with full 8-step decode, so the
divergence is in HOW the shared-contract wrapper invokes the exporter
(`--runtime-profile profiles/production` + capability-aware policy).
Distinct triage thread, not blocking 31B work.

### What landed in tonight's overnight sweep

`bench/out/overnight/20260425T175736Z/` — 12 cells (8 csl_heavy + 4 light),
Lane A intentionally deferred behind `--include-lane-a` flag pending Doppler
31B workflow verification (now resolved in the generator with the canonical
`run-program-bundle-reference.js --manifest --model-dir --conversion-config
--surface node --prompt --max-tokens --report-out --out` invocation;
re-runnable tomorrow with `--include-lane-a`). Critical evidence pieces:
`csl-31b-L061-size1024` (independent receipt for L61 bundle citation),
`csl-3-1b-L001-decode-truncated-size1024` (first ever exercise of
`kv_write`/`kv_read` in any Doe receipt via `--max-layers 1` truncation in
`bench/tools/run_doe_csl_int4ple_transcript.py`).

## 2026-04-25 — Structured compile-target metadata first slice

The HostPlan executor now has a structured metadata path for compile-target
bindings, so fresh Zig-emitted simulator plans no longer require Python to
reparse `layout.csl` and `pe_program.csl` text for the kernels covered by the
metadata contract.

Landed in this entry:

- `config/doe-wgsl-simulator-plan.schema.json`: `compileTargets[]` now accepts
  `metadata` with target phase, binding shape, per-PE shape,
  staging/detile transforms, and weight-source hints.
- `runtime/zig/src/doe_wgsl/emit_csl_host_plan.zig`,
  `runtime/zig/src/doe_wgsl/emit_csl_simulator.zig`, and
  `runtime/zig/src/csl_host_plan_tool.zig`: Zig compile targets can carry
  structured binding metadata, and simulator-plan emission writes it for
  `reduction`/`rms_norm`, `residual`, `gelu`, and `tiled_matmul`.
- `bench/runners/csl-runners/int4ple_binding_metadata.py` plus
  `int4ple_hostplan_execution_plan.py`: Python materialization consumes the
  structured metadata first and falls back to CSL text parsing only for legacy
  targets. The tiled path still enriches metadata with concrete SUMMA
  dimensions and preserves nested q4k/f16/bf16 staging transforms.
- `bench/runners/csl-runners/int4ple_runtime_scheduler.py`: residual and GELU
  dataflow symbols now match the real WGSL bodies (`input`/`residual`/`output`
  for residual, `input`/`output` for GELU) instead of the previous shared
  elementwise stub symbols.

Validation:

- `python3 -m unittest bench.tests.test_int4ple_binding_metadata
  bench.tests.test_int4ple_scheduler_readiness
  bench.tests.test_csl_host_plan_kernel_patterns` passed.
- `python3 -m unittest bench.tests.test_csl_gelu_wgsl_backed_fixture` passed.
- `python3 -m unittest bench.tests.test_config_schemas` passed.
- `zig build test-wgsl` passed; only existing TSIR line-limit allowlist notices
  were printed.
- `python3 bench/gates/csl_operation_graph_gate.py` passed.
- `git diff --check` passed.

Still not claimed:

- `python3 bench/gates/schema_gate.py` is blocked on this checkout by missing
  local `bench/out/...` evidence artifacts, not by the metadata schema; the
  focused schema/unit coverage above is the current local validation.
- Full simulator evidence still needs regeneration before this becomes a
  numeric-parity claim. The permanent evidence gate still needs to distinguish
  HostPlan plumbing success from transcript/logit parity success.
- The next CSL status update should split this shard by subdomain before it
  approaches the 1200-line live shard cap.

## 2026-04-25 (cycle 20) — Live HostPlan kv_read now sourced from TSIR (fourth ownership transfer; kv_cache file fully migrated)

Item 2 cycle-20 slice. Symmetric counterpart to cycle 19's
`emitWrite` swap. The hand-written body of
`emit_csl_kv_cache.emitRead` is gone. Same recipe: extract
WGSL-derived storage names from `module` + `info`, build a TSIR
SemanticFunction with bindings named to match those exact
symbols, delegate through `emitWithConfig` with `var_prefix=""`.

The `kv_read` body has no state buffer (no `decode_position`);
the read range is supplied by the host plan via `read_start` /
`read_len` params. TSIR's `emitCslKvRead` already declares those
params with the correct defaults (`read_start: i16 = 0;`,
`read_len: i16;`).

`emit_csl_kv_cache.zig` is now fully TSIR-driven on both halves
of the KV-cache lifecycle. The hand-maintained-emitter surface
in this module is empty.

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–19).
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.

Loop tally for live ownership transfers from hand-written
emitters to TSIR-driven CSL: **8 kernel bodies** (residual /
residual_prefill / residual_decode + gelu / gelu_prefill /
gelu_decode + kv_write + kv_read).

Hand-maintained surface remaining for Item 2: `emitRmsNormPe` in
`emit_csl_semantic_ops.zig` is the last entry. The TSIR
`rms_norm` body needs a Gemma `1+w` offset Config knob (or a
body-level flag) before swapping; the live hand-written body
emits `output[idx] = input[idx] * inv_rms * (1.0 + weight[idx])`,
where the `1.0 +` is the Gemma offset. TSIR's current emitter
uses the standard `inv_rms * scale[d]` form. Adding the offset
is a contained Config addition similar to `chunk_size_default`.

## 2026-04-25 (cycle 19) — Live HostPlan kv_write now sourced from TSIR (third ownership transfer)

Item 2 cycle-19 slice. Cycle 16's recipe applied to
`emit_csl_kv_cache.emitWrite`. The hand-written body — including
its `pe_id` / `num_pes` unused params, separate
`emitDecodePositionState` call, and module-driven storage-pointer
loop — is gone. The live wrapper extracts the WGSL-derived
storage-binding names from `module` + `info`, threads them into
a TSIR `SemanticFunction` (binding names `kp` / `vp` / `kc` /
`vc` from the WGSL globals plus the literal `position` for the
runtime state buffer), and asks TSIR to emit with no `tsir_` var
prefix.

The exported symbol contract is preserved:
`@export_symbol(<kp>_ptr, "<kp>")` etc. with the WGSL global
names, plus `@export_symbol(position_ptr, "position")` for the
decode-position state buffer. Internal var names differ from the
prior hand-written body (TSIR uses the binding name as the var
name; live used `decode_position` as a separate hardcoded var
name), but those are not part of the host plan binding contract.

This is the first ownership transfer outside
`emit_csl_semantic_ops.zig` — the `emit_csl_kv_cache.zig`
module's emitWrite is now a thin TSIR wrapper. `emitRead` remains
hand-maintained; symmetric swap is the natural next slice.

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–18).
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.

Note: the `kv_write` pattern is not in the gemma-3-1b HostPlan
target set so this swap doesn't affect that simulator regen.
Models that DO use kv_write (KV-cache attention variants outside
the gemma-3-1b fused-attention path) will get TSIR-driven CSL.

Loop tally for live ownership transfers from hand-written
emitters to TSIR-driven CSL: **7 kernel bodies** (residual /
residual_prefill / residual_decode + gelu / gelu_prefill /
gelu_decode + kv_write).

## 2026-04-25 (cycle 18) — cerebras-csl shard split (cycles 7–15 + late+16–21 → archive)

Item 6 cycle-18 slice. The live shard hit 1171 lines after cycle 17's
status entry — 29 line headroom against the 1200-line cap. Cycles 7
through 15 plus the earlier late+16 through late+21 history moved to
`archive/2026-04-25-loop-cycles-7-to-15.md` (968 lines). The live
shard now keeps cycles 16 + 17 inline (the live ownership-transfer
milestones) plus the steady-state sections.

Live shard: 1171 → 219 lines after this entry. Archive file: 968
lines.

This is the second split in this loop — the first happened in cycle
3 when the late+18 / late+19 entries pushed the shard over. The
archive file references in the live shard now form a chain:
`2026-04-25-loop-cycles-7-to-15.md` (this split) →
`2026-04-24.md` (cycle 3 split) → older monthly archives.

Validation: no code changes, no test runs needed.

## 2026-04-25 (cycle 17) — Live HostPlan gelu_gated now sourced from TSIR (second ownership transfer)

Item 2 cycle-17 slice. Cycle 16's recipe applied to
`emitGeluPe`. The hand-written gelu body is gone; `compile/gelu/`,
`compile/gelu_prefill/`, and `compile/gelu_decode/` pe_program.csl
files are now generated by TSIR's `emitCslGeluGated` path with
`var_prefix=""` and `chunk_size_default=1024`.

The TSIR `gelu_gated` body gained saturation clamping
(`if (inner < ±15.0) inner = ±15.0;`) to preserve the prior
hand-written numerical behavior. The live wrapper builds a
SemanticFunction with bindings named `gate` / `input` / `output`
(matching the live exports the host plan binding map expects).

Validation:

- `zig build test-wgsl`: 963 / 964 (same single pre-existing
  unrelated `reduction pattern` failure as cycles 9–16). The TSIR
  test for `gelu_gated` now also asserts on the clamping lines.
- `csl_sdk_driver.py simulator-plan.json`: **17 / 17 compile
  succeeded**, all 3 residual variants AND all 3 gelu variants
  succeed.
- Schema gate, CSL + TSIR Python tests: all green.

Loop tally for live ownership transfers from
`emit_csl_semantic_ops.zig` to TSIR-driven CSL: **6 kernel
bodies** (residual / residual_prefill / residual_decode +
gelu / gelu_prefill / gelu_decode). Remaining hand-maintained
in this file: `emitRmsNormPe` (TSIR `rms_norm` body needs a Gemma
`1+w` offset Config knob). And in `emit_csl_kv_cache.zig`:
`emitWrite` and `emitRead` (TSIR `kv_write`/`kv_read` ready).

## 2026-04-25 (cycle 16) — Live HostPlan residual_add now sourced from TSIR (first ownership transfer)

Item 2 cycle-16 slice. The hand-written body of
`emit_csl_semantic_ops.emitResidualPe` is gone. The live HostPlan
residual / residual_prefill / residual_decode pe_program.csl files
are now generated from a TSIR `SemanticFunction` with body op
`residual_add`, dispatched through
`tsir.emit_kernel_body.emitWithConfig(.., .csl, &.{ .var_prefix
= "", .chunk_size_default = 1024 })`. This is the first time a
production HostPlan kernel's CSL comes out of the TSIR contract
emitter rather than a hand-maintained per-kernel body in
`emit_csl_semantic_ops.zig`.

Landed:

- `runtime/zig/src/tsir/emit_kernel_body.zig`: `Config` extended
  with `chunk_size_default: ?u32 = null`. New helper
  `writeCslChunkSizeParam` emits either `param chunk_size: i16;`
  (default null preserves existing behavior) or `param chunk_size:
  i16 = <value>;` when set. Wired through `emitCslResidualAdd` and
  `emitCslGeluGated`.
- `runtime/zig/src/doe_wgsl/emit_csl_semantic_ops.zig`: added
  imports for `tsir/emit_kernel_body.zig` and `tsir/schema.zig`.
  `emitResidualPe`'s 30-line hand-written body replaced with a
  SemanticFunction construction (bindings `a` / `b` / `output`,
  body op `residual_add`) plus a TSIR delegation through an
  `ArrayList(u8)` writer (TSIR helpers' error set is
  Allocator.Error-shaped, so `FixedBufferStream`'s NoSpaceLeft
  doesn't fit). The live wrapper sets
  `chunk_size_default = 1024` to match the prior hand-written
  default — the elementwise layout doesn't forward `chunk_size`
  through `@set_tile_code`, so cslc raises
  `csl_compile_uninitialized_param` without it.

Why a default was needed: the live elementwise `layout.csl` only
forwards `.memcpy_params` to pe_program. Top-level
`--params=chunk_size:N` from the cslc command flows to the layout
module, where it's logged as "externally provided initializer:
chunk_size: unused entry in module instantiation" because the
layout doesn't declare `chunk_size`. The pe_program ran on its
hand-written `param chunk_size: i16 = 1024;` default. Mirroring
that default in the TSIR-emitted output is the minimal-change
swap that preserves cslc's compile path.

Validation evidence:

- `zig build test-wgsl`: 963 / 964 passed. Same single
  pre-existing `reduction pattern` test failure as cycles 9–15.
  The live `host compile source` test that asserts
  `output[idx] = a[idx] + b[idx];` substring on the residual
  pe_program continues to pass — the TSIR-emitted output produces
  this byte-equivalent line.
- `python3 bench/gates/schema_gate.py`: PASS.
- `python3 -m unittest discover -s bench/tests -p "test_csl*.py"`:
  77 passed.
- `python3 -m unittest discover -s bench/tests -p "test_doe_tsir*.py"`:
  22 passed.
- `python3 -m unittest discover -s bench/tests -p "test_int4ple*.py"`:
  40 passed.
- End-to-end: `csl_sdk_driver.py simulator-plan.json` against the
  regenerated artifacts compiles **17 / 17** targets. All three
  residual variants succeed:
    `residual succeeded`,
    `residual_prefill succeeded`,
    `residual_decode succeeded`.

Item 2 hand-maintained surface remaining in
`emit_csl_semantic_ops.zig`:

- `emitGeluPe` (TSIR has the `gelu_gated` body since cycle 10;
  same swap pattern as residual but with `gate` / `input` /
  `output` bindings).
- `emitRmsNormPe` (TSIR has `rms_norm` since the original Phase A
  surface; the live body has the Gemma `1+w` offset which the
  TSIR `rms_norm` body does not yet model — need a Config knob or
  a body-level flag before swapping).
- `emit_csl_kv_cache.emitWrite` and `emitRead` (TSIR has
  `kv_write` / `kv_read` since cycles 11–12; live binding map
  expects `kp` / `vp` / `kc` / `vc` symbol names which differ
  from TSIR's `key_projection` / `value_projection` /
  `key_cache` / `value_cache` — same `binding.name` parameterization
  works).

Each of these is now a tractable next-cycle slice using the same
recipe this cycle established.

**Older 2026-04-25 loop entries (cycles 7 through 15) and the late+16
through late+21 entries from the start of this loop have been archived
to [`archive/2026-04-25-loop-cycles-7-to-15.md`](archive/2026-04-25-loop-cycles-7-to-15.md).
The earlier 2026-04-24 history is at
[`archive/2026-04-24.md`](archive/2026-04-24.md). The live shard keeps
cycles 16 onward inline.**

## Current state

- The forward architecture for replacing classifier/template CSL lowering with
  parity-oracle-first TSIR lowering is documented in
  `docs/tsir-lowering-plan.md`. Phase A compiler surface is landed (schema,
  digests, frontend, planner, reference interpreter, and mechanical skeleton
  emitters for five backends including a TSIR-to-CSL skeleton; see
  [`docs/status/tsir.md`](./tsir.md)). The TSIR-to-CSL emitter has executable
  bodies for `fused_gemv`, `rms_norm`, `gather`, `residual_add`,
  `gelu_gated`, `kv_write`, and `kv_read`; the live CSL lane still routes
  through the classifier/template + `emit_csl_semantic_ops.zig` path for
  those kernels rather than through the TSIR emitter — the wiring switch is
  the open Item-2 work.
- The INT4 PLE CSL lane now applies manifest compile params to the live
  simulator plan and records the result at
  `hostPlanBundle.manifestCompileParamApplication`.
- The fresh simulator driver result on this host compiles **17 of 17**
  compile targets at manifest scale (embed, rmsnorm, rmsnorm_prefill,
  rmsnorm_decode, tiled, rope, attn_head256, residual, residual_prefill,
  residual_decode, gelu, gelu_prefill, gelu_decode, gemv, attn_decode,
  lm_head_gemv, sample). Source of truth:
  `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/trace.json.driver-result.json`.
- Runtime advances through `embed` (chunked dispatch, 6 sublaunches succeed
  in launch[0]) and `rmsnorm_prefill` (launch[1] succeeds end-to-end); was
  in `tiled` q_proj output memcpy_d2h when the 600s wallclock timeout hit.
  Source of truth:
  `bench/out/doppler-reference/gemma-3-1b-doe-csl-hostplan/simulator-evidence.json`.
- The blocker is no longer kernel architecture — the four kernels previously
  flagged (`embed`, `lm_head_gemv_stable`, `attn_head256`, `attn_head512`)
  all compile cleanly and at least `embed` runs cleanly under the BF16
  layernorm-broadcast fix landed late+18 / cycle 7. Open work is now the
  simulator wallclock vs simfabric per-launch cost, the TSIR-to-live-path
  wiring, and the parity-comparison data the simulator-evidence gate
  cannot yet produce.

## Landed infrastructure

- Shared execution contract wiring between Doppler source artifacts, HostPlan,
  transcript receipts, and parity receipts.
- Manifest compile-param projection and apply path for the live transcript
  producer.
- HostPlan executor validator, execution-plan receipt, target-session probe,
  and bootstrap/runtime scaffolding.
- Fail-closed promotion gates for manifest compile params and transcript
  readiness.

## Ground truth

- SDK access is no longer the primary blocker on this host.
- `cslc` runs and produces real linker/compiler diagnostics.
- The missing work is bounded to kernel redesign plus the downstream transcript
  executor path that consumes those kernels.

## Use this shard for

- Cerebras SDK / CSL runtime status
- INT4 PLE compile/runtime blockers
- HostPlan executor status
- Simulator and hardware promotion status
