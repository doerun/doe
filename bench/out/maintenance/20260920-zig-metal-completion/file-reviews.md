# File examinations

## Completion owner

`src/backend/metal/metal_completion.zig`: verified within file scope.

Read the full owner and tests. The runtime owns its allocator and pending array;
reservation precedes commit and transfer of the native reference. Retirement
waits and reads each result before release. It drains the whole array even after
failure, preserves the first native error code, and does not clear failure on a
successful successor. `check` is the fallible observation point after cleanup.
Deinitialization drains before releasing array capacity. Tests cover reservation
failure, ordered waits/releases, success, absent error detail and retained first
failure. No extra ownership is claimed for native resource handles referenced by
the command; their runtime owner must outlive retirement. No general ownership
checking or physical Metal qualification is implied.

## Queue operations

`src/backend/metal/metal_runtime_queue_ops.zig`: needs changes.

Read all encoder finalization, submission, pool recycling, flush, deferred
barrier and prewarm paths. The completion owner replaces last-handle dropping.
Allocation failure leaves encoders and commands unchanged. Flush commits current
work before waiting earlier submissions, then drains resources before exposing
the preserved error. Deferred barriers reserve ownership before creating and
committing their fence. Pool return failures retain the existing release path.
Host tests exercise a failed completion through the real flush implementation.

Resolved: loss of predecessor errors, success inferred from void waits and
event-only retirement dependent on a possibly missing signal. Remaining: explicit
queue wait-mode/timeout behavior and native encoder error reporting. Native waits
can still block without a timeout. These are separate obligations, not resolved
by retaining the command buffers.

## Dispatch runtime

`src/backend/metal/metal_dispatch_runtime.zig`: needs changes.

Read direct/indirect dispatch, pipeline lookup, argument allocation and writes,
submission preparation, deferred and synchronous finalization. Indirect argument
reuse still flushes earlier users. Deferred completion capacity is reserved
before acquisition/encoding and transfer. Synchronous completion consumes and
releases the command even when status is failed. The first failed runtime rejects
new dispatches. No additional descriptor interpreter or shader behavior appears.

Resolved: dropping the previous deferred handle and ignoring failed immediate
completion. Remaining: the bridge's void encoding methods cannot report all
encoding failures; repeated indirect execution and failure handling still require
physical Metal verification. Existing dispatch-count semantics are unchanged.

## Async map operation

`src/backend/metal/metal_async_runtime.zig`: verified within file scope.

Re-examined the whole size-validation, flush, allocation, borrowed mapping and
release path after its completion dependency changed. Invalid size fails before
access; native acquisition/mapping failures remain errors; defer releases the
temporary buffer. The operation rejects a previously failed runtime before any
new allocation and flushes retained submissions before observing bytes. This
command maps its own temporary allocation by contract; it does not establish
ordinary WebGPU callback semantics. Tests cover device size limits and the
runtime integration failure path.

## Surface port

`src/backend/ports/surface.zig`: needs changes in bound implementations.

Read the whole port with prepared surface operations, application routing,
provider adapter/bundle and relevant Metal surface lifecycle paths. Context and
vtable are borrowed from the provider; inputs are borrowed for the call. Direct
forwarding preserves reports/errors and performs no allocation or backend
selection. Documentation distinguishes successful submission/presentation from
display visibility. The Metal presentation path now waits prior command work
within its timing scope and propagates checked completion after drawable cleanup.

Remaining: Metal configure/layer replacement can leave flags describing released
state after failure, and capability querying creates an entry without querying
native capabilities. These are existing implementation findings retained from
the preceding Metal examination. Supporting edits and passing composition tests
do not grant the port an end-to-end verified lifecycle.
