# File examinations

These are whole-file source examinations. Supporting callers, contracts, bridge
code and fixtures are bound as context, without automatic review credit.

## Metal resource commands

`src/backend/metal/metal_resource_commands.zig`: needs changes.

Examined sampler creation/replacement/rollback/destruction and all texture
write/query/destruction branches. Sampler ownership remains cache-or-deferred;
texture native references belong to the named texture map until transfer to
deferred retirement. Inputs are borrowed for the call; CPU writes do not retain
the payload. The write plan has no allocation and validates before flushing or
acquiring. Shared layout arithmetic bounds the subsequent pointer offset. Array
and volume paths have distinct native shapes. Query expectations no longer
silently pass. The recording bridge checks output and call order independently.

Resolved: missing footprint/mip checks, contradictory texture reuse, ignored
query fields and CPU writes overtaking queued work. Remaining: retirement relies
on native flush/wait status that is not yet a complete error/completion contract.
Host ordering tests cannot close that finding or qualify in-flight release.

## Metal copy runtime

`src/backend/metal/metal_copy_runtime.zig`: needs changes.

Examined every direction, timing boundary, map lookup, resource acquisition,
encoder transition and temporary-reference path. The plan owns no allocations;
checked descriptors/layouts feed execution. Buffer capacity is checked on both
sides before acquisition. Map references survive partial acquisition failure
under the runtime owner. A temporary native reference is locally released until
encoding transfers it to deferred releases, including when later flush fails.
No new parallel format table or hand-computed pixel size remains.

Resolved: fixed-size pixel assumptions, unchecked offset/mip arithmetic,
descriptor/extent mismatch, undersized padded staging and treating array layers
as volume depth in the bridge. Remaining: void native encode and completion APIs
cannot report all native failures; physical copy/readback is unqualified.
Metrics retain their existing timing boundaries and make no performance claim.

## Metal texture resources

`src/backend/metal/metal_texture_resources.zig`: verified within file scope.

Examined complete new descriptor/map owner, enum and extent admission, mip
selection, usage/identity compatibility, query predicates and acquisition.
Allocator and device are explicit acquisition inputs; no process-global state
or hidden allocation policy is introduced. Publication reserves capacity first,
so a failed native creation cannot leave a valid-looking map object. Cleanup is
bound as a consumer. Descriptor region construction requires the admitted
descriptor/resource pair used by the command planners. Native handles remain
inside the adapter boundary; no host payload is retained. Host tests exercise
allocation/native failure and retry, descriptor conflicts and query subsets.
This verdict covers ownership/admission code, not hardware support or the whole
shared native texture factory.

## Texture copy contract

`src/contracts/texture_copy.zig`: verified within file scope.

Examined all public types, aspect selection, mip/physical-block bounds, strict
versus native stride modes, empty-copy behavior, checked arithmetic and tests.
The pure validator allocates nothing and owns canonical footprint/error meaning;
`required_bytes` exposes its existing result. Extent validation is shared with
full-aspect texture-to-texture admission, which does not pretend to be a buffer
plane upload. Overflow, compressed edge and depth/stencil restrictions remain
explicit. Aggregated/core/full suites exercise consumers of the internal type
addition. The descriptor passed here is an already admitted resource, not a
substitute for device creation/feature validation. Multiple invalid inputs may
now report extent/alignment failure before aspect failure; no acceptance is
relaxed and no serialized error field changes.

## Spatial port

`src/backend/ports/spatial.zig`: verified within file scope.

Examined the complete vtable/context wrapper, prepared spatial operation and
identity, provider adapter, bundle construction and application routing. Removed
an unused import and documented provider lifetime and borrowed identity strings.
The forwarding method preserves returned reports and errors without allocation,
resource retention, fabric selection or native-state knowledge. The generic
provider returns explicit unsupported status; no hidden host simulation occurs.
Existing composition tests exercise the port bundle. No additional mirror test
was added for the direct forwarding statement. The Cerebras front door remains
the qualification authority; this review establishes no accelerator execution.
