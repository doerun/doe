# Compiler stage file review

Version-1 source and CLI receipt for `runtime/zig/bench/compiler/bench.zig`,
reviewed completely against predecessor `723dd140f`. This is diagnostic tooling
verification; retained timing rows are smoke output and support no speed claim.

## Examination and repairs

The predecessor could not build the stage benchmark: the proof source belonged
to both `doe` and a separate `lean_proof` module. [Build failure](build-before.log)
records that boundary. Characterization used only the import repair, preserved
as [source text](import-fixed-source.txt), then built the original benchmark
logic in [build-import-fixed.log](build-import-fixed.log). The final build uses
`doe.verification.leanProof()` and removes the unused separate build dependency.
The previous build-file review established graph equivalence and selected
native builds, not compilation of every tool; this exercised consumer exposed
an additional failure and reopens that file's review until its delta is recorded.

[Before cases](before-cases.tsv) record the zero-sample abort, ignored missing
value, successful empty filter, and repeated string arguments.
[Duplicate argument diagnostics](before-duplicate.stderr) and
[output failure diagnostics](before-output-failure.stderr) reproduce lost
allocation ownership. Configuration now borrows process-owned arguments,
rejects malformed or out-of-range choices before opening output, and keeps
last-value selection without allocating another string owner. Defaults and
valid-input corpus contents retain their definitions.

The prepared reference module now has immediate deferred cleanup. Compilation
and allocation failures remain errors instead of being converted into missing
rows. Warmup and timed invocation share an exhaustive stage runner; analysis
warmup no longer performs a rewrite absent from its timed stage. Emission
selection has one owner, stage enumeration derives from its enum, private
helpers follow the style guide, and output takes a concrete file writer.
The proof-pattern-referenced function name remains stable. The statistic sum
uses a wide accumulator and empty samples fail explicitly.

Timer reads precede parser, semantic, and IR cleanup. Reference preparation,
output-buffer allocation, deallocation, statistics, and output remain outside
recorded stage time. This is a scope inspection, not a timing parity or
performance result. Compiler implementations, emitted formats, and proof policy
were not changed.

## Acceptance and migration

[Debug CLI cases](after-cases.tsv) and [optimized CLI cases](release-cases.tsv)
verify process status, complete row coverage, unchanged successful row fields,
and absence of allocator leak reports. The corpus order and all non-timing
fields, including emitted byte counts, match the runnable predecessor.
Byte-count agreement does not establish emitted-code correctness. Debug output
failure checks exercise tracking allocation; absence of a ReleaseFast allocator
report alone would not establish cleanup.

[Canonical tests](canonical-tests.log), [proof-enabled tests](proof-enabled-tests.log),
and [filtered tests](filter-tests.log) exercise argument rejection, statistics
bounds, original source failures, and every allocation failure across reference
construction and each stage. [Structural gates](structural-gates.log) retain the
existing ownership, ABI, formatting, test-inventory, bridge, and line checks.
The named test target shares the benchmark module and accepts the build's test
filter and proof mode.

The repo-only CLI now rejects invalid values that previously selected defaults
or capped counts, unknown arguments and filters that previously produced
apparent success, and stage failures that previously skipped rows. Successful
row serialization has no new fields. Consumers must require zero process exit
status as well as the expected complete workload rows. This does not change a
public package contract or promote the exploratory SPIR-V gate compilation
path into an emitter-artifact guarantee; that consumer already requires a
separate binary-emission contract.

Reproduce from `runtime/zig/`:

```bash
zig build test-bench-shader --summary all
zig build test-bench-shader -Dlean-verified=true --summary all
zig build bench-shader -Doptimize=Debug --prefix <debug-output> --summary all
zig build bench-shader -Doptimize=ReleaseFast --prefix <release-output> --summary all
```

From the repository root, run the retained `verify_cli.py <binary>` on Linux;
its output-failure case uses `/dev/full`. Run a fresh label when retaining new
results. Source hashes and installed executable hashes live in
[source-files.tsv](source-files.tsv) and [binaries.tsv](binaries.tsv). Output
folders are local reproducible build products and are not committed.

## Component handoff

Component: Zig compiler benchmark tooling and its build entry
Intent: preserved
Acceptance evidence: linked tests, CLI cases, compiler builds, and source hashes
Boundary effects: explicit diagnostic CLI errors and named benchmark tests;
no compiler implementation, public package, runtime policy, or speed claim change
