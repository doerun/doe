# D3D12 and backend adapter review batch

Batch base: `4da9a6b6db410a4ca909d148267f77d4fb0e11f8`.
The user-selected batch size and exact file outcomes are recorded in
[scopes.tsv](scopes.tsv). [File examinations](file-reviews.md) retain each scope's
responsibility, ownership, fixes, open findings and next action. The append-only
[ledger](../../../../runtime/zig/reviews/log.json) owns current review history;
[queue.tsv](../../../../runtime/zig/reviews/queue.tsv) remains its derived view.
An examined file with open findings is `needs_changes`, not verified. This batch
contains file passes; no directory or relationship pass inherits completion.

## Implementation

D3D12 map reads now declare their read range and release native storage through
failure paths. Vertex and normalized-texture footprints use corrected sizes;
constant-buffer admission checks bounds before alignment. Native render objects
reserve retention capacity before acquisition, deferred recording releases on
failure, replacement preserves the old pipeline until success, and bundle errors
abort recording. Indirect argument storage accommodates both draw shapes.

Texture writes now copy the provided data, validate and repack source layouts,
address mip/array/volume subresources, preserve resources through completion,
and use the registry allocator at cleanup. Samplers write real descriptors and
reuse released slots. Depth and surface replacements are transactional. The
adapter capability registry serializes access. These repairs do not close the
separate resource/binding/presentation findings in the file notes.

Metal capture checks native buffer length and waits before copying to independent
allocator-owned storage. Failed flushes retain pending-work accounting. The
internal buffer-length bridge is implemented, declared, stubbed and registered.
The Vulkan pipeline-cache adapter now names its runtime dependency explicitly.

The style guide and charter boundaries remain applicable without edits. Tests
exercise production helper bodies using recording native adapters where physical
backends are unavailable. Tests were explicitly added to the existing generated
inventory; generated roots were regenerated. Module-decision hashes were updated
mechanically and grant no review credit.

## Contract and receipt compatibility

No public serialized field or schema version is added. The Metal length query
and D3D12 write metrics are internal interfaces; corresponding callers and bridge
manifest change together. Invalid descriptors, unknown bound handles, close
failure and bundle recording errors remain failures instead of partial success.

Existing texture-write receipts now separate encoding from native submission and
waiting. Render submission timing includes Execute/Signal and reports host
submission cost even when completion is deferred. Existing build identities must
keep earlier receipts distinguishable; historical results are not reinterpreted.
No accepted package, calibration procedure, threshold or performance claim changes.
The blocking/advisory gate policy in `docs/process.md` is unchanged.

## Acceptance evidence

- [aggregate-final.log](aggregate-final.log): unfiltered host suite, formatting,
  source-layout/import, test inventory, WebGPU ABI and bridge-manifest checks.
- [d3d12-release-fast-final.log](d3d12-release-fast-final.log): D3D12-focused host
  suite with debug safety removed; executed/skipped counts remain in the log.
- [windows-compile-receipt.txt](windows-compile-receipt.txt): Windows Zig test
  executable compiled and linked with the native C bridge, using `--test-no-exec`.
  [windows-build.log](windows-build.log) preserves the earlier compile/link
  success followed by the expected inability to execute a Windows binary here.
- [native-constants-receipt.txt](native-constants-receipt.txt) and
  [native-constants.c](native-constants.c): independent native-value assertions
  against the toolchain's Windows headers and pinned WebGPU header. The documented
  Doe stencil-resource alias is compared with its canonical DXGI resource value.
- [schema.log](schema.log) and [doc-links.log](doc-links.log): schema and local
  documentation-link checks.
- [spec-diff.log](spec-diff.log): the broader spec-diff gate could not run because
  its canonical Chromium checkout headers are absent. The native-value probe
  checks this batch's constants but does not clear that separate gate.

Earlier checkpoint logs retain development attempts, including a wrong test
expectation and the initially unregistered Metal bridge symbol. They are not
acceptance results. Physical Windows/Metal execution, driver validation, native
texture round trips, presentation, latency and performance qualification remain
unperformed. The queue retains open findings rather than treating host compilation
as evidence that these backend paths are complete.

## Reproduce and continue

With pinned Zig 0.15.2 on PATH, from the repository root:

```bash
(cd runtime/zig && zig build test --summary all)
(cd runtime/zig && zig build test-d3d12 -Doptimize=ReleaseFast --summary all)
zig cc -target x86_64-windows-gnu -std=c11 -c bench/out/maintenance/20260919-zig-batch32/native-constants.c -I runtime/zig/vendor/webgpu-headers -o /tmp/doe-batch32-native-constants.obj
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref 4da9a6b6db410a4ca909d148267f77d4fb0e11f8
python3 runtime/zig/tools/review_log.py --check --base-ref 4da9a6b6db410a4ca909d148267f77d4fb0e11f8
```

The Windows compilation receipt retains the exact compiler command. Its generated
build-options path comes from `zig build test-d3d12 -Dtarget=x86_64-windows-gnu
--verbose`; regenerate that path for a fresh checkout, then compile with
`--test-no-exec` instead of interpreting a foreign-binary run failure as a test.

Prioritize the open D3D12 pipeline/binding and real-resource copy findings, with
native capability/query/presentation and the lost Vulkan write region kept visible.
Do not advance their statuses through hash refreshes. The next never-examined file
following this batch is `file:src/backend/metal/metal_async_runtime.zig`; this is
separate from the open repair work and stale earlier reviews.

Component: Zig native backends and native/backend adapters.
Intent: preserved.
Acceptance evidence: commands and retained artifacts above; open gates and physical
limitations are stated explicitly.
Boundary effects: internal native ownership, descriptor/layout admission,
submission timing, Metal buffer observation, generated test inventory and review
history. No public schema or architectural authority change.
