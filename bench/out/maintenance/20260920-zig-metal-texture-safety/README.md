# Metal texture safety and spatial-port checkpoint

Batch base: `4eec28db09a06df1ff977e7cddfe7dfdb831e220`.
This follows the [sampler/resource checkpoint](../20260920-zig-metal-sampler-resource/README.md).
File-level conclusions are in [file-reviews.md](file-reviews.md); supporting edits
do not complete their files, directories or relationships.

## Repair and ownership

The shared `contracts/texture_copy.zig` validator now exposes its already-checked
last accessed byte as `Region.required_bytes`. Metal command uploads and copies
consume that authority for format blocks, offsets, row/image padding, selected
mips, array layers, volume depth and checked arithmetic. Temporary copies size
their storage from that footprint, rather than nominal command bytes alone.
Admission precedes allocation and encoder transitions. Existing buffer capacity
and texture identity are checked before reuse.

`metal_texture_resources.zig` owns command texture metadata and publication of
native references. Map capacity is reserved before native acquisition; failure
publishes no entry. Cleanup and deferred destruction release the stored handle.
The descriptor validates required usage and exact identity, including format,
dimensions, mip capacity and natural view shape. Queries check every requested
field; usage expectations require a subset, matching the other command backends.

CPU texture writes retire preceding queued work before replacing bytes. Array
uploads address each slice independently; volume writes preserve mip depth. The
bridge likewise copies array slices individually rather than treating array
length as volume depth. Its shared texture factory preserves the stencil plane,
creates a real one-dimensional texture when requested, and no longer interprets
CopyDst usage as shader-write usage. These factory corrections also affect the
ordinary native caller, without claiming a complete review of that API.

## Contract and qualification boundaries

This is a repair to existing command semantics, not a new serialized field or
policy mode. `Region.required_bytes` and the command texture-map entry are
internal type migrations; all consumers compile together. Public command schemas,
bridge signatures, backend selection and charter authority are unchanged.
Existing correctness, architecture, ABI, format and inventory gates in
`docs/process.md` continue to apply. No accepted package or threshold changes.

Unknown formats, contradictory descriptors and missing required usage now fail
instead of silently creating or reusing a different texture. Multisample command
copies and alternate/cube view declarations return explicit unsupported errors.
Nonempty CPU uploads of depth/stencil planes remain explicitly unsupported;
direct texture copies use a separate full-aspect contract. Empty texture-write
payloads retain their existing declaration-only meaning. Command buffer windows
must cover the actual padded footprint; invalid historical workload declarations
are not grounds to weaken these checks.

Native command-buffer completion/error propagation is still an open dependency.
A void bridge encode or wait is not a success receipt. Host tests establish
admission, ordering of calls, checked storage and failure propagation available
at those interfaces; they do not establish GPU completion or Apple API validity.

## Reproduction and checks

Run from the repository root with Zig 0.15.2 on PATH:

```bash
python3 bench/out/maintenance/20260920-zig-metal-texture-safety/reproduce_predecessor.py
(cd runtime/zig && zig build test --summary all)
(cd runtime/zig && zig build test-core -Doptimize=ReleaseFast --summary all)
(cd runtime/zig && zig build test-full --summary all)
(cd runtime/zig && zig build test -Dtest-filter='Metal repair proof' --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref 4eec28db09a06df1ff977e7cddfe7dfdb831e220
python3 runtime/zig/tools/review_log.py --check --base-ref 4eec28db09a06df1ff977e7cddfe7dfdb831e220
```

- [Predecessor receipt](predecessor-staging.log) records a behavioral assertion
  failure in the extracted predecessor helper, not a compile failure. The
  [reproducer](reproduce_predecessor.py) retains the exact
  [probe](predecessor-staging-probe.zig). Its independently calculated padded
  footprint is also exercised against the new planning path in the runtime test.
- [Aggregate](aggregate-final.log), [ReleaseFast core](core-release-fast-final.log)
  and [full-lane](full-final.log) receipts include the final test and build gates.
  Inline tests cover one-byte-short rejection, compressed blocks, padded layers,
  overflow, invalid mips, descriptor conflicts, acquisition failures and query
  expectations. A recording write bridge verifies distinct slice bytes, no side
  effects for rejected input, retirement before writes and preserved wait errors.
- [Physical availability](physical-availability.log) records explicit Linux
  skips. The retained Metal fixture exercises independent per-layer patterns,
  direct and temporary copies, readback guards and short-input rejection. Run it
  on macOS with the pinned toolchain; actual acquisition failure is a test failure.
  Apple SDK compilation and physical execution remain unestablished here.
- [Schema](schema.log) and [documentation links](doc-links.log) retain repository
  checks. Earlier `*-acceptance.log` files record the source-metadata gate failure
  fixed before the final receipts; they are not passing acceptance evidence.

## Continuation

Repair native completion/error propagation in `metal_async_runtime.zig`,
`metal_runtime_queue_ops.zig` and the bridge, with one owner of retirement status.
Preserve original failures through queue consumers before granting lifecycle or
copy completion. Run the bounded Metal fixture on a physical Apple host, then
extend it to early GPU-object release, device failure and texture-volume cases.
Resource-port submission accounting and Vulkan write admission remain separate
open findings in their existing reviews. The next never-examined queue file is
`runtime/zig/src/backend/ports/surface.zig`.

Component: Metal command textures/copies, shared copy-layout contract and spatial port.
Intent: preserved.
Acceptance evidence: commands and hash-bound receipts above.
Boundary effects: internal texture ownership and layout types, shared Metal
texture factory, test inventory and review history; no public schema or authority
change. No physical Metal, performance or release-readiness claim.
