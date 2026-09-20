# Metal command wait policy

The command-oriented Metal runtime uses
[`config/metal-command-wait-policy.json`](../config/metal-command-wait-policy.json)
for operational retirement. This policy does not configure the ordinary native
WebGPU callback path, Vulkan, D3D12, or WebGPU FFI waits. It changes no accepted
release package until a rebuilt package passes its qualification.

## Build contract

The [schema](../config/metal-command-wait-policy.schema.json) owns the serialized
fields. The [parser](../runtime/zig/src/backend/metal/metal_wait_policy.zig)
rejects missing, unknown, coerced, unsupported-version and nonpositive values.
The build reads it once and supplies immutable timeout and polling values to
every runtime build tier. No environment variable or invocation fallback
overrides these values.

`timeoutNs` is one elapsed-time budget for all submitted references in a
retirement call. `pollIntervalNs` bounds the requested sleep between native
status observations; the final sleep is capped to the remaining budget. OS
scheduling and the time to inspect the batch can exceed that budget. This is
bounded waiting, not a hard real-time guarantee.

## Completion and ownership

[`Completion`](../runtime/zig/src/backend/metal/metal_completion.zig) queries each
command buffer's native status. Only successful or failed terminal status
authorizes releasing that command reference. A terminal failure records the
first observed native error code, including a missing code, and remains an
error after later successful submissions retire.

`MetalWaitTimeout` retains pending commands and prevents new submission through
the completion owner. An explicit queue flush can retry retirement with a fresh
budget. It does not resubmit work. Deferred releases and pooled uploads remain
owned until that flush establishes terminal completion for all pending work.
`MetalCompletionUnknown` and `MetalWaitClockUnavailable` also retain ownership;
neither is interpreted as successful completion or elapsed time from zero.
Failed waits produce no valid output or timestamp result.

Destruction is a separate blocking drain. It waits for terminal completion before
destroying resource maps and does not promise a deadline or cancellation. If
native completion remains unknown, it retains ownership and sleeps between
attempts. Reentrant destruction during retirement is not supported; a safe
lifetime-transfer contract for that case remains open. Do not use operational
timeout as permission to free the runtime or referenced resources yourself.

## Migration and evidence

Policy version 1 replaces unbounded operational `waitUntilCompleted` with native
status polling and a monotonic elapsed clock. Existing flush, dispatch, mapping
and presentation error unions can now report the explicit wait errors above.
The old blocking bridge entrypoint remains available for destruction and ABI
compatibility. The additive polling entrypoint distinguishes submitted/pending
from terminal success, terminal failure and unknown state.

No serialized execution-result field changes. Failed waits retain error status;
they cannot become successful execution receipts. Existing WebGPU FFI timeout
options keep their original scope. The separate `QueueWaitMode` mapping for
native Metal remains an open review item; this policy does not establish
`wait-any` implementation.

Polling changes CPU work and host completion-observation latency. No performance
benefit follows from this repair. Compare physical Metal application latency,
CPU consumption and tails before qualifying a rebuilt package.

Host failure-injection tests and the event-blocked physical fixture are retained
in the [checkpoint](../bench/out/maintenance/20260920-metal-bounded-wait/README.md).
The blocking process gates in [process.md](process.md) remain authoritative;
Linux host acceptance does not establish Apple SDK or Metal hardware support.
