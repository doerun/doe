# Metal staged-write benchmark file review

Version-1 maintenance receipt for the complete examination of
`runtime/zig/bench/entrypoints/metal_staged_write_bench.zig` against
`9b8371db4`. This is source and diagnostic-tool verification on Linux, not a
physical Metal correctness or performance receipt.

## Findings and repair

The [captured regression](capture-before.log) extracts the predecessor's byte
comparison unchanged and passes an inconsistent capture size. The original
parallel-slice loop panics under Debug. Capture lengths now fail explicitly
before byte access in every build mode. Mismatch accounting retains the first
absolute byte offset and aggregates later unequal bytes without replacing it.
The oracle algorithm, workload constants, GPU execution sequence, and valid
receipt fields remain unchanged.

Arguments borrow process-owned storage; the CLI's existing bounds and error
names are preserved with actionable context. Sampling bounds, handle identity,
and input-pattern constants have names; equivalent word counts derive from
one definition where applicable. Main returns its existing process status
through Zig's supported error-union byte return, allowing deferred argument and
allocator cleanup on nonzero oracle outcomes.

Serialization receives an allocator and output file explicitly. Zig's standard
JSON allocation helper preserves `OutOfMemory`, and deferred release covers
both successful writes and file errors. Tests sweep allocation failures and
exercise `/dev/full`; their constructed failure receipts are unit fixtures,
not GPU observations.

## Validation and limits

[Predecessor CLI cases](before-cases.tsv), [Debug cases](debug-cases.tsv), and
[optimized cases](release-cases.tsv) preserve accepted/rejected arguments and
Linux `UnsupportedPlatform` behavior. No JSON GPU receipt is emitted on this
host. [Debug tests](tests-debug.log), [optimized tests](tests-release.log), and
the [final combined checks](./final-checks.log) cover the actual private
helpers and canonical executable/test module. Later final checks include the
output-failure regressions added after the initial unit runs.
[Proof-option checks](./proof-tests.log) and
[empty-filter checks](./filter-empty.log) exercise build wiring;
[source hashes](source-files.tsv) and [binary hashes](binaries.tsv) identify the
exact inputs. Executables were installed into isolated evidence directories.
`SHA256SUMS` binds retained files, excluding reproducible install directories.

The [macOS build attempt](../metal-compute/build-macos.log) could not find Apple
frameworks on this Linux host. Linux constant-folds the unsupported-platform
branch; these checks do not compile or exercise every macOS-only runtime call.
A compatible Apple host must run the unchanged workload suite's normal and
corruption-probe commands before these tools establish physical Metal evidence.
Accepted Linux package inputs retain their [recorded hashes](accepted-inputs.tsv).

The [tool contract](../../../../../runtime/zig/bench/entrypoints/README.md)
explains retained device-buffer ownership, timer scope, and compatibility.
Existing schemas, workload commands, trace/replay contracts, process gates,
and performance ineligibility remain unchanged. No global style rule needed
revision; this file applies the existing allocator, bounds, naming, and cleanup
rules. Directory cohesion and cross-file consolidation remain separate reviews.

Reproduce from `runtime/zig/` using `zig build test-bench-metal-staged-write` in Debug
and ReleaseFast, also with `-Dlean-verified=true`; build `bench-metal-staged-write`
with an isolated `--prefix`. On Linux, run
`python3 bench/out/maintenance/20260914-zig-file-reviews/metal-compute/verify_cli.py <installed-binary> --tool staged-write --label <fresh-label>`
from the repository root. The [CLI verifier](../metal-compute/verify_cli.py)
checks process errors only and refuses unsupported verification hosts.

## Component handoff

Component: Zig Metal staged-write benchmark and canonical build test entry
Intent: preserved
Acceptance evidence: linked regression, unit and CLI checks, source hashes,
shared structural gates, and documented missing Apple frameworks
Boundary effects: explicit tool error on inconsistent capture size; serialized
receipts and runtime behavior retain their existing contracts
