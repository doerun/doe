# Metal and capability-port file examinations

Batch base: `a825aa79c062d8a939f8246924e56625fb5d4b9c`.
These are file passes only. Source inspection includes whole files and the named ownership/ABI consumers; host tests do not establish native Apple execution. Open findings prevent verified status.

## 1. `src/backend/metal/metal_async_runtime.zig`

Read the complete temporary-buffer mapping command, size admission, queue retirement and scoped native release. This is a command probe, not the ordinary WebGPU mapAsync callback implementation. Exhaustive read/write handling and checked zero/maximum size admission remain; device selection now uses the runtime device.

Verdict: `verified`.

Repairs and checks:

- The maximum-buffer-length query now receives runtime.device instead of querying the default device. The host failure-route test exercises acquisition failure and safe teardown; existing pure tests cover maximum/unknown-limit admission.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 2. `src/backend/metal/metal_bridge_decls.zig`

Read the extern declarations and C-layout records against the bridge header and native callers. Retain the ABI boundary: optional native handles and C calling conventions are explicit, and layouts use extern structs. Symbol-manifest checks and host linking establish declared linkage, not Apple runtime semantics.

Verdict: `verified`.

Next action: Retain declarations; extend signature/layout parity checks alongside native changes. Native sampler and completion semantics remain findings in their owning scopes.

## 3. `src/backend/metal/metal_buffer_pool.zig`

Read exact-size lookup, ownership transfer on return, per-size saturation, allocator failure release and shader-name normalization. Pop transfers a handle; insertion failure releases it; cleanup owns list/map deallocation.

Verdict: `needs_changes`.

Open findings:

- BufferPool limits each size class but not the number of size classes or total retained bytes; empty keys persist after pop. There is no overall retained-memory bound.
- strip_extension owns shader request normalization in a buffer-storage module, with an external test dependency that must migrate with any move.

Next action: Give the pool a versioned total retention policy and owned accounting, test full/OOM/reuse paths, then move shader normalization with its tests to its actual owner.

## 4. `src/backend/metal/metal_cleanup.zig`

Read every teardown helper, map key allocation owner, native handle release and sampler-cache coordination. The caller must retire outstanding work before invoking these helpers. Surface cleanup now uses the same complete release operation as explicit surface destruction.

Verdict: `verified`.

Repairs and checks:

- Runtime surface-map cleanup previously released only textures, leaking drawable and host ownership. It now delegates to releaseSurfaceState; a recording test verifies discard, texture release, unconfigure, host release and idempotent reset.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 5. `src/backend/metal/metal_copy_runtime.zig`

Read all copy directions, implicit resource creation, encoder transitions, temporary staging and timing. Shared buffer admission now uses actual native lengths, and temporary staging belongs to deferred retirement.

Verdict: `needs_changes`.

Repairs and checks:

- Buffer offset addition, default pitch multiplication and temporary-size rounding now reject overflow.
- Texture publication releases on allocator failure; buffer publication uses the shared transactional owner. Temporary storage is retained until queue retirement instead of immediate CFRelease.
- Buffer/texture bridge calls now supply the missing origin and aspect arguments. Host failure-route compilation instantiates the real copy function.

Open findings:

- Texture footprints still assume four bytes per pixel and staging size can be smaller than padded rows/images; format/block/aspect-aware layout and payload bounds are not established.
- Existing texture handles bypass descriptor compatibility checks; copy geometry/mip/sample restrictions need validation before any native recording.

Next action: Implement canonical format-aware copy footprints and validate both source/destination resources before encoding; add padded-row, compressed/aspect and native readback oracles.

## 6. `src/backend/metal/metal_deferred_release.zig`

Read ring saturation/drain, descriptor equality, logical reference accounting, full-cache eviction and uncached ownership. Removed unsupported performance narrative and clarified retirement preconditions and uncached-handle release ownership.

Verdict: `needs_changes`.

Repairs and checks:

