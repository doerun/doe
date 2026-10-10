# Doe performance contract

This page defines measurement and comparison mechanics only. Performance's
place in the product priority order and downstream-application strategy lives
only in [`thesis.md`](thesis.md).

## Purpose

Performance is part of the promoted Node/Bun product contract. A speed claim is
eligible only after correctness, structural equivalence, runtime identity, and
failure checks pass.

`config/gates.json` classifies performance as advisory repository-wide. Each
promoted developer-wedge workload must additionally declare a blocking
performance decision in its promotion contract.

## Measurement order

1. Validate both outputs with an independent oracle.
2. Prove both sides executed the same declared work.
3. Verify provider, backend, adapter, driver, cache, and fallback identity.
4. Verify timing-scope symmetry.
5. Measure the complete user-visible operation.
6. Evaluate latency, memory, failures, retries, and fallbacks together.
7. Emit compare and claim artifacts.

Failure at an earlier step makes timing diagnostic.

## User-visible operations

Promoted Node/Bun evidence should include cold and warm forms of:

- inference prefill and decode;
- embeddings and vector operations;
- upload through readback;
- shader and pipeline creation;
- prepared pipeline reuse;
- process and device memory.

Internal phase timing remains useful for diagnosis. It cannot rescue an
end-to-end loss.

## Comparison classes

Declare the comparison class before freezing a workload. Equivalent application
work does not require identical internal implementation work. Missing required
execution invalidates a comparison; verified elimination of unnecessary work may
constitute the advantage.

### Unchanged-application replacement

Require identical application inputs, requested work, output and numerical
requirements, validation obligations, hardware/driver environment, and complete
timing boundaries. Preserve upload visibility, ordering, completion, readback,
resource lifetime, and failure semantics. Keep the application and its shaders
unchanged. Internal allocations, copies, native submissions, cache strategies,
and generated GPU programs may differ when they preserve these obligations.

Record actual internal paths and explain eliminated work with execution and
independent output evidence. Different readback mechanisms or shared-memory
access replacing staging can be a legitimate advantage on the qualified hardware;
they do not establish a portable or isolated operation-speed claim. A missing
internal phase may reflect elimination, but a zero value alone never proves it.
Absent required dispatch, completion, or readback remains an invalid comparison.

Give both implementations equivalent application-level reuse opportunities,
initial state, input history, warmup policy, and cache population opportunities.
Measure cold initialization and preparation separately from declared resident
operations, retain both, and prohibit one-sided precomputation or costs moved
outside the declared boundary. Identical internal cache layouts are not required.

### Fixed-operation or shader experiments

Freeze the command/dispatch shape, repetitions, effective paths, preparation and
cache conditions needed to isolate the named transformation. Declare exactly
which compiler or runtime behavior may change; generated instructions need not
be identical when code generation is the treatment. Matching effective readback
paths is required when readback implementation is a control. A path difference
outside the declared treatment is diagnostic, not an isolated operation win.
Selected operation timing owns an operation-speed claim; switching to wall time
after a loss cannot rescue it. A component win does not establish application value.

## Shared comparability requirements

Both classes require independent oracles, actual provider/backend identity,
explicit fallback, complete timing scopes, matched sampling and normalization,
raw samples, lifecycle checks, and predeclared acceptance thresholds. Audit
unexplained zero phases and implausible wins before accepting any result. Do not
invent symmetric costs for a verified eliminated phase, or hide a required phase
because instrumentation did not capture it. Retain failures and adverse tails.
Normalized workload-unit wall must contain selected operation timing for each
side; a negative gap is a normalization or scope failure.

This clarification is prospective. Existing frozen contracts, executable gates,
thresholds, and historical verdicts retain their meaning. A new campaign must
encode its class and treatment in its versioned workload contract and have gates
that verify those obligations before claiming a result. If an existing gate only
supports fixed-operation parity, extend that contract and its checks in the new
campaign; prose is not permission to bypass a failing gate or relabel old results.

## Statistical requirements

- Report p50, p95, and p99 for release claims.
- Use enough independent samples for the declared tail percentile and disclose
  the estimator and variance.
- Set a practical winning margin larger than observed benchmark noise.
- Repeat evidence across independent process runs.
- Treat unusually large speedups as fairness-audit triggers.

The sample floors and reliability policy belong in
`config/benchmark-methodology-thresholds.json`, not prose. A configured floor
that cannot support its declared percentile must fail methodology review.

## Claim artifacts

Every promoted result must retain:

- raw run artifacts for both products;
- comparison and claim sidecars;
- workload and config hashes;
- output-oracle result;
- runtime and hardware identity;
- timing-scope and structural-equivalence verdicts;
- memory and failure summaries;
- fallback and retry state.

Public prose should link `reports/claim-index.json`, not transcribe percentages.

## Optimization loop

1. Reproduce one named end-to-end loss.
2. Attribute it with phase receipts and profiles.
3. Change one runtime or compiler contract.
4. rerun correctness and reliability gates;
5. rerun the matched comparison;
6. retain the change only when the user-visible result and tails remain valid.

Dated investigations belong in status archives, not this contract.
