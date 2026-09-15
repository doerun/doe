# Backend policy file review

Version-1 maintenance receipt for the complete `src/backend/backend_policy.zig`
examination and the associated build-file recheck. The review covers policy
admission, lane selection, compiled defaults, ownership, file discovery, errors,
and tests. Companion schema, inventory, generated suite, and fixture edits are
tracked as deltas; they do not receive automatic full-file review credit.

## Diagnosed drift and repair

[The predecessor regression](default-parity-before.log) compares every compiled
lane policy with the versioned JSON. It reproduces the Vulkan app lane selecting
`prefer_timeline_semaphore` from the handwritten default table while the file
selects `require_fence_pool`, under the same selection-policy seed. The test
fails on that exact field. The same run also reports stale module-decision
metadata after the new test was appended; that structural failure is separate
from the reproduced policy mismatch.

The default table now derives from `config/backend-runtime-policy.json` during
build evaluation. A field for each canonical `BackendLane` contains the existing
`SelectionPolicy` type. Missing lanes fail before consumers compile. Zig's
build-options serializer emits the complete typed struct into each build view;
the runtime converts generated enum identities by name into the canonical
contract. Reflection walks the actual policy fields instead of adding another
handwritten field map. There is no allocation or file lookup in default policy
selection. Explicit file loading remains a separate operation with an allocator.

The parser and enum declarations retain policy semantics. Removed the duplicate
lane/default/hash table, duplicate backend import, redundant parser arena, and
handwritten enum spelling ladders. Selected policies from a parsed file borrow
its hash; the file-loading API duplicates that hash for its caller. The existing
session owner keeps it alive until after provider destruction. Parsed storage,
file bytes, and the returned hash have separate explicit release boundaries.

## Admission and compatibility

The shared parser now enforces declared root/lane keys, field types, canonical
backend/enum spellings, known lane names, default-lane membership, nonempty policy
identity, no fallback, and strict staged-upload requirements. Every supplied
lane is checked, including unselected lanes. Raw JSON syntax/duplicate errors,
allocation failures, and filesystem failures retain their original causes;
invalid policy semantics use `InvalidRuntimePolicy`.

Relative path lookup retains its existing bounded ancestor search, stopping on
errors other than `FileNotFound`. Absolute paths now refer only to the supplied
path. The path-capacity check uses subtraction to avoid addition overflow. The
policy byte limit has one named definition shared with the build.

The existing schema version and field spellings remain. The schema now requires
`selectionPolicyHashSeed`, matching the loader's existing requirement, and
rejects an empty identity. Files must include the already schema-required
`defaultLane`, name a supplied canonical lane, and remove unknown or malformed
fields. Partial lane files can still be loaded explicitly when their supplied
lanes and default are valid; the build requires every canonical lane. Existing
negative fixtures now supply a valid default so each still exercises its named
failure rather than failing earlier on unrelated metadata.

The repository policy JSON is unchanged. Its current upload defaults and
Vulkan subgroup compatibility defaults retain their meaning. The native path
that uses compiled Vulkan app defaults now honors the file's fence-pool choice;
this is an intentional source behavior correction. Explicit valid file-loaded
choices retain their configured values. Newly built outputs have not replaced
accepted package binaries or been promoted as an application improvement.

## Verification

[Initial post-repair parity](default-parity-after.log) passed the regression
while module-decision metadata was still stale. The later
[focused checks](focused-tests.log) and [core policy suite](core-policy-tests.log)
pass with current structural metadata. New checks sweep allocation failures
through parsing and actual file loading, preserve an escaped owned hash after
parser/file storage is released, reject incomplete build tables, and reject
malformed fields. [ReleaseFast policy checks](release-policy-tests.log) use the
aggregate suite. Policy tests are now explicitly registered in core and aggregate
inventory instead of depending on incidental imports or a platform-named suite.

[Actual build admission](build-admission.tsv) and its
[verifier](verify_build_admission.py) exercise accepted and rejected policies in
an isolated source copy. Inputs and raw build output live under `build-cases/`.
The copy is restored after each experiment; the working policy is not mutated.
[The changed-policy probe](changed-policy-probe.log) compiles and runs actual
policy tests after changing the isolated synchronization choice and adding
quotes, a backslash, and a newline to its seed. This verifies that generated
values follow changed config and survive Zig serialization. The
[probe verifier](verify_changed_policy.py) records its isolated test root and
uses the actual build-options construction; it does not install a runtime.