- Cache reference increments now detect overflow. Native lifecycle commands retire pending queue work before sampler eviction or resource destruction.

Open findings:

- SamplerDescKey and native creation omit SamplerCreateCommand.compare, allowing distinct comparison descriptors to alias. The native bridge also uses a process-global mutable sampler descriptor and divergent filter/address mappings.
- The ring has no completion token of its own and relies on caller retirement; current lifecycle callers now flush before release/eviction, but this contract needs a complete native retirement test.

Next action: Repair sampler meaning and descriptor ownership across the bridge and ordinary native sampler caller; add comparison/filter/address and concurrent-device tests.

## 7. `src/backend/metal/metal_dispatch_runtime.zig`

Read direct/indirect allocation, pipeline selection, shared argument writes, queue transitions and result accounting. Standalone command buffers own their handles through completion or transfer to outstanding state.

Verdict: `needs_changes`.

Repairs and checks:

- Indirect dispatch retires earlier users before overwriting the shared argument buffer; the returned submit/wait time includes this retirement.

Open findings:

- Bridge dispatch recording and completion return void, so failed encoding or command-buffer execution cannot reach the result. Required native status must survive both deferred and immediate paths.

Next action: Propagate native encode/completion status and exercise repeated indirect dispatch argument preservation on Metal.

## 8. `src/backend/metal/metal_external_texture.zig`

Read IOSurface/CVPixelBuffer admission, plane acquisition, partial-failure rollback and retained PlaneLayout release. Non-macOS/null acquisition is explicit and successful planes transfer native references.

Verdict: `needs_changes`.

Open findings:

- Every plane_count greater than one follows the two-plane NV12 interpretation; more planes and incompatible two-plane pixel formats are not rejected or described by the input contract.

Next action: Bind native pixel format and exact supported plane layout to import admission; add unsupported-layout and second-plane failure tests on the bridge.

## 9. `src/backend/metal/metal_gpu_timestamps.zig`

Read capability probing, counter owner, begin/end recording, resolution and streaming activation. Deinit resets state; resolved nonpositive/failed samples remain unavailable through zero plus validity flags.

Verdict: `needs_changes`.

Repairs and checks:

- Timestamp activation now closes an active compute encoder as well as render/blit encoders before creating the sample encoder.

Open findings:

- record_begin/record_end call a void sampling bridge, so activation can be marked successful even if the sample encoder was not created; stale sample contents are not distinguished by generation.

Next action: Return sampling success/generation from the bridge and bind validity to both samples from the completed invocation; test encoder failure and reuse.

## 10. `src/backend/metal/metal_kernel_dispatch.zig`

Read pipeline/workgroup resolution, binding packing, warmup, repeated/deferred dispatch and timestamp accounting. Pending work now retires before standalone/warmup submissions, preserving the queue order; this retirement remains in setup cost.

Verdict: `needs_changes`.

Repairs and checks:

- Prior streaming work is flushed before warmup, timestamped or immediate command buffers are submitted, preventing newer standalone work overtaking uncommitted work.

Open findings:

- Binding packing silently skips non-buffer resources and out-of-range slots, ignores group and buffer_offset, and has no duplicate-slot admission. Requested binding semantics can differ from encoded work.
- Fixed rollover policy and void native execution status remain outside an explicit validated dispatch contract.

Next action: Lower validated binding groups/offsets and resource kinds through compiler metadata, reject unrepresentable requests before work, and add delayed-submission ordering tests.

## 11. `src/backend/metal/metal_native_runtime.zig`

Read initialization rollback, runtime-owned native maps, scratch/pool/cache state, forwarding operations and teardown order. Allocator and borrowed configuration are supplied by the backend owner; teardown retires work before releasing maps.

Verdict: `needs_changes`.

Repairs and checks:

- Staged writes use checked required-size arithmetic. A new non-Metal failure-route test instantiates actual mapping, copy, texture allocation and teardown paths and checks maps remain unpublished on failure.

Open findings:

