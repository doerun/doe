# File examinations

The append-only review log owns verdicts. These notes retain the examination and
open repair obligations; supporting edits do not grant directory or relationship credit.

## `src/backend/d3d12/commands/d3d12_map_async.zig`

Examined the entire temporary-buffer map command, its provider caller, native Map range contract, and cleanup. The command borrows a device, owns one native heap buffer through unmap/release, and does not implement ordinary WebGPU callbacks. Bounds and native failures are admitted explicitly; no retained borrowed payload or process state is introduced.

Resolved:

- Read mappings now declare the CPU-read range and no CPU writes on unmap; write mappings preserve the upload-heap contract. Null/empty/oversized requests fail before native allocation. Recording-native tests cover both heap kinds, allocation/map failure, byte effects, and balanced cleanup.

No open file-local finding retained.

Next action: Retain the repaired implementation; ordinary map callbacks and physical D3D12 execution retain separate review/qualification obligations.

## `src/backend/d3d12/commands/d3d12_native_render_pass.zig`

Examined native recorded-pass decoding, attachment/view conversion, descriptor ownership, drawing, resolve operations and the queue caller. Native resource pointers remain borrowed through command references; per-pass native heaps/root signatures transfer into the submission retention list.

Resolved:

- Reserve all per-pass retention slots before acquiring native objects, eliminating append-failure leaks. The queue caller now aborts an unsubmitted list and reports recording/close failures instead of continuing with omitted passes.

Open findings:

- Recorded load/store/clear operations, pass boundaries, viewport/scissor and indirect execution fields are not faithfully consumed; vertex buffer stride is hardcoded to zero.
- A root signature created while recording replaces the pipeline root when bindings are present; this does not establish PSO/root-layout compatibility. Buffer bindings are not encoded.

Next action: Repair the pipeline-layout and recorded-pass contract together; preserve vertex strides and load/store/dynamic state through encoding, then test native command traces and physical output.

## `src/backend/d3d12/commands/d3d12_render.zig`

Examined pipeline identity/replacement, attachment ownership, vertex/index/indirect encoding, bundle replay and synchronous/deferred submission. State owns pipeline, root, attachments and indirect argument storage; deferred command objects transfer to runtime batches.

Resolved:

- Pipeline replacement is transactional and partial command acquisition is released. Indirect storage fits both draw argument shapes; command-signature creation uses the required empty root association and retry repairs missing argument storage.
- Deferred error cleanup now spans recording, bundle errors propagate, command-list close and fence bounds are checked, and submit timing starts before Execute/Signal instead of omitting that work. Runtime drains retained submissions before shared render-state replacement.

Open findings:

- Command shader/target inputs are not fully represented: the path builds fixed passthrough shaders and a private target, with a single-sample target even when the pipeline requests multisampling.
- Binding creation still supplies fallback sampler/texture interpretations and lacks authoritative resource/register mapping. Attachment load/store behavior and resource transitions need native debug-layer/output validation.

Next action: Replace the fixed shader/attachment assumptions with the declared render contract and shared pipeline layout, then verify state replacement and deferred execution on D3D12.

## `src/backend/d3d12/commands/d3d12_render_bind_groups.zig`

Examined fixed-array bounds, registry lookups, descriptor allocation/rollback, root-signature construction and table binding. The helper borrows resource registries and returns an owning root handle; descriptors remain owned by the device heap.

Resolved:

- Preflight rejects oversized slices and unknown non-null handles. Removed fabricated RGBA8/default-sampler fallbacks, sized temporary entries for both binding families, and roll back descriptor cursors on failure.

Open findings:

- Native recorded texture pointers and logical texture-view registry keys are different identities; the descriptor writer still passes a view identity where a native texture resource is required.
- Sparse binding positions are compacted and a new root signature is built without the pipeline layout; lifetime/full-capacity policy for shared descriptor ranges is not tied to submission retirement.

Next action: Define one typed binding snapshot carrying native resources and actual register positions; allocate descriptor tables against the pipeline-owned layout and retire them with submissions.

## `src/backend/d3d12/commands/d3d12_render_vertex.zig`

Examined command normalization, pipeline key fields, array/slice lookup, native-handle conversion, byte-size/stride arithmetic and inline tests. This file owns no allocation and borrows binding arrays only during recording.

Resolved:

- Vertex byte sizes now switch exhaustively over the canonical format enum. Fixed-vector indexing and offset addition are checked; key identity includes texture/sampler counts. Regressions cover scalar/vector sizes, invalid indexing and overflow.

Open findings:

- Count normalization silently clamps excess layouts/attributes, and zero stride is treated as missing and inferred from attributes, although an explicit zero stride has defined repetition semantics.

