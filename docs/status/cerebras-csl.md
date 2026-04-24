# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

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
