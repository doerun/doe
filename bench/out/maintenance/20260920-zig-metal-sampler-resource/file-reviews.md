# Sampler repair and resource-port examinations

Base: `5e0e4dd969ea88bc3755e268a193f6c6b5c0fb59`.
The [triage](triage.tsv) consolidates the preceding batch's open scopes by
failure mechanism and responsible owner. It does not replace their file reviews.

## `src/backend/metal/metal_deferred_release.zig`

Re-read the complete file: ring saturation/drain, descriptor equality, acquisition,
logical release, eviction, uncached transfer and teardown. The cache owns a native
reference; clients own counted loans, or an explicitly uncached reference. No
native acquisition is published after failure. The ring remains a retirement
mechanism whose callers must first complete GPU uses; it cannot infer completion.

Repaired comparison omission in both key and factory arguments. Distinct comparison
modes no longer reuse one sampler. A nonempty cache is bound to its originating
device; cross-device misuse fails before reuse or allocation. Deinit clears that
identity. The recording test exercises create failure, reference overflow, reuse,
separate devices, full-cache uncached ownership, idle eviction and actual teardown.
The shared bridge repair supplies canonical enums, comparison mode and call-local
descriptor ownership to this caller and ordinary native sampler creation.

Verdict: `needs_changes`. The preceding retirement finding remains: successful
host ownership tests do not establish that callers release resources only after
native completion/device-loss retirement. Run the physical retirement campaign,
including sampler use followed by caller release before completion. Neither
sequential device cache tests nor source inspection prove concurrent GPU behavior.

## `src/backend/metal/metal_resource_commands.zig`

Re-read every sampler/texture lifecycle operation and map publication path.
Sampler creation and destruction flush before replacement/eviction; insertion
failure returns the logical loan or releases an uncached native reference. Those
rules now consume the repaired cache and bridge instead of owning another enum
translation. The whole-file review remains separate from that supporting repair.

Verdict: `needs_changes`. Remaining texture write admission still lacks complete
payload/row/image/mip bounds and descriptor compatibility. Texture query still
ignores expected depth one and several other optional descriptor expectations.
Required native failures must survive retirement. Resolve these at the texture
resource owner and reuse canonical format/layout facts in copy paths, rather
than adding validation to the generic port. The sampler semantic finding is
resolved in source and host checks; physical sampling remains unqualified.

## `src/backend/ports/resource.zig`

Read the whole port and followed `app/runner.zig` through
`ports/provider_adapter.zig` into Metal, Vulkan and D3D12 prepared-resource routing.
Inspected their texture-write, sampler and map-command callees as supporting
context. Those files do not receive automatic review credit.

The port allocates nothing and directly propagates the provider's error union or
report. Borrowed context/vtable lifetime, call-scoped payload borrowing, distinct
resource retention and provider-owned report strings are now explicit. Handles
are identities, not ownership transfers. Successful return is operation success
under the selected queue policy, not a general GPU-completion receipt. The
map_async command is a temporary-buffer command probe, not the ordinary WebGPU
callback API. Callers receive only the neutral operation/report contract and do
not need backend-private fields.

Verdict: `needs_changes` across the requested interface-and-implementations
examination. Metal texture_write reaches native memory access without validating
the complete payload; Vulkan texture_write builds a native region without using
its checked buffer-copy footprint routine. D3D12 uses a typed validated layout
and retains its staging allocation through its draining wait, but that observation
does not qualify every D3D12 failure path.

The report adapter also synthesizes submit_count from dispatch_count. Vulkan
texture_write submits real work with dispatch_count zero, so the returned report
cannot truthfully identify observed submissions. Queue completion/status is a
separate open owner; no success report can repair a hidden native failure.
Preserve these findings while fixing the resource implementation and the canonical
execution receipt. Do not add a universal interpreter or backend branches to the
port. Next never-examined queue file: `src/backend/ports/spatial.zig`.

## Supporting edits and tests

Changes to the ordinary native sampler caller, extern declarations, Objective-C
bridge/header/stub, manifest and test inventory are targeted supporting work,
not additional complete-file reviews. The physical proof test's bodies compile
against host stubs and are explicitly skipped on non-Metal hosts; Apple SDK
compilation and execution remain required. No directory, relationship or subsystem
completion is granted by these file examinations.