Next action: Separate absent layout defaults from explicit zero stride and reject excessive counts before key generation; bind normalization tests to the actual command producers.

## `src/backend/d3d12/commands/d3d12_streaming_copy.zig`

Examined recording/reuse, submitted-fence recovery, resource resolution, copy variants and teardown. Existing failure tests establish retry without duplicate submissions, but resource creation and copy semantics remain incorrect.

Open findings:

- resolve_resource creates buffers for texture identities and does not maintain a real buffer registry. Fresh buffer handles are not retained/released with the copy batch.
- Buffer offsets are omitted and texture-to-buffer/texture-to-texture commands are sent through CopyBufferRegion; dimensions, sizes, states and native footprints are not validated.

Next action: Repair real resource lookup/ownership first, then implement each copy direction with native layouts, offsets and transitions; use recording tests and GPU readback rather than state-only tests.

## `src/backend/d3d12/d3d12_bridge_decls.zig`

Examined the complete narrow ABI adapter, C-header-owned structures and synchronization status mapping. It allocates and retains nothing; unknown native status codes are failures, never success.

Resolved:

- check_signal and check_wait now expose the named SynchronizationError set explicitly. Existing synchronization fault tests exercise loss/signal/wait classifications and Windows compilation checks imported ABI use.

No open file-local finding retained.

Next action: Retain the typed boundary; backend C behavior and physical driver failure delivery require their own evidence.

## `src/backend/d3d12/d3d12_constants.zig`

Examined the entire native numeric/constants surface and its consumers. Constants encode native ABI values or fixed baseline bounds; there is no mutable policy, allocation, ownership transfer or unsafe execution here. Header/spec checking remains authoritative for transcriptions.

Resolved:

- Map admission and device caps now share BASELINE_MAX_BUFFER_SIZE; CBV admission and uniform limits share MAX_CONSTANT_BUFFER_BYTES. No new deployment knob was introduced.

No open file-local finding retained.

Next action: Retain centralized native constants and run the existing spec-drift checks when the pinned headers change.

## `src/backend/d3d12/d3d12_descriptors.zig`

Examined heap ownership, linear allocation, descriptor writing, root-signature layout conversion, errors and tests. Native heaps own descriptors; caller synchronization must protect descriptor reuse.

Resolved:

- Constant-buffer sizing is fallible and bounded before alignment, casts or slot mutation, including zero, over-limit and maximum-integer tests. Null native root creation remains an error.

Open findings:

- create_root_signature_with_bindings counts entries by type but discards explicit binding numbers and dynamic-offset semantics; its stated group/table model disagrees with native range-per-root-parameter construction.
- reset_allocations has no submission-retirement precondition encoded in its interface; overflow/full-capacity behavior needs integration with the owning queue.

Next action: Build tables from actual binding/register identities and make retirement part of descriptor reuse; test sparse groups, sampler-only groups, failure rollback and in-flight allocations.

## `src/backend/d3d12/d3d12_device_caps.zig`

Examined static limits, feature admission, native probe calls, adapter cache and tests. The adapter registry is process-owned and returns copied snapshots; device probing must remain authoritative for hardware facts.

Resolved:

- Protected registry get/set/remove with a mutex and release the empty map. Shared buffer/uniform limits replace duplicate values.

Open findings:

- Native bridge shader-model and wave-size functions return constants rather than hardware observations; subgroup reporting derived from them cannot establish native support.
- Registry insertion still suppresses allocation failure, and advertised static limits/features are not bound to implemented native/compiler support across all consumers.

Next action: Replace bridge placeholders with actual CheckFeatureSupport results, propagate required cache failures, and qualify advertised features against native/compiler implementation tests.

## `src/backend/d3d12/d3d12_formats.zig`

Examined all color, depth/stencil, compressed and vertex conversions, copy-byte metadata and tests against canonical format identities. The pure mapping allocates nothing; unavailable native formats return UnsupportedFeature. Copy footprint metadata is not GPU allocation/residency.

Resolved:

- RGBA16 normalized formats now report their full byte footprint. Registered inline format tests explicitly and corrected the erroneous integer-vector test identity while retaining separate two- and three-component expectations.

No open file-local finding retained.

Next action: Retain the pure format mapping and pinned-value tests; plane-specific copy legality remains owned by the copy contract and native adapter.

## `src/backend/d3d12/d3d12_native_runtime.zig`

Examined initialization/deinitialization, pending upload/submission retention, completion/device-loss handling and every resource/compute/render/surface forwarding path. The runtime owns allocator-backed registries and native device/queue state; helpers borrow that serialized owner.

