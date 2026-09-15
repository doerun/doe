# Benchmark entrypoints

These repository-only entrypoints retain their existing executable names and
workload contracts. They do not expand public package or backend support.

## Metal correctness benchmarks

`metal_compute_bench.zig` runs the exact-output kernel oracle;
`metal_staged_write_bench.zig` verifies deferred writes after an explicit flush.
Their workload commands, expected process statuses, and receipt schemas remain
owned by [the workload suite](../../../../config/doe-workload-suite.json).
The fixed device profile is a policy input for these lanes, not an observed
adapter identity. Diagnostic wall timing includes host preparation and oracle
work; these tools are ineligible for performance claims.

From `runtime/zig/`, the CPU-only contract tests are:

```bash
zig build test-bench-metal-compute test-bench-metal-staged-write
```

These tests check argument admission, capture-size rejection, byte mismatch
accounting, allocation failure, output failure, and unsupported-host admission.
They do not create a Metal device. Build filters use `-Dtest-filter`; inspect the
executed test count. Actual Metal execution still requires a compatible Apple
host and the workload suite's normal and corruption-probe runs.

The entrypoints own process arguments through execution. Sessions own retained
device buffers until teardown; unique per-iteration handles therefore retain
device storage across the run. Expected and captured host bytes belong to each
iteration and remain live through completion and comparison. Serializers use
the caller's allocator and preserve allocation and file-output errors. Main
returns the existing status code through Zig's entrypoint contract so deferred
cleanup runs on successful corruption rejection and failed oracle outcomes.

Unexpected capture lengths now return `CaptureSizeMismatch` with expected and
observed sizes before reading bytes. Previously the parallel-slice loop relied
on build-mode safety checks. Valid receipt fields, versions, sampling bounds,
kernel inputs, completion requirements, and expected exit codes are unchanged;
there is no serialized-field migration. The [compute review](../../../../bench/out/maintenance/20260914-zig-file-reviews/metal-compute/README.md)
and [staged-write review](../../../../bench/out/maintenance/20260914-zig-file-reviews/metal-staged-write/README.md)
record validation and platform limitations. Existing process, trace, schema,
and release gates retain their authority.
