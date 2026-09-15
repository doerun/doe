# Runtime compile-report file reviews

Version-1 maintenance receipt for the forwarding benchmark entrypoint,
`src/compiler/wgsl/runtime/runtime_compile_report.zig`, and the dedicated test
root. The implementation was examined completely, including argument admission,
source ownership, translation metadata, emission, structural observations,
serialization, and failure cleanup. The forwarding file retains its original
delegation; its consumed implementation supplies the repair.

## Findings and repair

[Initial CLI observations](before-cases.tsv) reproduce successful invalid JSON
for quoted shader names, leaked overwritten argument allocations, and ignored
unknown or incomplete options. [Baseline cases](baseline-cases.tsv) also show
that an incompatible emit request could fail after another output was written.

Arguments now borrow process-owned storage until synchronous execution finishes.
An exhaustive option enum rejects unknown and missing arguments; metadata must
be nonempty and valid UTF-8 where the existing schema requires strings. Target
compatibility is checked before translation or emission. Parse errors unwind
the process allocator instead of bypassing cleanup through direct exit.

A typed report uses Zig's JSON serializer and the existing translation timing
type. Shader names and source paths are escaped correctly. Source, output
buffer, translated metadata, and serialization buffers each retain an explicit
owner and release path. The existing report fields, version, compiler options,
translation calls, structural observations, and phase timing boundaries remain
unchanged. This is a repair within the existing schema, not a field migration.

## Test discovery and validation

The [initial test target](tests-initial.log) exited successfully without running
tests: a reference from the forwarding root did not register tests inside its
separate named compiler module. That run did not establish allocation safety.
The dedicated `test_suite_runtime_compile_report.zig` imports the implementation
inside its own test module. [Focused execution](tests-focused.log) runs the
new regressions; [registered execution](tests-registered.log),
[proof-option execution](proof-tests.log), and
[optimized execution](release-registered.log) run the discovered implementation
and dependency tests. [Empty selection](filter-empty.log) checks filter wiring.

Allocation failure is swept through actual source reading, MSL and SPIR-V
translation, metadata cleanup, and report writing. Serialization tests preserve
quoted/newline metadata and allocation causes. `/dev/full` checks file-error
propagation and cleanup. Unit fixture values are not GPU observations.

[Final Debug CLI checks](final-cases.tsv) and [optimized CLI checks](release-cases.tsv)
validate the actual report against its existing schema, compare both emitted
targets byte-for-byte with the predecessor, exercise quoted names and paths,
and retain compiler/output errors. Invalid source and mixed emit-target
requests preserve the checked pre-existing output file. These comparisons
establish equivalence for the retained shader, not complete compiler coverage.

The [WGSL and structural checks](wgsl-structural-checks.log) exercise the existing
compiler suite and repository gates. That initial combined run still used the
empty report test target; the later [final combined run](final-tests.log) uses
the dedicated root with the existing benchmark tests and structural gates.
[Consumer tests](consumer-unittest.log) exercise the existing comparison reader;
[the actual consumer result](consumer-result.json) comes from reading an escaped
report and validating the real emitted SPIR-V. [Direct SPIR-V validation](spirv-validation.log)
checks the retained output independently. No Tint comparison, Apple shader
compilation, physical GPU run, or application performance claim is made.

The attempted pytest invocation in [consumer-tests.log](consumer-tests.log)
failed because pytest was unavailable. The existing unittest consumer suite
ran successfully; the schema test functions were invoked directly, and actual
CLI reports were schema-validated by [the retained verifier](verify_cli.py).

[Source hashes](source-files.tsv), [predecessor inputs](source-before.tsv),
[binary hashes](binaries.tsv), and [preserved package inputs](accepted-inputs.tsv)
bind the scope. `SHA256SUMS` binds retained artifacts; install and temporary-test
directories remain reproducible local outputs. The architecture manifest's
module decision is refreshed for the compiler diagnostic owner. Its review
fingerprint remains separate from the hierarchical file verdicts.

Reproduce from `runtime/zig/` with `zig build test-runtime-compile-report`, also
with `-Dlean-verified=true` and `-Doptimize=ReleaseFast`; build
`runtime-compile-report` using an isolated `--prefix`. From the repository root,
run the retained `verify_cli.py <installed-binary> --label <fresh-label>` after
recreating the baseline with `--label baseline --baseline` from predecessor
`9f621831f`. Existing baseline reports and emitted files are retained.
The [entrypoint contract](../../../../../runtime/zig/bench/entrypoints/README.md)
documents the unchanged schema and explicit tool errors. Process gates,
runtime trace/replay contracts, accepted package policy, and physical
calibration retain their existing authority.

## Component handoff

Component: WGSL runtime compile-report tool, forwarding entrypoint, test root
Intent: preserved
Acceptance evidence: linked CLI, schema, allocation, emitted-byte, consumer,
WGSL, and structural checks with exact source and artifact identities
Boundary effects: explicit malformed-input errors and valid JSON escaping;
compiler output and runtime execution contracts retain their meaning