Resolved:

- Texture cleanup now receives the map allocator. Resource replacement/destruction and render-state reuse drain outstanding work, including pending submit batches and streaming copies. Texture-write device loss is retained and write timing keeps submission separate.

Open findings:

- Kernel pipeline replacement and surface retirement still lack the same complete in-flight-resource handoff as the repaired render/resource paths.
- The runtime exposes copy/query/surface helpers whose resource semantics remain unfinished; wrapper reachability is not proof of native API completion.

Next action: Apply the completion/retirement contract to compute pipeline and surface replacement, then exercise mixed copy/render/compute resource lifetimes with injected failures and native validation.

## `src/backend/d3d12/d3d12_query_set.zig`

Examined the full multi-query-set helper, native query-type calls, readback ownership/conversion and callers. It is distinct from the repaired dispatch timestamp owner; runtime creation/destruction wrappers do not establish an exercised ordinary query path.

Open findings:

- create can overwrite an existing handle or leak all native objects on map insertion failure, and substitutes frequency 1 for an unavailable timestamp clock.
- begin/end/resolve use bridge functions with incompatible hardcoded query types; resolve records on an already-closed command list, lacks per-slot availability/mapping state, and conversion can overflow or collapse unavailable data to zero.

Next action: Establish a real consumer and typed query recording/availability contract, then repair transactional creation, readback lifetime and checked conversion; do not inherit dispatch timestamp qualification.

## `src/backend/d3d12/d3d12_runtime_compute.zig`

Examined shader lookup/compilation/cache identity, pipeline replacement, dispatch-info ownership, timestamp integration and command submission. Native transient buffer/heap ownership transfers into runtime submission batches; source/DXC allocations are explicit.

Resolved:

- Reserve both dispatch-info retention slots before either ownership transfer, preventing a failed second append from causing duplicate release.

Open findings:

- loadKernelCso can prefer an unrelated same-basename DXIL/CSO/DXBC file over requested WGSL without content/toolchain binding; generated cache identity omits compiler/options and publication is not atomic.
- Pipeline replacement drops old state before successful replacement and partial command acquisition is not transactional; the single dispatch-info root layout does not realize general kernel bindings. Shader hash reuse has no byte equality check.

Next action: Bind source and compiled artifacts explicitly, make pipeline replacement transactional after retirement, and implement request entrypoint/resource layouts before qualifying general kernel execution.

## `src/backend/d3d12/d3d12_runtime_upload.zig`

Examined temporary command/buffer ownership, pending submission admission, retry without resubmission, completion-driven release and pool allocation. Existing fault tests exercise queue errors, retry and terminal loss. No source change is needed for that already-repaired synchronization subpath.

Open findings:

- Pools limit entries per exact size but retain an unbounded number of size classes; capacity, total retained bytes, invalidation and full-budget behavior are not defined across the runtime owner.

Next action: Define an explicit total retention policy for both upload/default pools and test varied sizes, allocator failures, budget exhaustion and cleanup without changing measured work.

## `src/backend/d3d12/mod.zig`

Examined provider construction, capability routing, prepared/native commands, request conversion, policy admission, telemetry/artifacts and teardown. This is the command-oriented provider, distinct from native WebGPU object entrypoints.

Resolved:

- Pending-upload counters clear only after successful flush. Texture writes report actual submission waiting separately from encoding. Required timestamp admission remains before runtime work.

Open findings:

- Kernel execution/prewarm omit request entrypoint, binding and initialization semantics; broad capability reporting does not establish complete command behavior.
- Several subordinate render/copy/surface/query paths remain incomplete; provider success and logical counts cannot be used as proof of equivalent GPU work.

Next action: Propagate complete kernel requests into real pipeline/binding execution and validate per-command capabilities against repaired native work; retain non-claimable physical evidence boundaries.

## `src/backend/d3d12/resources/d3d12_depth_stencil.zig`

Examined pure depth/stencil classification and the single-sample texture/DSV owner. Native objects are acquired transactionally, reused by exact dimensions/format, and released by one state owner after caller retirement; no allocator or process cache is hidden.

Resolved:

- Canonical WebGPU depth identities replace local copies. Replacement preserves both old handles until the new pair exists; injected native allocation failures verify rollback and successful replacement releases the old pair.

No open file-local finding retained.

Next action: Retain this single-sample owner; the render caller must resolve its separate multisample attachment finding rather than treating this helper as multisample support.

## `src/backend/d3d12/resources/d3d12_sampler.zig`

Examined sampler identity, native descriptor creation, heap capacity, replacement, destruction and map ownership. The runtime serializes descriptor replacement with prior work; slots belong to the state-owned heap.

