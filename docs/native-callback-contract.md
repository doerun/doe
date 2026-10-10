# Native callback contract migration

[`config/native-callback-contract.json`](../config/native-callback-contract.json)
introduces a versioned bounded Vulkan callback contract for the pinned ONNX consumer.
[`native-callback-evidence.schema.json`](../config/native-callback-evidence.schema.json)
registers its retained source, process, application and custody manifest. Existing
WebGPU C structures and mode/status encodings stay ABI compatible.

The native instance owns unique future identities and pending callback obligations.
RequestAdapter, RequestDevice, async pipelines, mapping, error scopes, queue completion
and compilation information publish real readiness to that owner. WaitAnyOnly delivers
inside a matching wait; AllowProcessEvents also permits the owning instance pump;
AllowSpontaneous permits producer/worker delivery. Foreign callbacks execute outside
the owner mutex. A reentrant event registered by a pump belongs to the next pump.
Repeated waits observe settled issued identities without retaining tombstones.
Unknown identities return an explicit wait error. Identity exhaustion fails explicitly.

Queued replies own callback payloads and resource leases until the callback returns.
Pipeline descriptor snapshots retain shader/layout/device ownership; the request also
retains its instance through settlement. Cleanup releases producer and request resource
leases before removing the completion record. WaitAny/ProcessEvents retain the instance
for their call, allowing callbacks to release caller-held handles without invalidating
ongoing delivery. Callback userdata remains caller-owned through delivery.

Buffer objects now distinguish pending mapping, mapped extent and mapping generation.
Pending mapping blocks mapped-range access and GPU admission. Unmap/destruction
invalidates an undelivered success, producing Aborted (4); invalid mapping produces
Error (3), including validation-scope capture. Destroyed buffers retain their device
reference until the last object/callback lease is released. Backend completion is still
required before physical storage retirement. Callback deferral does not imply
asynchronous GPU execution. Empty scope popping now returns Error with NoError and
an owned diagnostic; it does not fabricate successful validation.

Mode zero remains an immediate flat-native compatibility convention, not a standard
WebGPU mode promise. The global work-done registry remains only for no-instance legacy
calls; standard instance requests route through their owner. Metal spontaneous queue
completion retains worker delivery; Vulkan is the physical qualification here.
Unsupported callback storage/modes without a representable failure remain explicit
fail-fast boundaries. Bridge calls without qualified recoverable contracts remain open.

This migration qualifies the [named tested paths](../reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-callbacks/README.md).
It excludes instance abandonment, descriptor-based device-loss callbacks, DeviceDestroy
semantics, real device loss and interruption of submitted GPU work. No timing policy,
performance advantage, compiler transformation, backend expansion or browser replacement
is promoted. Earlier reports keep their exact source/binary bindings; replay their
original verifiers against their retained source base instead of substituting current code.

Synchronous Node mapping and flattened map/copy/unmap adapters must process the
owning instance until the requested callback is delivered. They retain callback
storage past a timeout, releasing it on eventual delivery instead of leaving a
stack pointer in the pending event. The [Doppler mapping repair](../reports/maintenance/20261010-doppler-map-callbacks/README.md)
qualifies this bridge correction on Vulkan, including timeout followed by delivery.
No ABI fields or callback modes change. General instance abandonment remains open.
