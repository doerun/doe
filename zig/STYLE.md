# Fawn Zig Style Guide

This guide is the Zig style contract for `fawn/zig`.

## Core principles

- Prefer explicit typed contracts over inferred behavior.
- Keep runtime decisions deterministic and traceable.
- Fail fast on invalid/unsupported inputs with actionable errors.
- Keep hot-path execution allocation-light after initialization.

## Repository conventions

- Put shared command/profile contracts in `model.zig`.
- Put quirk parsing in `quirk_json.zig` and command parsing in `command_json.zig`.
- Keep deterministic selection logic in `runtime.zig`.
- Keep execution orchestration in `execution.zig`.
- Keep trace/replay behavior in `trace.zig` and `replay.zig`.
- Keep WebGPU proc/table contracts in `wgpu_types.zig` and loader glue in `wgpu_loader.zig`.
- Add new API clusters as feature-scoped `wgpu_*_procs.zig` modules.

## Formatting

- Run `zig fmt` for every changed Zig file.
- Keep imports explicit (`std` first, then local modules).
- Prefer small feature-scoped modules over catch-all utility files.

## Naming

- Types and enums: `PascalCase`
- Functions, variables, fields: `snake_case`
- Compile-time constants: `UPPER_SNAKE_CASE`
- File names: `snake_case.zig`

## Control flow

- Prefer `switch` on enums over long `if` ladders.
- Use early returns for invalid states.
- Keep fallback behavior explicit and auditable.
- Do not introduce silent capability switching.

## Errors and diagnostics

- Return explicit error unions (`!T`) for recoverable failures.
- Keep unsupported behavior explicit (`unsupported` taxonomy), never silent no-op.
- Route runtime observability through trace/trace-meta contracts.
- Avoid unconditional debug stderr printing in runtime paths.

## Memory

- Use explicit allocator ownership.
- Scope temporary allocations with `defer` cleanup.
- Keep long-lived caches explicit in owning structs.

## Determinism and trace

- Identical inputs/config must produce stable decision and trace sequences.
- Preserve hash-chain invariants in trace rows/meta.
- Include enough metadata to reproduce selection and execution outcomes.

## Testing and checks

- Run `zig build test` for affected runtime modules.
- Verify replay/trace gate compatibility for runtime-visible changes.
- For WebGPU API-surface changes, update config coverage + benchmark contracts in the same change.