Resolved:

- Sampler creation now writes the actual native descriptor. Reserve map capacity before native acquisition, reuse the existing slot on replacement, and recycle destroyed slots. Capacity/replacement/double-destroy tests prove reuse and exact descriptor-write accounting.

Open findings:

- Sampler admission does not validate finite/ordered LOD bounds, filter/address enums or anisotropy requirements before the bridge maps them; invalid values may silently become native defaults.

Next action: Apply shared sampler semantic validation before descriptor writes and test invalid enums, LOD ranges and anisotropic filtering combinations through the command/native boundary.

## `src/backend/d3d12/resources/d3d12_texture.zig`

Examined texture registry ownership, allocation/layout admission, data movement, mip/array/volume addressing, native state transitions, completion and query/destruction. Layout tests validate source bounds and packing independently of a GPU.

Resolved:

- Upload supplied bytes rather than uninitialized staging data; repack compact/padded source rows to native row/placement alignment, preserve offsets, size mips/volumes and use correct array subresource indices.
- Retain staging/list/allocator through completion, track write transitions, propagate allocation causes and device loss, validate existing texture identity, and free registry storage with its owning allocator. Separate host encoding and submission/wait timing.

Open findings:

- The shared texture registry is also populated/consumed by the unfinished streaming-copy path, so a registry hit does not yet guarantee a real texture or globally current resource state.
- texture_query omits expected dimension/view-dimension/usage fields; native upload round trips and allocation/recording failure probes remain required beyond layout-only tests.

Next action: Unify registry resource/state ownership with real copy execution, honor all query expectations, and verify upload/readback across mips, compressed layouts and native failure cleanup.

## `src/backend/d3d12/resources/d3d12_texture_view.zig`

Examined view identity/aspects, descriptor emission, dimension selection, map allocation, destruction and caller-owned heap lifetime. Views borrow texture identity; descriptor storage belongs to the supplied heap.

Resolved:

- Use canonical aspect values so depth and stencil cannot alias each other. Reject duplicate handles and null native prerequisites, reserve map space before descriptor writes, and reset freed map state. Aspect regressions are explicitly registered.

Open findings:

- Storage-vs-sampled descriptor selection follows texture usage rather than the binding role, and the 1D path calls a 2D-only bridge writer.
- Mip/layer bounds and supported storage-format admission are incomplete; unknown format/dimension fallbacks and descriptor retirement need an authoritative texture/layout contract.

Next action: Carry the actual texture descriptor and binding role into view creation, implement the native dimension variants, and validate ranges before publishing descriptors.

## `src/backend/d3d12/surface/d3d12_surface.zig`

Examined surface state transitions, swapchain/RTV/target ownership, reconfiguration failure and presentation. The state map owns native objects; the runtime must supply a completion boundary before replacement/destruction.

Resolved:

- Duplicate create and configure-without-create fail explicitly; reconfiguration publishes only a complete replacement and preserves old ownership on every acquisition failure. Reject replacement while acquired and presentation without acquisition. Native-failure probes cover rollback; deinit resets state.

Open findings:

- The render target is a separate allocation rather than the acquired swapchain back buffer; acquire only changes local status, so presentation does not prove rendered-frame delivery.
- Capabilities do not query native support, configure omits requested usage/present-mode/latency semantics, and caller retirement is incomplete.

Next action: Connect acquisition to real swapchain buffers and requested presentation policy, then validate rendered output, resize/reconfigure and in-flight teardown on Windows.

## `src/backend/dawn_delegate_backend.zig`

Examined the full owning Dawn delegate, composition-selected provider identity, narrow port adapters, error forwarding, logical submission accounting and observation. Allocation rollback and deinit retain the exact allocator; preparation/capture borrow caller inputs and forward to the inner WebGPU owner. Retain unchanged: the documented prewarm no-op makes no execution claim and telemetry performs no file output.

No open file-local finding retained.

Next action: Retain this adapter; independently review inner WebGPU execution and comparator work/timing before making provider-performance claims.

## `src/backend/dropin_capabilities.zig`

Examined the entire import gateway and actual Metal capability calls with native capability consumers. Retain unchanged: platform availability is compile-time explicit; the gateway owns no cache/allocation and does not invent hardware results. D3D12 probe defects remain attributed to their implementation scope.

No open file-local finding retained.

Next action: Preserve this narrow gateway while repairing D3D12 hardware queries in their owner; do not infer complete capability implementation from the re-export.

## `src/backend/dropin_external_texture.zig`