- Teardown suppresses flush errors and native waits cannot report completion failure; the resource retirement guarantee remains incomplete on device/command-buffer failure.
- Configuration/cache/scratch policy and many anytype implementation shards remain coupled through the full runtime field layout; narrow state ownership is still needed where it removes ambiguous lifetime dependencies.

Next action: Complete native completion/error retirement first; separate the cache and transfer owners using that lifetime contract without moving unrelated objects.

## 12. `src/backend/metal/metal_pipeline_cache.zig`

Read cache creation/destruction, path resolution, archive calls, telemetry, persistence, fingerprint invalidation, warmup manifests and every C export. Cache objects own allocations and sidecar lists; bridge-native archive ownership is scoped to deinit.

Verdict: `needs_changes`.

Repairs and checks:

- cache_dir now borrows the cache-owned archive path rather than caller/environment bytes. Failed archive serialization preserves dirty state for retry.

Open findings:

- Null compile results are accumulated as total_hit_ns while successful archive calls count as misses; no observed native hit/miss signal justifies these labels.
- A missing/unreadable fingerprint writes a new sidecar but retains any existing archive. Device name/registry ID does not identify driver/toolchain changes, and failed invalidation is silently ignored.
- Warmup limits and lazy flush policy remain handwritten; sidecar writes are non-atomic and compute keys/source identity need stronger validation and retention bounds.

Next action: Use observed cache-result metadata, transactional fingerprint/archive persistence and explicit configuration; test missing fingerprint, failed writes, source changes and caller string lifetime.

## 13. `src/backend/metal/metal_render_state_bridge_decls.zig`

Read render-state extern signatures and C-layout blend/depth records against the matching header and Objective-C consumer. Retain the narrow ABI declaration owner; it allocates nothing and does not choose render semantics. Existing conversion tests exercise all record fields, but native execution remains unqualified.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 14. `src/backend/metal/metal_resource_commands.zig`

Read sampler create/replace/destroy and texture write/query/destroy including native map publication. Lifecycle retirement now precedes release/eviction; insertion failures no longer leave an undefined texture value or an extra sampler reference.

Verdict: `needs_changes`.

Repairs and checks:

- Failed sampler-map insertion releases its acquired logical/native reference. New texture entries are initialized and removed on creation failure; host failure-route tests verify the map remains empty.
- Sampler creation/destruction and texture destruction flush pending uses before cached eviction or deferred release.

Open findings:

- texture_write does not validate data length, bytes-per-row/image products, shift/mip range or descriptor compatibility before native memory access.
- texture_query ignores an expected depth of one, and sampler compare/filter/address interpretation remains incomplete in the cache/native bridge.

Next action: Validate complete texture footprint and descriptor semantics before publication; fix exact-depth queries and repair sampler translation end to end.

## 15. `src/backend/metal/metal_runtime_limits.zig`

Read both constants and upload/queue consumers. This is a shared owner for staging capacity and scoped-wait selection, without allocation or executable state.

Verdict: `needs_changes`.

Open findings:

- Staging capacity and the wait-path threshold are handwritten policy values; the declared build/runtime configuration does not own or identify these meaningful choices.

Next action: Move supported staging/wait policy into the existing versioned backend policy and derive immutable typed values, with limits validated before use.

## 16. `src/backend/metal/metal_runtime_queue_ops.zig`

Read streaming encoder finalization, ordered submit rollover, outstanding retirement, uploads recycling, timestamps, barriers and prewarm delegation. Array storage is recycled only after the selected queue wait; source snapshots remain owned across rollover.

Verdict: `needs_changes`.

Open findings:

- Native completion waits and shared-event waits report no failure and have no enforced timeout; failed GPU work can appear successfully retired or wait indefinitely.
- barrier ignores queue_wait_mode and changes behavior with deferred policy without an explicit wait-capability result.

Next action: Make command-buffer completion/error/timeout observable and thread it through flush/barrier before releasing retained work; test failed signal and device loss.

