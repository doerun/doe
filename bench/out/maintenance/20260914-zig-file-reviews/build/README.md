# Build file review

This record completes the file examination of `runtime/zig/build.zig` begun in
`build_file_001`, against predecessor `f3897d28c`. Read scope covers every
declaration and the complete executable, installation, application, platform,
proof/configuration, benchmark, and test graph. Hashes live in
[source-files.tsv](source-files.tsv); this is source/build evidence.

## Findings and resolution

The test filter was passed only to the aggregate suite. The canonical core,
full, D3D12, and WGSL suites now use the same requested filter. The predecessor
[negative filter run](filter-before.log) demonstrates ignored selection; the
[current negative run](filter-after-empty.log) demonstrates empty selection.
[Aggregate/full parser tests](filter-after-quirk.log),
[registered core test](filter-after-core-registered.log),
[D3D12 identity test](filter-after-d3d12.log), and
[registered WGSL test](filter-after-wgsl-registered.log) exercise positive
selection. The initial core quirk and WGSL lexer selections ran no tests:
those modules are not explicitly registered in those lanes, and transitive
imports are subject to Zig's lazy analysis. Empty success never establishes
test coverage. The unfiltered [WGSL suite](wgsl-full.log) remains exercised.

The common libc/platform bridge recipe now has a typed private owner.
Distinct root files, imports, tier types/options, and platform-only tools stay
explicit in the graph. The Metal benchmark recipe differs on Windows and
remains separate. This removes repetition of a shared linking decision without
introducing a generic factory for unlike build artifacts. The unused private
include-path selector had no consumers and was removed.

Required file read failures now identify the path and original error.
[Input error probes](input-errors.tsv) exercise missing input and read bounds
through the actual build module without modifying repository inputs.
Build-arena allocation ownership, quirk parser cleanup, deterministic source
hash ordering, generated declaration ordering, proof selection, policy validation,
and fail-fast configuration ordering were examined. Existing parser allocation
failure tests remain the behavioral check for the public build-parser helpers.

## Verification and limits

[Graph equivalence](graph-equivalence.tsv) compares actual build graph link
objects, C flags, frameworks, libc settings, and generated option bytes across
Linux, Windows, and macOS target configurations with proof embedding on/off.
`capture_graph.py before` was run against the predecessor; `after` against the
changed build. Those configurations are graph checks, not execution or SDK
qualification on Windows or macOS.

The Linux compute and full libraries compile in [native-build.log](native-build.log)
with an isolated installation prefix. Their identities are in
[native-artifacts.tsv](native-artifacts.tsv); binaries are reproducible local
outputs and excluded from the retained source receipt. Canonical tests also run
formatting, source ownership, ABI, line-policy, inventory, and applicable bridge
and import checks. [Preserved inputs](preserved-inputs.tsv) bind the accepted
package and command-storage policy files. No application timing was measured.

Reproduce from `runtime/zig/` with `zig build test-wgsl -j2 --summary all`;
positive filters are the test names stated above. Reproduce the empty selection
with `zig build test test-core test-full test-d3d12 test-wgsl
-Dtest-filter=__doe_review_missing_test__ -j2 --summary all`. Build libraries with
`zig build dropin-compute dropin-full -Doptimize=ReleaseFast -j2 --prefix
<isolated-output-directory> --summary all`. Run `verify_inputs.py` and
`capture_graph.py` from the repository root, using their retained paths. The
probes temporarily create a build module and remove it on exit; do not run them
concurrently with source gates or another probe.

## Component handoff

Component: Zig runtime build and contributor tooling
Intent: preserved
Acceptance evidence: linked logs, graph captures, probes, and source hashes
Boundary effects: consistent test selection and actionable build-input errors;
no runtime policy, serialized field, package, or performance claim changes