Examined all aliases and the native external-texture caller. Retain unchanged: plane layout/import/release operations and pixel formats stay with the Metal owner, with no duplicated semantic transform, allocation or retained state in this gateway. The importer remains responsible for actual native resource acquisition.

No open file-local finding retained.

Next action: Retain the seam; external producer synchronization and plane lifetimes require the dedicated native/Metal relationship examination.

## `src/backend/dropin_lifecycle.zig`

Examined all runtime type and native lifetime aliases with shared/native lifecycle consumers. Retain unchanged: the gateway introduces no additional owner; Vulkan availability is explicit by target and Metal retain/release keep their native contracts.

No open file-local finding retained.

Next action: Retain the aliases; device construction, callback and teardown ordering remain separate end-to-end review scopes.

## `src/backend/dropin_pipeline_cache.zig`

Examined active/disabled/warmup accessors, explicit flush, platform handling and queue lifecycle consumers. Observations read the device-owned cache; persistence only occurs at the explicit flush boundary. Non-Vulkan queue callers return before this adapter, preserving availability discrimination.

Resolved:

- Use the named NativeVulkanRuntime pointer instead of anytype field-shape dependencies. Existing core/native compilation verifies callers against the explicit type.

No open file-local finding retained.

Next action: Retain the typed adapter; cache identity, budget, persistence failures and invalidation belong to the persistent-cache owner review.

## `src/backend/dropin_queue_submit.zig`

Examined all backend implementation re-exports and native queue consumers. Retain unchanged as an import gateway: it has no independent dispatch policy, allocations or resource lifetime. It does not establish behavioral backend decoupling or certify the implementations it exposes.

No open file-local finding retained.

Next action: Keep the gateway; inspect shared completion versus platform operations in the native/backend relationship pass and repair the D3D12 recorded-pass findings separately.

## `src/backend/dropin_render_state.zig`

Examined the complete single-alias seam and native render-state caller. Retain unchanged: it neither converts enum values nor owns mutable state; conversion correctness remains with the Metal render-state implementation and its actual ABI consumers.

No open file-local finding retained.

Next action: Retain the import seam; review Metal dynamic-state conversion and ABI enum identity in their implementation/relationship scopes.

## `src/backend/dropin_resource_ops.zig`

Examined all aliases plus Vulkan writeTexture argument conversion and error delivery, tracing the exported native caller through the Vulkan callee. Error handling is explicit once Vulkan is selected, but the request loses semantic information before execution.

Open findings:

- QueueWriteTextureArgs omits origin, slice, width and depth supplied by doeNativeQueueWriteTexture. copyTextureResource reconstructs the full texture extent, so partial/nonzero-origin writes cannot preserve the public request.

Next action: Carry the full validated write region through the adapter and native Vulkan copy operation; add public-path readback tests for partial, layered and nonzero-origin writes.

## `src/backend/dropin_surface_ops.zig`

Examined platform-gated surface constructors/types and native surface consumers. Retain unchanged: the gateway owns neither presentation state nor host handles and adds no hidden fallback; actual surface lifecycle remains in the selected native backend.

No open file-local finding retained.

Next action: Retain the gateway; platform surface creation, presentation and destruction require the dedicated native/backend execution-path review.

## `src/backend/metal/artifact_emit.zig`

Examined the full Metal manifest specification, typed artifact-state owner, shared emitter and explicit collection caller. Retain unchanged: stage labels are derived identities under the current manifest contract, optional fields are not asserted content hashes, and flush is explicit/fallible outside telemetry reads.

No open file-local finding retained.

Next action: Retain this backend specification and shared publication owner; actual compiler-stage byte capture needs independent evidence before changing identity kinds.

## `src/backend/metal/backend_execute.zig`

Examined every command adapter, timestamp admission call chain, pending-work flush, receipts, prewarm and capture. Runtime owns native resources; capture returns an allocator-owned independent copy. Generic backend field dependencies remain visible for a later typed-interface repair.

Resolved:

- Failed flushes preserve pending-upload accounting. Buffer capture queries actual native length, rejects bounds/overflow, waits for completion before mapping and copies into the caller allocator. The new internal bridge symbol is declared, implemented, stubbed and registered. Recording tests cover bounds, flush failure/retry and snapshot independence.

Open findings:

- Async diagnostic commands route through synchronous render-pipeline preparation while reporting diagnostic success and fixed logical counts without performing the requested asynchronous operations.
- The executor still relies on a large anytype backend field surface; the named owner/required operations should be explicit when repairing the diagnostic path.

Next action: Implement the requested asynchronous diagnostic operations with measured callback/completion events and a named execution dependency contract; retain capture/flush regressions and validate on Metal hardware.

