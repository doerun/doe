# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

## 2026-04-24 (late) — attn_head256/512 streaming KV emitter lands; compile probes green

`emit_csl_attention.zig:emitTiled` rewritten from PE-resident full KV
(`var key: [kv_len * head_dim]f32`, `var val: ...` — 128/256 KiB per PE at
head_dim=256/512) to streaming-KV. New PE-program params: `q_len_per_pe`
(shards q_len across width) and `block_size` (host-streamed tile window,
default 16). K/V storage is now sized as `block_size * head_dim`, so host
rewrites the tile buffers per block and launches `compute` once per tile;
`finalize` normalizes the accumulated output when all tiles have run.
Defaults (`q_len_per_pe=q_len`, `block_size=16`) preserve a usable 1-D
shape when the host has not opted into the streaming contract.

Layout emitter updated in `emit_csl_layout.zig:emitTiledAttentionLayout` to
surface the new params with matching defaults; `kv_len` is removed from
per-tile params (tile window size is `block_size`, iteration count is a
host-side concern).

Feasibility probe at PE budget ~63 KiB
(`bench/out/cslc-attn-streaming-probe/probe-result.json`):

- head_dim=256: `(block_size, q_len_per_pe) = (16, 4)` compiles clean.
  Working region bounded by `block_size ≤ 16` AND
  `(block_size + q_len_per_pe) ≤ ~24`; block_size=32 overflows even at
  q_len_per_pe=2.
- head_dim=512: `(block_size, q_len_per_pe) = (4, 4)` compiles clean.
  block_size=16 overflows at all q_len_per_pe; only block_size≤8 pairs
  fit in budget.

Emitter output verified by direct cslc on the regenerated PE program at
both shapes: `bench/out/cslc-attn-streaming-probe/emittedByDoe.*`. The
unused-entry warnings on `pe_id`/`num_pes` are harmless carry-overs from
the shared layout tile-loop helper; both PEs and host treat them as
metadata.

`zig build` and `zig build test-wgsl` are green. The validator's
`@export_symbol(compute)` structural marker is preserved by keeping the
streaming consumer named `compute`; a second `finalize` export carries
the post-tile normalize.

Not yet this session (remaining WS4-attn closure blockers):

- HostPlan tool must pick `(width, q_len_per_pe, block_size)` from
  `head_dim`, `kv_len`, and available grid, and emit them into the
  simulator-plan `compileParams` for `attn_head256` / `attn_head512`.
  Today it emits `width / head_dim / kv_len / q_len` only.
- `config/csl-operation-graph.schema.json` needs
  `hostIoLayout.attention.kvStreaming` with `blockSize` and
  `qLenPerPe` keys (namespaced so it doesn't collide with the
  `hostIoLayout.embed.chunkedDispatch` keys added by the embed
  workstream).
- Host Python runner (`int4ple_compile_target_sim_runner.py` or its
  attention-specific sibling) needs to loop `ceil(kv_len / block_size)`
  H2D(K_tile) + H2D(V_tile) + launch(compute) dispatches, then one
  launch(finalize), then D2H the output shards across width PEs and
  concatenate by q position.
- KV cache residency upstream of the tile window: the existing
  `kv_write`/`kv_read` emitters still allocate full per-PE KV memory;
  they are orthogonal to this streaming tile design but block full-model
  parity until wired.

Silent-NaN hazard noted in `emit_csl_attention.zig` header: calling
`compute` without first populating the K/V tile buffers reads zeroed
memory and produces numerically wrong (but non-crashing) attention
output. The emitter cannot detect this; host orchestration owns tile
staging.

## 2026-04-24 (afternoon) — embed chunked-dispatch emitter lands; compile probe green

`emit_csl_gather.zig` rewritten from 1-D pre-chunking to 2-D chunked
dispatch. New PE-program params: `pe_x`, `pe_y`, `hidden_per_pe`,
`tokens_per_chunk`. Per-PE buffers now size as
`[tokens_per_chunk]u32`, `[rows_per_pe * hidden_per_pe]f32`,
`[tokens_per_chunk * hidden_per_pe]f32`. Defaults
(`hidden_per_pe=hidden_size`, `tokens_per_chunk=num_tokens`) preserve
the pre-chunking 1-D behavior when `height=1`.

Layout emitter updated in `emit_csl_layout.zig:emitGatherLayout` to
surface the new params with matching defaults.

Direct cslc probe on the fresh emitter output at E2B per-PE shapes
(`width=32,height=8,hidden_size=1536,hidden_per_pe=192,rows_per_pe=16,
num_tokens=32,tokens_per_chunk=16`): **compile succeeded**. Second
probe at `width=256,height=8` (2048 PEs) also succeeded. The original
pre-chunking emitter output still fails with
`integer value 49152 cannot be coerced to type 'i16'` on the same
E2B shape, confirming the fix is a genuine kernel change rather than
a probe-configuration coincidence. Evidence:
`bench/out/cslc-embed-memory-probe/probe-result.json` plus the
pinned `pe_program.csl` and `layout.csl`.

Per-PE footprint at `(hidden_per_pe=192, rows_per_pe=16,
tokens_per_chunk=16)` is `indices 64B + table 12 KiB + output 12 KiB
= ~24 KiB`, well under the ~48 KiB `.data.hi` budget measured at
`.blocked_ut_ival = 0xFC04`.

`zig build` and `zig build test-wgsl` are green. No existing test
exercised `emit_csl_gather.emit` with specific CSL-output expectations,
so the emitter rewrite is source-compatible with the test surface.

