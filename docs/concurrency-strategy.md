# Doe concurrency strategy

## Goal

Beat Dawn on concurrency where AI/browser workloads care:

1. async pipeline creation
2. parallel model warmup
3. upload/compute overlap
4. predictable callback completion under load

## Non-goals

1. generic graphics-engine maximal threading
2. cross-thread encoder mutation
3. hidden backend fallback behavior

## Threading contract

The runtime should converge on:

1. thread-safe devices, queues, immutable resources, shader modules, and pipelines
2. thread-confined encoders and pass encoders
3. explicit callback-thread semantics

This document owns the contract until the runtime exposes a replacement
schema-backed object-thread classification surface.

## Native addon ownership and migration

Each N-API environment owns its cached JavaScript methods, promises, timeout,
and device-callback lists. Native callbacks enqueue notifications; they do not
mutate another environment's list. Environment cleanup unregisters native
callbacks before Node finalizes their bridges. Cleanup ordering follows the
[Node-API lifecycle contract](https://nodejs.org/api/n-api.html#finalization-on-the-exit-of-the-nodejs-environment).

The addon initializes native symbols under a loader lock and retains the loaded
library for its process lifetime. Repeated selection of that library reuses it;
selecting a different library in the same addon fails explicitly. Use a separate
process to compare different native builds. This replaces unsafe library reload
and process-global JavaScript caches without changing public fields or schemas.
Optional native symbols are resolved with the same initial symbol table.

Device-loss registration replaces or unregisters the device's previous callback.
Registry mutation is synchronized; notification detaches its entry before calling
user code, allowing callback reentry. This does not make concurrent destruction
of a device and application mutation of that same device a qualified operation.

Current physical concurrency acceptance covers independent devices in Node
workers, recreated environments, and a surviving parent device. It does not
qualify arbitrary shared-device mutation, physical driver loss, or other hosts'
worker implementations. Retained execution and failure artifacts are indexed in
`bench/out/compute-program/20260907-async-pipeline-ownership/README.md`.

## Tooling I/O contexts

Tooling and orchestration paths now have a separate explicit I/O seam in
`runtime/zig/src/tooling/tooling_io_context.zig`:

1. `sync` for ordinary blocking CLI/tool runs
2. `cooperative_same_thread` for future same-thread cooperative orchestration
3. `threaded_parallel` for future fan-out work that should use OS threads

This I/O context is for replay loading, CLI input loading, and related
artifact/tooling flows. It is not a replacement for the runtime object
threading contract above, and GPU device/queue execution should remain on the
explicit runtime threading model unless a separate architecture row changes it.

## Phase 1 delivered here

1. bounded worker pool for CPU-side background jobs
2. real background compute-pipeline creation through async ABI entrypoints
3. real background render-pipeline creation through async ABI entrypoints
4. in-flight async request sharing after exact comparison of owned descriptions,
   device and resource identities; hashes only select comparison candidates
5. worker-delivered callback dispatch for queue/timeline completion paths via a shared runtime dispatcher
6. queue-role policy surface for inference-oriented scheduling
7. benchmark harness skeleton for concurrency evidence

## Phase 2

1. make model warmup and upload preparation parallel by default
2. add cache-backed background pipeline warmup for known model graphs
3. measure actual backend pipeline reuse during background warmup
4. benchmark and tune worker-pool sizing per backend and workload class

## Evidence

Async requests retain descriptor strings, constants, blends and resource leases
until completion. Callbacks receive independent pipeline references; releasing
an earlier callback's result cannot invalidate a later callback. Descriptor
copy failures roll back through the request's allocator and report an error.
Unsupported descriptor chains reject before scheduling. Creation markers are
not compiled pipelines and no longer populate a separate process cache.

Concurrency claims should be made only from benchmark artifacts that show:

1. cold-start latency
2. N-thread pipeline creation throughput
3. upload/compute overlap
4. callback delay under contention
5. apples-to-apples Dawn comparison on matched workloads