## 17. `src/backend/metal/metal_runtime_render_ops.zig`

Read target/pipeline setup, temporary-target swap, draw recording, blit-back and queue-sync result. Temporary target restoration now occurs on failure as well as success, and its native reference lasts through retirement.

Verdict: `needs_changes`.

Repairs and checks:

- Temporary render storage is registered with deferred retirement instead of immediate release; the saved target is restored by defer on every exit.

Open findings:

- render_bundle and ordinary draw branches record identical direct draws, without implementing bundle recording/replay semantics. Several RenderDrawCommand state fields are not applied by this narrow path.
- Void bridge encoding/completion cannot report a failed render submission.

Next action: Implement command-declared bundle/state behavior and propagate native failures, then validate temporary render/blit output on Metal.

## 18. `src/backend/metal/metal_runtime_resources.zig`

Read shader request normalization, source selection/translation, pipeline publication, compute storage, mapped writes, render target/pipeline and ICB reuse. Native references now have single rollback/replacement paths.

Verdict: `needs_changes`.

Repairs and checks:

- Compute pipeline insertion failure now releases its PSO and releases function handles exactly once.
- Buffer creation releases on mapping/publication failure; reused handles check actual native length, and write-size arithmetic rejects overflow. Recording tests cover OOM, null mapping, initialization and oversized reuse.
- Mapped writes retire preceding GPU uses. Render pipeline/target/ICB replacement retires old uses and constructs the replacement before releasing current state.

Open findings:

- Pipeline identity strips file extensions and prefers .metal over .wgsl; cached keys omit source contents and compilation metadata. Selected entrypoint is not passed into runtime WGSL translation.
- Translation failure falls back to a different compiler entry and zero workgroup metadata; raw-MSL workgroup recognition uses source-text matching instead of a declared/analyzed invariant.

Next action: Make exact source, entrypoint and compiler metadata the pipeline identity and remove fallback translation/zero-metadata execution; add multi-entrypoint and source-change regressions.

## 19. `src/backend/metal/metal_surface_runtime.zig`

Read every create/configure/acquire/present/resize/unconfigure/release transition and surface-state ownership. Explicit release and runtime teardown now share a complete idempotent cleanup operation.

Verdict: `needs_changes`.

Repairs and checks:

- releaseSurfaceState owns drawable discard, texture release, host unconfigure/release and state reset; a recording test verifies order and exactly-once behavior.

Open findings:

- Failed reconfiguration or layer replacement can leave configured/acquired flags describing released previous state. Validate and transact state changes before admitting acquisition.
- surface_capabilities only creates an entry; it does not examine native surface capabilities. Presentation ordering relative to pending streaming work still needs an explicit contract.

Next action: Make configure/layer replacement transactional and add failure/resize/presentation ordering tests against the actual surface bridge.

## 20. `src/backend/metal/metal_upload.zig`

Read staging prewarm, scratch reuse, pool checkout/return, submission ownership and failure paths. Arbitrary user writes now own independent byte snapshots until completion; constant-zero upload scratch is initialized across its full capacity.

Verdict: `needs_changes`.

Repairs and checks:

- Consecutive staged writes no longer reuse mutable prewarmed source bytes. A recording test delays both copies, mutates caller storage and checks independent output.
- Retention capacity is reserved before native acquisition; null mapping/encoder and allocation failures release acquired sources and leave no published pending upload.
- Destination range/overflow checks are explicit, upload source/destination acquisition has rollback, and zero scratch initialization covers future larger uploads. Scratch prewarm now acquires both buffers and mapping before replacing previous state, and releases both on failure.

Open findings:

- Staging and scoped-wait choices still depend on handwritten policy; no native allocation-failure campaign or physical retention/reuse check establishes the complete prewarm contract.
- Full pool retention and native completion failure are not bounded/observable by this helper; those owners retain separate findings.

Next action: Add native OOM/completion failure and bounded-retention tests for prewarm; move policy to its configuration owner and measure any cost only on ordinary physical workloads.

