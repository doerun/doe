# Compilation benchmark file review

Version-1 maintenance receipt for the complete examination of
`runtime/zig/bench/compiler/bench_compilation.zig`, its forwarding entrypoint,
and the affected build entries against predecessor `fcda31bfd`. This receipt
records diagnostic tool correctness; smoke timings are not performance evidence.

## Findings and implementation

The previous entrypoint imported its sibling implementation outside Zig's module
root. [Original build failure](build-before.log) and
[direct-root build](build-root-fixed.log) establish the repair. The unused
forwarder was removed after searching its active consumers. The ledger retains
its reviewed source fingerprint and marks that path retired. Other benchmark
entrypoints still require their own review.

[Before cases](before-cases.tsv) and [diagnostics](before-diagnostics.log)
reproduce the zero-sample abort, duplicated argument allocation leak, successful
invalid-source run, ineffective filter, and unescaped external metadata.
Characterization used the predecessor implementation with only its build root
corrected. The original source hash is in [source-before.tsv](source-before.tsv).

Arguments now borrow process-owned storage. Input admission rejects invalid
sample counts, missing/unknown arguments and targets, ineffective filters,
unbound external metadata, and invalid UTF-8 metadata. The external source is
read into owned storage before output is opened; names, tiers, and the external
shader descriptor no longer need separate allocations. Output and compilation
failure unwind each owner and retain the original error. Failed translations
cannot silently remove workloads from an apparently successful process.

The compiler translation calls remain the timed boundary, including their
internal cleanup. Output-buffer allocation, statistics, JSON string escaping,
reporting, and source reading remain outside that boundary. Warmup and timed
loops use the same translation function. The shared target enum is exhaustive;
private functions and namespaces follow Zig naming conventions. Statistics use
wide accumulators for mean and squared differences, and summary addition is
checked. Empty samples and empty summaries fail explicitly.

## Output migration

NDJSON version `2` removes `compilerLoc`, whose literal was not an observation.
Physical `sourceLines` no longer counts a phantom line after a final newline,
and empty input has no physical lines. Names and tiers are JSON escaped. Other
successful field names, units, target/corpus order, and emission byte counts
retain their meaning. Existing version `1` artifacts stay intact.

The row contract is [the registered schema](../../../../../config/zig-compilation-bench.schema.json).
[Actual rows](contract-rows.json) are a JSON array of successful NDJSON rows
retained for the schema gate, not another source of benchmark policy. Each
row kind is closed. [Negative schema cases](schema-negative.tsv) reject stale
versions, invented counts, zero iterations, mixed row kinds, and unknown fields.
Whole-process success and complete workload coverage remain separate obligations.
The existing comparison reader accepts the current rows, including escaped
names. Its comparison/fairness decisions were not changed or certified here.

## Acceptance

- [Debug CLI cases](after-cases.tsv), [optimized CLI cases](release-cases.tsv),
  and [CLI verification](cli-checks.log) check process status, row identities,
  output sizes, JSON schema, and the existing comparison reader. Debug allocator
  reports reproduce and check cleanup; missing ReleaseFast reports alone cannot
  establish ownership correctness.
- [Unit tests](unit-tests.log), [proof-enabled tests](proof-enabled-tests.log),
  and [final combined tests](final-tests.log) exercise allocation failures,
  source errors, sample arithmetic, physical lines, and escaped metadata.
  [Initial test output](unit-tests-initial.log) retains the test-author error:
  the compiler's original rejection is `UnexpectedToken`, not `InvalidWgsl`.
- [Output protection](output-protection.log) verifies that an input-read failure
  leaves a pre-existing output file untouched.
- [Structural gates](structural-gates.log) preserve existing formatting,
  ownership, import, ABI, bridge, source-line, and test-inventory policy.
- [Source hashes](source-files.tsv) and [binary hashes](binaries.tsv) bind the
  reviewed implementation and isolated executable builds. `SHA256SUMS` binds
  retained evidence. Install folders remain local reproducible outputs.

Reproduce from `runtime/zig/` with `zig build test-bench-compilation`, also with
`-Dlean-verified=true`; build `bench-compilation` using Debug/ReleaseFast and an
isolated `--prefix`. From the repo root, run the retained
`verify_cli.py <installed-binary> --label <fresh-label>`. The output-error test
uses Linux `/dev/full`. No GPU workload or calibration was run.

## Component handoff

Component: Zig compilation benchmark, diagnostic row schema, and build entry
Intent: preserved
Acceptance evidence: linked builds, CLI runs, ownership tests, schema, and hashes
Boundary effects: diagnostic NDJSON version migration and explicit tool errors;
no compiler implementation, runtime policy, accepted package, or speed claim change
