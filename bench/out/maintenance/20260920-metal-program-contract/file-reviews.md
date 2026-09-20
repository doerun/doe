# Metal owner continuations

These are complete file examinations with unresolved findings, not directory or
subsystem completion. Compiler, bridge, surface, cleanup and fixture edits are
supporting changes and receive no automatic review credit.

## `metal_completion.zig`

Responsibility: allocator-backed ownership of submitted native references and the
first native failure code. Reserve is fallible before commit; retain transfers a
reference after commit. Retirement releases only terminal references and compacts
unknown references in place. The owner disallows mutation through reentrant
reserve/retire calls during native waiting. The bridge is the unsafe boundary;
the owner does not reinterpret absence of error detail as successful execution.

Resolved: an unknown native status previously collapsed into terminal failure;
it could therefore authorize resource destruction. Unknown now retains ownership
and remains observable. Mixed outcomes preserve the first terminal failure while
remaining unknown commands stay retained. Tests exercise those outcomes,
allocation-before-transfer failure and reentrant waiting.

Open: `deinit` cannot return an error and waits until every reference is terminal.
There is no supported timeout/cancellation outcome that transfers still-live
ownership. Permanent unknown status or reentrant destruction can block teardown.
Implement the wait/lifetime contract with the runtime owner; do not free live
references to make destruction return. Ordinary-native callbacks are separate.

## `metal_runtime_resources.zig`

Responsibility: acquire/cache command pipelines, compute buffers, render targets
and indirect command buffers. Pipeline records own copied source bytes and native
library/pipeline references; keys are separately allocator-owned. Returned info
borrows native identity and copies interface metadata. The caller runtime owns
maps, allocator, queue and eventual release. Allocation/acquisition failures use
rollback; replacement waits for prior work before releasing the old owner.

Resolved: a normalized cache key previously bypassed source loading, preferred a
different-language sibling and allowed another translator after failure. Source
resolution, selected entrypoint, fixed compiler options and compiler identity now
determine creation and cache reuse. Workgroup/binding metadata comes from the same
analysis. Raw MSL cannot masquerade as a reflected command kernel. Existing buffer
extent checks, publication rollback and render/ICB replacement ownership remain.

Open: the number/total bytes of retained kernel pipelines and compute buffers
remain unbounded by an explicit capacity/full policy. Native library/pipeline
failure returns its typed error but drops bridge diagnostic text. Archive
compile-or-serve and telemetry need examination with `metal_pipeline_cache.zig`.
The helper's broad `anytype` runtime dependency remains; a named owner should
replace it when extracting the actual acquisition/cache responsibility. Do not
add allocation or forwarding layers solely to change the signature.

## `metal_kernel_dispatch.zig`

Responsibility: validate a command kernel's reflected buffer interface, acquire
buffer extents, encode warmup/timed/streaming work and report actual completion
through the queue owner. Binding planning is pure and checks every input before
buffer acquisition. Group-slot conversion is shared with the MSL emitter. Buffer
offsets and visible sizes survive the bridge; alias allocation uses maximum
extent. Timestamp resolution follows successful terminal completion.

Resolved: nonbuffer and out-of-range bindings were silently skipped; group,
offset and reflected minimum extent were absent. Invalid layouts now fail before
buffer acquisition/encoding. The checked encoder returns native rejection as an
error. Command references reserve before submission and unknown completion never
becomes valid timing output. Host tests cover rejection, alias order, ranges,
reserved/duplicate slots, groups and missing bindings.

Open: Apple SDK compilation and physical readback of the new checked encoder are
unavailable on this host. Pipeline acquisition still precedes complete command
binding validation because cache info is the metadata provider; split analyzed
program admission from native creation if this boundary must reject all invalid
layouts before any GPU acquisition. Streaming rollover uses a local policy
constant shared in meaning with other encoders; its policy owner still needs the
existing queue review. The legacy direct/indirect dispatch path is a different
consumer and is not qualified by this file's checked bridge.

## `metal_runtime_queue_ops.zig`

Responsibility: finalize streaming encoders, commit reserved references, retire
submitted work and then recycle uploads/deferred resources. Runtime maps and
pools remain externally owned; this module determines when their retained data
can be reused. Unknown retirement exits before any recycling. Terminal failure
drains resources, then remains a returned error. Deferred barriers report
submission acceptance without inventing completion.

Resolved: current command references are transferred into the completion owner
before waiting and cleared from streaming state, so a failed/interrupted wait
does not leave a second owner. Unknown completion does not reach pool recycling,
deferred release, timestamp success or surface destruction. Prior failure stays
observable across later submissions.

Open: `barrier` still ignores the requested wait mode, and checked native waiting
has no bounded timeout policy. Unsupported wait choices must be rejected or
implemented under the existing declared contract. Upload/deferred collections
need an explicit aggregate retention budget. Broad structural runtime dependency
remains until queue services have a named owner interface. Physical native failure
and concurrent-device execution are not established by the host probes.
