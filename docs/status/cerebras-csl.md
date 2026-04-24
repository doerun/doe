# Doe status: Cerebras and CSL

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

## 2026-04-23

- `docs/doppler-ingest.md` now explicitly frames TSIR as the planned lowering
  layer between Doe WGSL IR and backend artifacts, and narrows HostPlan to the
  runtime orchestration boundary for the CSL lane. This closes one live doc
  drift between the Doppler ingest boundary, the TSIR plan, and the current
  CSL migration story.

## Current state

- The forward architecture for replacing classifier/template CSL lowering with
  parity-oracle-first TSIR lowering is now documented in
  `docs/tsir-lowering-plan.md`. The TSIR scaffold is in tree, but the live CSL
  lane still uses the existing classifier/template route.
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