[Build-table comparisons](build-table.tsv) preserve all pre-existing generated
option bytes and native link recipes across the recorded target/proof matrix;
only the new policy declarations are prefixed. Raw options and recipes are
retained under `build-table/`. These are build-graph observations, not Windows
or Metal execution qualification. The [verifier](verify_build_table.py) uses the
existing retained graph-capture helper and exact predecessor build source.

[Native builds](native-builds.log) compile the compute library, full library,
and runtime executable into an isolated prefix. `binaries.tsv` records output
hashes and sizes. [Benchmark consumer tests](benchmark-consumer-tests.log),
[application consumer tests](app-consumer-tests.log), and
[proof-enabled WGSL tests](wgsl-proof-tests.log) check consumers of the shared
build options. Existing compiler/benchmark/app source is unchanged in this
checkpoint. [Schema validation](schema-gate.log), documentation checks, and the
canonical Zig structural gates retain their authority. No physical GPU workload,
A/A calibration, incumbent comparison, or tail-latency claim is made.

The process documentation now requires this config/default parity. Previously
reviewed files and the local app directory passes are rechecked against that
specific guidance/build change, with their original evidence retained. This
updates their fingerprints; it does not grant coverage to other directories.

## Separate telemetry file examination

The next file, `src/backend/backend_telemetry.zig`, was read completely and
receives a separate ledger entry without source edits. It aliases the canonical
snapshot type, delegates initial values to that contract, and fills selection
identity from explicit inputs. It adds no allocations, caches, casts, timing
measurements, or policy decisions. Selection reason and policy hash are borrowed;
the examined factory/session call path uses a static reason and preserves the
owned hash until provider destruction. Snapshot initialization is not evidence
of an observed adapter. [Its existing test](telemetry-tests.log) checks canonical
initialization through the aggregate suite. Broader telemetry consumers and
contract defaults retain their own pending review scopes.

## Reproduction and identities

Use Zig 0.15.2 from `runtime/zig/`:

```bash
zig build test-core -Dtest-filter=policy -j2 --summary all
zig build test -Dtest-filter='backend runtime policy' -Doptimize=ReleaseFast -j2 --summary all
zig build test-wgsl -Dlean-verified=true -j2 --summary all
zig build test-bench-shader test-bench-compilation test-bench-host-hotpaths test-bench-metal-compute test-bench-metal-staged-write test-runtime-compile-report -j2 --summary all
zig build test-core -Dtest-filter='hexagonal application layer' -j2 --summary all
zig build dropin-compute dropin-full doe-runtime -Doptimize=ReleaseFast --prefix ../../bench/out/maintenance/policy-reproduce/install -j2 --summary all
```

For isolated build checks, copy the retained Python verifiers and
`prepare_scratch.py` into a fresh `bench/out/maintenance/<label>/backend-policy/`
directory at this review's source revision. Run the preparation script, then
`verify_build_admission.py`, `verify_changed_policy.py`, and
`verify_build_table.py`. Preserve original receipt files when reproducing.
The graph comparison reconstructs build source from predecessor `b271907c4`;
all copied runtime/config inputs come from the checked-out review revision.

`source-before.tsv` identifies initial inputs; `source-files.tsv` binds final
source, contracts, tests, build configuration, and documentation. `SHA256SUMS`
binds retained evidence. `accepted-inputs.tsv` confirms accepted binaries and
storage configuration remain intact, and the policy JSON matches its initial
hash. Scratch copies and installed build outputs are reproducible local files.

## Component handoff

Component: Zig backend selection policy and build configuration
Intent: preserved
Acceptance evidence: config/default parity, allocation/lifetime and admission
checks, actual build rejection, changed-config compilation, build-table and
native-build receipts, schema and consumer checks
Boundary effects: compiled Vulkan app defaults now follow configured fence-pool
synchronization; malformed policy admission is stricter; accepted package
binaries, trace fields, native ABI, and promotion/calibration procedure are intact
