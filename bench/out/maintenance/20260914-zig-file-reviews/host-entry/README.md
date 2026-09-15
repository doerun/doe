# Host benchmark file reviews

Version-1 maintenance receipt for the host hotpath entrypoint and its support,
case, and scalar lexer files against predecessor `0aa73c533`. Each complete file
examination has its own ledger entry. Directory organization and relationships
still require their separate reviews. The smoke runs validate diagnostic tool
behavior; their timing values are not evidence of an application improvement.

## Findings and repair

The [original build](build-before.log) rejected sibling imports outside the
entrypoint module root. Moving the entrypoint beside its helpers makes the
[existing executable build](build-root-fixed.log) without changing Doe's module
boundary or its executable name. The old path remains retired in the ledger.
The canonical build now exposes a test target using that executable's module,
options, libc dependency, and test filter.

[Predecessor CLI cases](predecessor-cases.tsv) reproduce successful zero-sample,
missing-value, and unknown-option runs. Argument parsing now borrows process
storage and rejects invalid input explicitly. The arena's lifetime covers all
borrowed strings, datasets, result arrays, and synchronous artifact output.
The entrypoint uses the standard array-list append operation directly; its
generic forwarding helper was removed after examining consumers.

The [queue allocation failure](queue-failure-before.log) leaked previously
allocated nodes when a later C-allocator allocation failed. An error cleanup
walk now releases that prefix. Trace scratch and corpus builders release
intermediate allocations for ordinary allocators as well as the entrypoint
arena. Serialization borrows its allocating writer's buffer, and restores the
original allocation error erased by that writer's interface. Actual file-write
errors remain unchanged. [Initial tests](tests-initial.log) retain the erased
`WriteFailed` failure that prompted this repair.

The [predecessor artifact](before.json) used the timed XOR accumulator as the
coordination output comparison. Even sample counts canceled equal repeated
outputs to zero. Independent invocations outside timing now establish those
output comparisons. The timed accumulator remains a distinct observation.
The sampler rejects empty input, uses a monotonic timer, and reports an
unavailable ratio when either observed mean is zero. Sampling scales and the
numeric relative-error denominator floor now have shared named definitions.

The [lexer regression](lexer-before.log) reproduces scalar reference drift for
increment, decrement, and shift-assignment operators. The reference now covers
their tags and spans, with independent expected-token checks. Lexer cases reject
different token streams before measuring; token work counts cannot silently be
copied across a mismatched pair. The original fixed corpus remains unchanged.
Agreement with the runtime lexer is not complete WGSL conformance evidence.

## Contract and validation

The [host tool contract](../../../../../runtime/zig/bench/host_hotpath/README.md)
documents ownership, exact timing boundaries, scaled effective sampling, target
metadata, and artifact migration. Artifact version `2` adds diagnostic
classification and timing identity, uses nullable ratios, and corrects
coordination output identity. No external active report consumer was found;
historical artifacts retain their original version and interpretation.
Existing process gates remain authoritative. Runtime trace/replay contracts,
verification policy, and provider promotion rules were not changed.

- [Debug CLI checks](debug-cases.tsv) and [optimized checks](release-cases.tsv)
  validate failure taxonomy, output routing, unchanged corpus/work identities,
  integer statistics ordering, and odd/even coordination results.
- [Actual output](after.json) validates against the registered schema;
  [negative cases](schema-negative.tsv) reject stale versions, claim promotion,
  unknown fields, empty samples, and negative ratios.
- [Combined tests](combined-tests.log) cover the host benchmark and both prior
  compiler benchmarks after the shared build change. [Proof-enabled tests](proof-tests.log)
  and [empty-filter execution](filter-empty.log) exercise the new build target's
  option and test-selection wiring.
- [Structural checks](structural-gates.log), [schema gate](schema-gate.log), and
  [documentation checks](documentation-checks.log) preserve repository policy.
- [Source hashes](source-files.tsv), [predecessor hashes](source-before.tsv),
  [binary hashes](binaries.tsv), and [preserved inputs](accepted-inputs.tsv)
  identify the evidence. `SHA256SUMS` binds retained files; install directories
  remain local reproducible outputs and are excluded from the receipt.

Allocation-failure tests exercise ordinary allocators; successful arena cleanup
alone would not establish helper ownership. Numeric scalar/SIMD association
differences remain visible in output hashes and error envelopes. Fixed variant
order, uncalibrated local timing, and compiled-target metadata cannot support
physical application or provider superiority claims. No GPU workload ran.

Reproduce from `runtime/zig/` using `zig build test-bench-host-hotpaths`, also
with `-Dlean-verified=true`; build `bench-host-hotpaths` in Debug and ReleaseFast
using an isolated `--prefix`. From the repository root, run
`python3 bench/out/maintenance/20260914-zig-file-reviews/host-entry/verify_cli.py <installed-binary> --label <fresh-label>`.
The output-error check uses Linux `/dev/full`. The CLI verification initially
expected `InvalidCharacter` for a negative unsigned integer; Zig's original
error is `Overflow`, as retained in the CLI stderr. That expectation was
corrected without changing runtime error handling.

## Component handoff

Component: Zig host benchmark, diagnostic artifact schema, and build entry
Intent: preserved
Acceptance evidence: linked builds, CLI runs, allocation and output checks,
schema validation, structural gates, and source/artifact hashes
Boundary effects: diagnostic output version migration and explicit tool errors;
accepted runtime/package inputs retain their recorded hashes
