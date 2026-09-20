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
every runtime build tier. The timeout is the default for each completion owner.
Explicit queue-port `setWaitTimeoutNs` calls override that owner only; there is no environment
override or fallback. Polling intervals remain build-selected.

The effective timeout is one elapsed-time budget for all submitted references in a
retirement call. `pollIntervalNs` bounds the requested sleep between native
status observations; the final sleep is capped to the remaining budget. OS
scheduling and the time to inspect the batch can exceed that budget. This is
bounded waiting, not a hard real-time guarantee.

## Queue controls

The existing queue port's `setWaitMode` now reaches the Metal completion owner.
`process_events` observes native status with bounded sleeps; it does not pump
an application event loop. `wait_any` waits on a private command notification
and then observes native status. It is a command-provider treatment, not an
implementation of public WebGPU waitAny or arbitrary JavaScript callbacks.
Both modes consume one budget across the retirement pass. A barrier override
selects the mode for that flush and does not add another retirement pass.

`setWaitTimeoutNs` accepts a nonblocking observation at zero, finite durations,
and an explicit indefinite wait at `maxInt(u64)`. Zero and indefinite waits do
not require a clock. These existing typed call inputs do not broaden the JSON
build policy: its default remains positive and finite. Callers serialize policy
changes, command preparation, submission, and retirement on the runtime owner.

A private notification is registered before commit even when polling is selected,
so switching mode after submission remains possible. The command and completion
block retain the semaphore; the block captures neither Zig stack data nor the
completion owner. Registration failure reports `MetalWaitPreparationFailed`
without committing or taking the caller's command reference. Unsupported-host
stubs reject registration rather than synthesizing a notification.

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
they cannot become successful execution receipts. The command-provider queue
port now honors timeout and mode inputs on native Metal; its historically FFI-named internal callback no longer discards timeout.
WebGPU ABI-backed providers retain their own behavior. No public descriptor,
execution-result field, or serialized policy field changes; the schema keeps
its existing positive finite build defaults. This is an explicit semantic
extension of previously ignored Metal call inputs, not a change to old receipts.

Polling changes CPU work and host completion-observation latency. No performance
benefit follows from this repair. Compare physical Metal application latency,
CPU consumption and tails before qualifying a rebuilt package.

Host failure-injection tests and the event-blocked physical fixture are retained
in the [checkpoint](../bench/out/maintenance/20260920-metal-bounded-wait/README.md).
The blocking process gates in [process.md](process.md) remain authoritative;
Linux host acceptance does not establish Apple SDK or Metal hardware support.

Notification integration and host verification are retained in the
[follow-up checkpoint](../bench/out/maintenance/20260920-metal-notification/final-checkpoint.md).
Apple requires completion handlers to be registered
[before commit](https://developer.apple.com/documentation/metal/mtlcommandbuffer/addcompletedhandler%28_%3A%29).
A [semaphore wakeup](https://developer.apple.com/documentation/dispatch/dispatch_semaphore_wait)
is not evidence of successful shader execution; native status still owns retirement.
