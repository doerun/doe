# Doe CSL-plan quickstart

## Run the evidence ladder

```
python3 bench/tools/run_csl_plan_sweep.py
```

Exit 0 iff every gate passes. Structured summary at
`bench/out/csl-plan-sweep.json` with `{total, passed, failed, allPassed}`.

## Read next

- `docs/csl-evidence-status.md` — full artifact-by-artifact map.
- `docs/csl-architecture.md` — the abstraction stack Doe uses to
  retarget Cerebras CSL.

## What the sweep verifies (top-to-bottom)

1. **Cross-backend kernel matrix** at `bench/out/cross-backend-matrix/`.
   Every tracked WGSL kernel has Vulkan SPIR-V, Metal MSL, D3D12
   HLSL+DXIL, and — when the Cerebras SDK is available — CSL runtime
   artifacts.
2. **Per-kernel CSL runtime parity**. Each runtime-ready fixture in
   `config/csl-runtime-fixtures.json` has a governed-lane simulator
   receipt under `bench/out/dual-compile-evidence/governed-lane-sdk-handoff/`.
3. **Full-grid cslc compile** proven for E2B (149×117 = 17,433 PEs) and
   31B (246×236 = 58,056 PEs) via 2D layouts —
   `bench/out/cslc-grid-probe/grid-probe-aggregate.json`.
4. **Model-level runtime receipts** for E2B and 31B in
   `bench/out/{e2b,31b}-full-graph/`, binding manifest + host-plan +
   memory-plan + runtime-config + simulator-plan + chain-parity
   evidence into one artifact per model.
5. **Stream-graph + execution plan + dry-run trace** per model, plus
   predicted-trace diff and lookahead-sensitivity sweep tools for
   A/B comparison before the SdkLayout streaming runtime lands.
6. **ELF fingerprints** at `bench/out/csl-kernel-fingerprints.json`
   catch silent emitter drift — any change to the WGSL→CSL path that
   still passes schemas shows up as a hash delta in review.
7. **Kernel-chain parity** — every Gemma host-plan kernel pattern
   appears in at least one 2-, 3-, or 4-step chain with bit-exact or
   bit-close numerical parity against a numpy reference.
8. **Hardware-endpoint propagation** — driver's `--cmaddr` wiring
   verified without needing real hardware.

## What the sweep does NOT prove

- Actual model execution on hardware (gated on SdkLayout streaming
  executor + CS system endpoint access).
- Logit-checkpoint parity through a full Gemma forward pass.
- Per-kernel full-grid compile sweep at E2B/31B scale (probe covers
  grid size; each kernel's per-PE body at real shape params is a
  separate multi-hour sweep).

Every outstanding blocker is named explicitly in the E2B / 31B
runtime receipts under `executionBlocker`.
