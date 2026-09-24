# Qwen reranker HEAD confirmation

Component: Vulkan shader ownership and local application evidence.
Intent: preserved.
Acceptance evidence: `build.log`, `allocation-tests-prepared.log`, `comparison/comparison.json`.
Boundary effects: test coverage only; no new production behavior or package change.

## Disposition

The requested ownership correction and one synchronization candidate already
landed before this task. `identities.json` resolves the starting commit, records
the clean working tree, and verifies the retained implementation and libraries.
The original batch is indexed at
[`../20260923-shader-owner/README.md`](../20260923-shader-owner/README.md).
Its ownership correction remains; its synchronization optimization was rejected.
The uniform-read visibility repair remains separately identified as correctness
work. This confirmation introduces no further optimization candidate.

The deliverable of a repeatable material application advantage remains unmet.
Read the fresh `comparison/comparison.json` independently of every older cohort.
Do not pool the historical predecessor/Dawn comparison with the subsequent
Doe-only compiler confirmation or this run.

## Inspected and changed

Inspected shader selection, the shared pipeline registry's immutable words and
reference ownership, pending artifact staging/discard, capture allocation failure,
collection retry, cache collision/replacement, prepared-state release, and teardown.
The existing tests cover staging replacement, failed retain, capture failure,
independent snapshot bytes, caller/program release, and final registry cleanup.
Existing common artifact tests retain failed collection for retry.

The added assertions extend the physical pipeline collision regression: after
preparation, select A, B, then A with the runtime allocator rejecting allocations.
Each pending capture must refer to the active immutable owner, use storage
distinct from caller words, and preserve exact shader bytes. Allocator calls,
allocated bytes, and attempted allocation failure are checked. The complete
test still dispatches and reads the independently expected integer outputs.

No compiler, shader, synchronization, application, public API, runtime policy,
schema, or release-gate behavior changed. Existing process acceptance requirements
continue to apply. Source-layout ownership is unchanged. This is targeted
regression coverage, not systematic review credit.

## Executed evidence

- `build.log`: aggregate ReleaseFast tests and isolated HEAD native build.
- `allocation-tests-prepared.log`: aggregate tests including the added allocation checks.
- `allocation-tests.log`: retained failed test setup, which incorrectly treated
  a finished recording's private cache as preparation of the ordinary cache.
  The corrected test prepares ordinary selection before forbidding allocations.
- `allocation-results.json`: allocation observations and their deliberately
  narrow scope; shader-copy absence is established from ownership and source,
  without an application-wide copy counter.
- `identities.json`: source, compiler, library, archive, Capsule, oracle, and
  input identity checks; installed Doppler files matched the retained archive.
- `vulkaninfo.log`, `loaded-libraries.json`, and `process-*-libraries.txt`:
  host driver and process library observations. A library being mapped does not
  establish that every mapped ICD executed; adapter receipts identify the GPU.
- `comparison/`: balanced fresh processes, the unchanged public awaited rerank
  operation, original numerical oracle, raw receipts, cleanup, GPU boundary
  observations, and comparison replay.
- `comparison/*-resources.txt`: GNU time CPU and peak RSS observations for the
  entire child lifetime, including startup, model loading, warmup, oracle,
  serialization, and teardown. These are not query-only CPU or GPU residency.
- `shader-costs.csv` and `shader-costs.json`: reanalysis of the prior owner-profile
  cohort, family invocation counts, cumulative GPU time, instrumented-wall
  fractions, and complete dispatch sequences. No historical samples enter the
  fresh comparison.

The shader table explicitly marks absent family-linked current Doe/Dawn ISA
comparisons. Historical driver dumps belong to an earlier compiler cohort and
cannot establish current register, scratch, or dynamic-indexing differences.
Pass splitting perturbs synchronization and short Dawn timestamps are quantized.
The table therefore does not causally apportion ordinary application latency.
The already-rejected synchronization experiment is the sole second candidate;
no scalarization candidate was added.

## Reproduction and limits

From `runtime/zig`, build with the pinned compiler and an isolated prefix:

```sh
zig build test dropin -Doptimize=ReleaseFast --prefix /absolute/isolated/prefix --summary all
```

The retained `comparison/run.py` and probe have explicit local prerequisites.
For another run, copy them to a new directory, update the directory and library
paths together, freeze hashes, and run the Python script followed by its
`compare.mjs`. Existing output directories are never reused. Build and GPU test
work must finish before application comparisons start. Diagnostic interposers,
forced subgroup selection, Node options, and identity tracing are rejected.

New JSON/CSV files here are local diagnostic projections, not promoted receipt
contracts. `shader-costs.json` names its historical input paths and hashes;
`process-resources.json` preserves whole-process scope. `checksums.json` binds
the retained evidence and source diff. Raw receipts are losslessly compressed in
`raw-receipts.tar.gz`; extract in this directory before replaying the comparison.

Whole-application allocation counts, query-only CPU, peak GPU residency, full
native dispatch/readback equivalence, CPU exclusivity, and current family-linked
ISA attribution remain unavailable. Boundary GPU observations cannot exclude
every transient client. No second-workload speed claim is justified without a
first-workload advantage. Additional workloads, Metal, D3D12, browser/Fawn,
complete search, package promotion, and release qualification were skipped.
Accepted binaries and application code were preserved.

The next product decision should be tied to an adopter's consequential execution
problem and a competent incumbent control, including feasible incumbent fixes.
Compiler depth and fewer allocations alone do not establish a reason to replace
the runtime or acquire its owner. This negative result remains evidence against
the current application-advantage hypothesis.

An initial build invocation used the wrong working directory for its output
directory creation and failed before Zig ran. The corrected invocation produced
`build.log`; it did not overwrite an accepted library.
