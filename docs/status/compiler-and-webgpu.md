# Doe status: compiler and WebGPU

This is a live topical status shard.

- Add new entries at the top.
- Keep this file under 1200 lines.
- Split by subdomain before it exceeds the cap.
- Dated history lives under `docs/status/archive/`.

**Scope notice:** 2026-04-24 TSIR entries moved to
[`tsir.md`](./tsir.md); 2026-04-23 TSIR Step 4 history moved to
[`archive/2026-04.md`](archive/2026-04.md). **New TSIR entries go in
[`tsir.md`](./tsir.md).** This shard stays focused on non-TSIR
compiler work (shader compiler non-TSIR paths, WebGPU runtime,
robustness).

## Current state

- TSIR (Tiled Spatial IR) current state and contracts live in
  [`tsir.md`](./tsir.md); that shard owns schema, digests, frontend,
  planner, reference interpreter, backend skeleton emitters, parity
  CLI, manifest fixtures, and canary. Do not duplicate those bullets
  here.
- Postfix `++` / `--` statements are now supported in the WGSL compiler
  (tokens, lexer, AST `inc_stmt`/`dec_stmt`, parser, sema, IR lowering).
  `ir_transform` / `emit_spirv` errors are surfaced with specific kinds
  instead of silently becoming empty `OOM` strings, and the failing-kernel
  log carries the first 120 chars of the WGSL so failures are identifiable
  without re-running.
- The Doe WebGPU shared-contract lane has real transcript and parity plumbing,
  but it is not green end to end.
- The current blocker is in `runtime/zig/src/doe_wgsl/`, not Vulkan feature
  discovery.
- Vulkan-side capability bring-up has improved: the adapter now advertises
  `shader-f16` correctly, and the shared-contract runner can force subgroup
  removal with `DOE_DISABLE_SUBGROUPS=1`.

## Active blockers

- WGSL semantic-analysis and/or SPIR-V emission gaps still block some real
  Doppler kernels in the shared-contract lane.
- Mixed subgroup and non-subgroup entrypoints remain a real compiler surface.
- Real KV/cache evidence is still not emitted in the WebGPU transcript path.

## Landed infrastructure

- Shared-contract WebGPU transcript receipt
- Pairwise parity binder
- Generic transcript parity report surface
- Vulkan API-version and feature-capability fixes that expose `shader-f16`
  correctly
- Shared-contract runner defaults that force the declared subgroup workaround
  instead of silently relying on unsupported subgroup lowering

## Ground truth

- The WebGPU lane is blocked by WGSL compiler work, not by contract design.
- The current failures are concrete compiler/runtime gaps with named files and
  reproducible signatures.

## Use this shard for

- `doe_wgsl` compiler status
- WebGPU shared-contract transcript status
- WebGPU parity blockers
- Vulkan capability / adapter issues that affect the WebGPU lane
