# Native device lifecycle contract

The [versioned policy](../config/native-device-lifecycle-contract.json) extends
[callback qualification](native-callback-contract.md) with descriptor-based loss,
explicit destruction, last external release and instance-owned loss futures.
Historical callback and application reports retain their original verdicts.

## Migration and ownership

Public descriptors and C signatures retain their pinned layouts. Descriptor
callbacks are now installed before the device is exposed. GetLostFuture returns
one instance-issued identity; explicit destroy makes the obligation ready exactly
once under its requested delivery mode. The callback receives a non-null pointer
to a borrowed device handle. Last external release, including release before a
deferred callback, clears that handle. Failed creation uses FailedCreation with a
null handle and preserves RequestDevice failure and later valid initialization.

Native resource leases are distinct from application AddRef/Release. Internal
leases retain native cleanup but do not defer logical destruction after the last
application reference. Callbacks borrow a scoped internal lease through return;
foreign code may release the caller handle or reenter without duplicating loss.
The legacy callback setter updates the same pending obligation.

DeviceDestroy invalidates admission before draining prior native work. It does
not interrupt submitted kernels. Vulkan retirement uses the existing completion
policy: unknown completion retains ownership until completion or confirmed loss.
Existing resource objects remain releasable; a destroyed device cannot admit new
GPU work or successful mapping. This is a correction behind existing interfaces,
not a new fallback or performance policy.

Valid async pipeline requests delivered after logical loss return Success with an
inert error object, matching pinned Dawn. The object owns its cleanup lease but
cannot be submitted or used to restore GPU admission. This is not successful
compilation or execution. Callback modes and allocation failures retain their
existing contract.

## Qualification

The [lifecycle fixture](../bench/external-projects/onnx-vulkan-device-lifecycle/lifecycle.cpp)
compares the preceding Doe binary, pinned source-built Dawn and repaired Doe in
independent processes. Raw phases, reasons, future polling, reentrant release,
failed creation/reuse and in-process DRM cleanup are retained. The existing
callback fixture, unchanged SqueezeNet and MatMul/Add recovery controls must pass
against the same immutable repaired binary. Semantic replay and schema checks
complement canonical Zig ownership and allocation-failure tests.

Actual driver loss, abandoned-instance cancellation, all-API conformance,
submitted-work interruption and physical non-Vulkan backends remain separate.
Neither these controls nor earlier rejected application timing establishes a
material advantage.
