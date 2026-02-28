# Doe Zig Style Guide

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

## File size

- 777 lines max per source file in `zig/src/`.
- Shard before exceeding this limit, not after.
- Split by cohesive functionality (e.g. `pipeline_cache.zig`), not by type (e.g. `helpers.zig`).
- Keep related code together; splitting must not scatter a single concern.

## Formatting

- Run `zig fmt` on every changed file before commit.
- `zig fmt` compliance is a blocking check; do not commit unformatted Zig.

## Imports

- `std` and `builtin` first.
- Then local modules, with `model.zig` before domain-specific imports.
- Group domain imports by subsystem (e.g. backend modules together).

```zig
const std = @import("std");
const builtin = @import("builtin");
const model = @import("model.zig");
const types = @import("wgpu_types.zig");
const webgpu = @import("webgpu_ffi.zig");
const backend_runtime = @import("backend/backend_runtime.zig");
const backend_ids = @import("backend/backend_ids.zig");
```

- Prefer small feature-scoped modules over catch-all utility files.

## Naming

- Types and enums: `PascalCase`
- Functions, variables, fields: `snake_case`
- Compile-time constants: `UPPER_SNAKE_CASE`
- File names: `snake_case.zig`

## Constants and magic numbers

- No bare numeric literals in runtime code.
- Use named `UPPER_SNAKE_CASE` comptime constants or config values.
- Place constants at file top, after imports.
- Domain-shared constants belong in `model.zig` or `wgpu_types.zig`.
- Module-specific constants stay in the module that uses them.
- If a value appears in more than one file, it must have a single source of truth.

```zig
const QUEUE_SYNC_RETRY_LIMIT: u32 = 3;
const QUEUE_SYNC_RETRY_BACKOFF_NS: u64 = 1_000_000;
pub const TIMESTAMP_BUFFER_SIZE: u64 = 16;
```

## Control flow

- Prefer `switch` on enums over long `if` ladders.
- Use early returns for invalid states.
- Keep fallback behavior explicit and auditable.
- Do not introduce silent capability switching.

## Errors and diagnostics

- Return explicit error unions (`!T`) for recoverable failures.
- Keep unsupported behavior explicit (`unsupported` taxonomy), never silent no-op.
- Include actionable context: what was expected, what was received.
- Route runtime observability through trace/trace-meta contracts.
- No ad-hoc `std.debug.print` in runtime paths; use structured trace output.
- Guarded debug output (e.g. `DOE_WGPU_TIMESTAMP_DEBUG`) is acceptable for investigation aids, not for production paths.

## Comments

- Comments explain why, not what.
- Do not add comments that restate the code.
- Use `///` doc comments for public function/type intent.
- Inline comments are for preconditions, control-flow rationale, or non-obvious constraints.
- Do not add TODO/FIXME inline; track follow-ups in `fawn/status.md`.

## Memory

- Use explicit allocator ownership.
- Scope temporary allocations with `defer` cleanup.
- Keep long-lived caches explicit in owning structs.

## FFI and C interop

- Define C function pointer types as `pub const Fn<Name> = *const fn (...) callconv(.c) <ReturnType>`.
- Collect function pointers into a `Procs` struct in `wgpu_types.zig`.
- Required procs are non-optional fields. Optional/conditional procs use `?` wrapper.
- Load required procs with `loadProc()` (error on missing symbol). Load optional procs with `loadOptionalProc()` (returns null on missing symbol).
- Check optional proc availability before call: `if (procs.someFn) |fn| fn(...) else return error.Unsupported`.
- C callbacks use `callconv(.c)` and cast `?*anyopaque` userdata to known state structs via `@ptrCast(@alignCast(...))`.
- Suppress unused callback parameters with `_ = param;`.

```zig
// Type alias
pub const FnWgpuCreateInstance = *const fn (?*anyopaque) callconv(.c) WGPUInstance;

// Proc struct
pub const Procs = struct {
    wgpuCreateInstance: FnWgpuCreateInstance,           // required
    wgpuDeviceHasFeature: ?FnWgpuDeviceHasFeature,     // optional
};

// Callback
fn onQueueWorkDone(status: types.WGPUQueueWorkDoneStatus, userdata1: ?*anyopaque, _: ?*anyopaque) callconv(.c) void {
    const state = @as(*types.QueueSubmitState, @ptrCast(@alignCast(userdata1.?)));
    state.done = true;
    _ = status;
}
```

## Determinism and trace

- Identical inputs/config must produce stable decision and trace sequences.
- Preserve hash-chain invariants in trace rows/meta.
- Include enough metadata to reproduce selection and execution outcomes.

## Testing

- Tests are inline `test` blocks in the source file they cover.
- Test names are descriptive behavior strings: `test "vendor comparison ignores case"`.
- Use `std.testing.expect` and `std.testing.expectEqual` for assertions.
- Run `zig build test` for affected runtime modules.
- Verify replay/trace gate compatibility for runtime-visible changes.
- For WebGPU API-surface changes, update config coverage + benchmark contracts in the same change.
