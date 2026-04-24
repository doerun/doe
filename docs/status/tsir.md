# Doe status: TSIR

This is a live topical status shard for the Tiled Spatial IR (TSIR) work
defined in [`docs/tsir-lowering-plan.md`](../tsir-lowering-plan.md) and
sequenced by [`docs/loop-protocol.md`](../loop-protocol.md).

- Add new TSIR entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under [`archive/`](archive/).
- Parity receipts themselves land under `reports/parity/` and are bound
  into Doppler manifests at `integrityExtensions.lowerings[]`; this shard
  is narrative status, not the receipt surface.

This shard exists because `compiler-and-webgpu.md` exceeded its 1200-line
cap once the TSIR Phase A wedges started landing. Historical TSIR entries
remain in `compiler-and-webgpu.md` until a deliberate migration sweep
moves them here; new TSIR entries go here going forward.

## 2026-04-24

- Plan doc refresh: `docs/tsir-lowering-plan.md` "Current scaffold
  already in tree" section was drafted before Phase A landed and
  didn't mention `family_hint.zig`, the five backend skeleton
  emitters (`emit_csl`, `emit_webgpu`, `emit_msl`, `emit_dxil`,
  `emit_spir_v`) plus `emit_text_skeleton`, the target descriptors
  under `runtime/zig/src/targets/`, the four JSON schemas under
  `config/`, the bench tooling (parity CLI, manifest-lowering
  builder, nightly canary), the bootstrap manifest fixtures, or the
  bootstrap test fixture set. Future Loop 2 readers were getting a
  stale starting picture. Rewrote the section to describe what
  exists in shape (not counts) with artifact-path references per
  CLAUDE.md documentation-drift discipline. Also refreshed the
  "missing work" paragraph to name executable kernel bodies, parity
  CLI subprocess harness, AOT convert-time cache, Loop 3 per-family
  parity receipts, manifest binding into Doppler RDRR, and
  Phase B attention + sollya. Strategy-leak gate verified PASS
  post-edit. Cites `docs/tsir-lowering-plan.md` §Current scaffold
  and `docs/loop-protocol.md` Loop 2 protocol (doc-only
  in-step increment).
- Private-strategy leak gate: fixed two cross-repo path references to
  the upstream planning repo in `docs/doppler-ingest.md:11` that were
  failing `bench/gates/doe_private_strategy_leak_gate.py` (a hard
  blocking gate per CLAUDE.md). The line had a markdown link pointing
  at an upstream planning repo path. Replaced with Doe-local prose
  describing only the Doe-local side of the Doppler-Doe boundary;
  motivation and composition context are intentionally not named.
  Gate now passes. Not a TSIR wedge strictly, but logged here because
  the status shard has been the main Loop 2 activity surface today
  and the leak was discovered while confirming no TSIR doc drift
  during this tick's
  scope search.
- TSIR Loop 2 — cross-backend emitter digest distinctness lock: new
  test "tsir emitter code digests are pairwise distinct across all five
  backends" in `runtime/zig/tests/wgsl/tsir_emit_backend_skeleton_test.zig`.
  Computes `emitterCodeDigest()` for each of the five backend emitters
  (`emit_csl`, `emit_webgpu`, `emit_msl`, `emit_dxil`, `emit_spir_v`)
  and asserts all pairs are distinct. The manifest-lowering contract
  binds `(kernelRef, backend)` pairs to an emitter digest so replay
  identifies which backend produced an artifact; silent digest
  collision (e.g. a refactor leaving two emitter sources identical)
  would make that binding ambiguous and attribute artifacts to the
  wrong backend. Per-emitter digest formation (emitter source +
  shared `emit_text_skeleton.zig`) is still covered by the existing
  "expose source-backed code digests" test. `zig build test-wgsl`:
  933/933 pass. Cites `docs/tsir-lowering-plan.md` Step 7 (mechanical
  emitter identity) and Step 10 (manifest binding); `docs/loop-protocol.md`
  Loop 2 protocol.
- TSIR Loop 2 — nightly parity canary increment:
  `bench/gates/nightly_tsir_parity_canary.py` now runs all six bootstrap
  manifest lowering fixtures through the parity CLI, validates the emitted v2
  receipts, checks that each receipt carries the expected lowering identity,
  and writes an advisory JSON report. The canary accepts today's honest
  `not_implemented` / `deferred` statuses and fails only on fixture coverage,
  schema, identity, or explicit parity-fail regressions; it does not promote
  the stub backend lanes to a green claim.
- TSIR Loop 2 — shard created by splitting `compiler-and-webgpu.md` on
  subdomain after it exceeded the 1200-line cap. Historical TSIR
  entries remain in `compiler-and-webgpu.md` until a deliberate
  migration sweep; new TSIR entries route here. Updated
  `docs/status.md` front door to list the new shard and left a cap
  notice at the top of `compiler-and-webgpu.md` pointing new TSIR
  traffic here. Cites `docs/loop-protocol.md` Loop 2 protocol
  (no-code subdomain-split increment). No runtime, test, or contract
  change.

## Scope

Use this shard for:

- TSIR schema + digest contract changes
- TSIR reference interpreter (oracle) coverage
- TSIR frontend lowering (WGSL IR → TSIR semantic)
- TSIR planner (residency, tile factors, PE grid, realization)
- TSIR mechanical backend emitters (CSL, WebGPU, MSL, HLSL/DXIL, SPIR-V)
- TSIR manifest-lowering identity contract + fixtures
- Loop 2 stop-until-green iteration status
- Loop 3 per-kernel-family parity closure status

Use `compiler-and-webgpu.md` for:

- Doe WGSL shader compiler (non-TSIR paths: Metal, Vulkan, D3D12)
- WebGPU runtime behavior outside TSIR lowering
- Robustness / validator / conformance work
