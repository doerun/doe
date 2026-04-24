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

## 2026-04-24

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