Not yet this session (remaining WS4-embed closure blockers — see
`bench/out/cslc-embed-memory-probe/probe-result.json` for the
authoritative list):

- HostPlan tool (`emit_csl_host_compile_source.zig` path) must pick
  `(width, height, hidden_per_pe, tokens_per_chunk)` that covers vocab
  and fits per-PE budget, and emit them into the simulator-plan
  `compileParams` for `embed`. Today it emits `width/height/
  hidden_size/rows_per_pe/num_tokens` only.
- `config/csl-operation-graph.schema.json` needs
  `hostIoLayout.embed.chunkedDispatch` with `tokens_per_chunk` and
  `hidden_shardCount` keys.
- Host Python runner (in `bench/tools/run_doe_csl_int4ple_transcript.py`
  or an embed-specific runner) needs to dispatch
  `ceil(num_tokens / tokens_per_chunk)` chunks and concatenate per-
  column slices across height PEs to reassemble the
  `[num_tokens, hidden_size]f32` output.
- Weight staging in `emit_csl_host_runtime.zig` is currently 1-D
  (`pe_start:pe_end`). It needs a 2-D (row-shard, hidden-shard)
  mapping so each PE receives the slice of `embed_tokens.weight`
  that matches its `(pe_x, pe_y)` position.

Silent-drop hazard noted in `emit_csl_gather.zig` header: until the
host runner implements chunked iteration, calling the emitter with
`tokens_per_chunk < num_tokens` produces only the first chunk of
output and drops the rest. The kernel cannot detect this; it is a
host-orchestration contract.

## 2026-04-24

Direct cslc verification of the 4 manifest-scale blockers (see stderr logs
under `bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-hostplan/
compile/driver-logs/*.cslc.stderr.log`). The i16 array-dimension error on
`embed` and `lm_head_gemv_stable` is the surface symptom; the architectural
blocker for all 4 is per-PE memory. Direct-probe numbers at PE budget
~63 KiB (`.blocked_ut_ival` at 0xFC04):

- `embed` at `num_tokens=32, hidden_size=1536, rows_per_pe=16`:
  output 192 KiB + table 96 KiB per PE. Both exceed budget. 2D array
  syntax fixes the i16 error (confirmed by `/tmp/test-2d-array` probe)
  but does not help the memory overflow. Fix requires 2D grid with
  `hidden_per_pe` sharding + host-chunked dispatch.

- `lm_head_gemv_stable` at `width=197,height=1,out_dim=1331,
  in_dim_per_pe=512, num_blocks_per_row=2`:
  weight 383 KiB per PE (`out_dim * num_blocks_per_row * 144`). Fix
  requires 2D layout with `out_dim_per_pe = ceil(out_dim/height)` so
  weight drops to 4.6 KiB at grid 197×84.

- `attn_head256` / `attn_head512`: .bss 147 KiB / 294 KiB per PE. Full
  KV cache is PE-resident. Fix requires host-streamed K/V tiles instead
  of the current PE-resident `key`/`val` arrays.

Architectural fix plans landed as header-level TODOs in the emitters:
`runtime/zig/src/doe_wgsl/emit_csl_gather.zig`,
`runtime/zig/src/doe_wgsl/emit_csl_fused.zig`,
`runtime/zig/src/doe_wgsl/emit_csl_attention.zig`. Each names touch
points (emitter, layout, classifier, host runner, operation-graph
schema) and the partial-fix hazard.

Reachable-infrastructure finding: SDK container runs locally and reports
real cslc diagnostics; prior classification `csl_compile_container_runtime_blocked`
is stale on this host.

## 2026-04-23

- `docs/doppler-ingest.md` now explicitly frames TSIR as the planned lowering
  layer between Doe WGSL IR and backend artifacts, and narrows HostPlan to the
  runtime orchestration boundary for the CSL lane. This closes one live doc
  drift between the Doppler ingest boundary, the TSIR plan, and the current
  CSL migration story.

## Current state

- The forward architecture for replacing classifier/template CSL lowering with
  parity-oracle-first TSIR lowering is documented in
  `docs/tsir-lowering-plan.md`. Phase A compiler surface is landed (schema,
  digests, frontend, planner, reference interpreter, and mechanical skeleton
  emitters for five backends including a TSIR-to-CSL skeleton; see
  [`docs/status/tsir.md`](./tsir.md)), but the live CSL lane still uses the
  classifier/template route — the TSIR-to-CSL skeleton emits contract text
  rather than executable kernels.
- The INT4 PLE CSL lane now applies manifest compile params to the live
  simulator plan and records the result at
  `hostPlanBundle.manifestCompileParamApplication`.
- The fresh simulator driver result on this host compiles 10 of 14 targets at
  manifest scale and fails 4 with real kernel-level diagnostics:
  - `embed`
  - `lm_head_gemv_stable`
  - `attn_head256`
  - `attn_head512`
- The blocker is kernel architecture, not SDK discovery, tool lookup, or
  receipt plumbing.

## Active blockers

- `embed` still materializes per-PE state that exceeds CSL array-dimension and
  PE-memory limits at manifest scale.
- `lm_head_gemv_stable` still materializes per-PE weight/scratch state that
  exceeds manifest-scale limits.
- `attn_head256` and `attn_head512` still allocate oversized per-PE K/V/Q/O
  backing arrays and scratch.
- The real CSL transcript lane cannot close until those kernels are redesigned
  for bounded per-PE residency.

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
