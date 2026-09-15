# Compiler benchmark tools

These are repository diagnostics. Their output is not a provider comparison or
application performance claim; governed comparisons belong to `bench/`.

## Stage benchmark

From `runtime/zig/`, build `bench-shader` with an isolated `--prefix` when
preserving installed artifacts, then run its `bin/doe-shader-bench`. The CLI
accepts `--iterations`, `--warmup`, `--filter`, and `--out`. Defaults and the
sample capacity remain named constants in [bench.zig](bench.zig). A filter
selects an exact built-in shader name. Repeated options use their last value.
The argument owner retains strings through execution; parsing borrows them.

Invalid numbers, missing values, unknown options or shader names, and sample
counts outside the supported range fail before opening the output file.
Warmup may be disabled explicitly. Compilation, allocation, and output failures
terminate with their original errors. Consumers must check process exit status:
earlier rows in a partial output file do not establish a successful run.

Successful NDJSON rows retain their existing names, order, units, and fields.
Analysis covers parsing, semantic analysis, IR construction, and configured
validation. End-to-end stages also cover rewriting and emission. Emit-only
stages borrow one prepared module. Output buffer allocation, reference-module
preparation, deallocation, statistics, and reporting are outside the recorded
stage time. Warmup calls the same stage runner and discards its timings.
Samples are sorted without outlier removal; percentile indices retain the
existing integer-rank convention. These raw timings require the owning
comparison harness's metadata and methodology before any performance claim.

The [file-review receipt](../../../../bench/out/maintenance/20260914-zig-file-reviews/compiler-stage/README.md)
records migration from ignored/normalized invalid arguments and skipped stage
failures to explicit errors. It also binds the runnable predecessor used for
row/byte-count parity and distinguishes that check from emitted-code correctness.
The shader corpus and proof selection are unchanged.

`zig build test-bench-shader` exercises argument admission, sample arithmetic,
original source failures, and allocator-failure cleanup. It honors
`-Dtest-filter` and `-Dlean-verified`; a filtered run qualifies only its selected
tests. The retained CLI checks additionally exercise output failure and complete
corpus rows using the built executable.