## 21. `src/backend/metal/mod.zig`

Read backend construction/config ownership, capability declarations, driver adapter, telemetry/artifact collection and destruction. Root forwarding preserves explicit fallible collection and device-owned configuration.

Verdict: `needs_changes`.

Open findings:

- native_capability_set advertises async diagnostic capabilities whose backend_execute branches run render-pipeline setup instead of the requested operation.
- Queue timeout setter silently ignores the requested timeout; required waits cannot currently report unsupported policy.

Next action: Connect each advertised capability to real execution and validate wait policy through a fallible configuration boundary; preserve ordinary-provider selection.

## 22. `src/backend/metal/render_state.zig`

Read descriptor types, conversion helpers, dynamic setters and every C export against the native render-state bridge and package callers. Conversion lifetime is synchronous; created handles transfer a native reference.

Verdict: `needs_changes`.

Open findings:

- Blend/stencil constants are a private zero-based vocabulary labeled WebGPU-compatible; the canonical WebGPU header has a different vocabulary. Current tests repeat local values rather than establish public/native parity.
- MSAA export maps sample_count below two to four, despite documentation admitting one; descriptor and dynamic-state admission is delegated to void native APIs.

Next action: Trace the public callers and migrate values to the canonical ABI without silently breaking private consumers; test independent native constants and exact sample-count behavior.

## 23. `src/backend/metal_package_pipeline_cache.zig`

Read the complete package cache adapter and native device-owner usage. Retain a narrow construction seam: allocator/device/path pass directly to the backend-owned cache, with no parallel policy or mutable wrapper state.

Verdict: `verified`.

Next action: Retain the adapter; the cache owner has independent unresolved persistence and observation findings.

## 24. `src/backend/ports/capture.zig`

Read buffer/texture capture signatures and delegation. Allocator ownership of returned independent bytes is now explicit; context/vtable remain borrowed and errors propagate without defaults.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 25. `src/backend/ports/compute.zig`

Read prepared dispatch, prewarm and timestamp-mode operations with their prepared/compute contracts. Inputs are synchronously borrowed and results/errors forwarded; removed an unused std import. No shader meaning or binding rewrite belongs here.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 26. `src/backend/ports/factory.zig`

Read every required port and optional capture slot, composition construction and owner teardown. Documented that the bundle borrows one provider context and does not retain resources; removed an unused std import.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 27. `src/backend/ports/lifecycle.zig`

Read the prepared lifecycle operation and report forwarding. The vtable requires an implementation and propagates its result; capability correctness belongs to the provider and is not inferred from this interface.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 28. `src/backend/ports/mod.zig`

Read every re-export and alias. Retain the aggregation root unchanged: it adds no state, fallbacks, allocation or command interpretation. Reachability was checked through the runner and provider construction.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 29. `src/backend/ports/provider_adapter.zig`

Read the full concrete-driver adapter and all vtables. Dispatch conversion uses the canonical prepared contract; direct-buffer-write adaptation preserves bytes/offset/size, sync propagates flush errors, and unsupported spatial/timestamp behavior remains explicit. Optional artifact collection is distinct from snapshots.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 30. `src/backend/ports/queue.zig`

Read flush/sync and policy setters through the driver adapter. Delegation preserves native errors and nanosecond returns; removed an unused import. Setter capability/admission limitations remain in the provider scopes, not evidence that every wait mode is supported.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 31. `src/backend/ports/readback.zig`

Read capture-buffer signature and delegation with the native capture caller. The supplied allocator owns the independent returned snapshot; missing/invalid handles remain provider errors and no host execution shadow is introduced.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.

## 32. `src/backend/ports/render.zig`

Read prepared render/report types and direct delegate. No resource retention, state policy or fallback is added; removed an unused std import. Backend completeness remains its own scope.

Verdict: `verified`.

Next action: Retain this file; re-examine when its bound contract or consumer changes.
