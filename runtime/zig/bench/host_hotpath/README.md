# Host hotpath benchmark contract

This repository-only tool compares local scalar and runtime implementations on
the fixed corpus assembled in `host_hotpath_bench.zig`. It emits diagnostic
observations, not a provider comparison or application speed claim. The
[file-review receipt](../../../../bench/out/maintenance/20260914-zig-file-reviews/host-entry/README.md)
retains predecessor failures, validation, and source identities.

From `runtime/zig/`:

```bash
zig build test-bench-host-hotpaths
zig build bench-host-hotpaths -Doptimize=ReleaseFast --prefix /path/to/isolated-install
/path/to/isolated-install/bin/doe-host-hotpath-bench --iterations 200 --warmup 20 --out /path/to/result.json
```

The executable accepts `--iterations`, `--warmup`, and `--out`; unknown options,
missing values, invalid unsigned counts, and zero timed samples fail. Repeated
options use the last value. Output defaults to stdout. Build-time test filters
apply through `-Dtest-filter`; check the executed count before interpreting a
filtered pass.

## Ownership and timing

The entrypoint arena owns argument storage, corpus data, result arrays, and
serialization storage through synchronous output. Arguments borrow that
storage. General allocator helpers release intermediate allocations on failure
and transfer only their returned slices. The linked-queue variant owns and
releases each C-allocator node, including a partially constructed queue. Ring
storage and flat waiter capacity belong to their benchmark instances; intrusive
links borrow the caller's waiter nodes through each synchronous invocation.

Each timed sample uses `std.time.Timer` around variant invocation and checksum
accumulation. Warmup calls are discarded. Corpus preparation, sample allocation,
statistics, independent output checks, and artifact writing are outside this
scope. Allocations performed by a variant remain inside it. The attention and
queue cases retain their existing scaled sampling recipe, named in
`intensiveCaseSampling`; each variant records its effective sample and warmup
counts. The CLI counts therefore need not equal every case's effective counts.

Percentiles retain the tool's sorted integer-index convention and integer mean;
they are local observations, not a calibrated release decision procedure.
Variant order is fixed. This tool does not measure GPU execution, application
tail latency, or cross-process reproducibility.

## Output migration

The [registered schema](../../../../config/zig-host-hotpath-bench.schema.json)
defines artifact version `2`. It adds explicit diagnostic classification and
timing source/scope. Existing field spellings and case identities remain stable.
The former wall-clock delta is replaced by a monotonic timer. A ratio is `null`
if either mean is zero; unavailable observations are not reported as speedups.
Historical version `1` artifacts retain their original meaning.

`checksum` is the timed XOR accumulator; an even number of identical outputs
can cancel it. Coordination `output_hash` now records a separate invocation's
result instead of that accumulator. Other output hashes retain their original
meaning. Lexer cases check token count and digest agreement before timing and
reject disagreement, so one side's token count cannot describe another side's
different work. The scalar reference is a comparison implementation; agreement
does not establish complete WGSL conformance or independent compiler correctness.

Numeric cases retain both output agreement and absolute/relative differences;
floating-point association can change results. These fields do not supply an
application's numerical acceptance policy. `host` describes the compiled target
and compiled SIMD lane choices, not an independently sampled physical CPU.
Schema validity does not establish complete workload coverage or authorize
promotion of any ratio. Existing process gates and application calibration
remain the acceptance authority for runtime changes.
