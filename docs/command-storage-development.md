# Command storage development

This is a bounded example of build-checked runtime policy and application
evaluation. The runtime owns command storage. Benchmark tooling owns calibration
and candidate decisions; no evaluator is needed to use ordinary WebGPU.

## Policy and diagnostic contract

[`native-command-storage-policy.json`](../config/native-command-storage-policy.json)
continues to own the device's maximum idle command-array capacity. Live loans,
resource-reference arrays, driver allocations, and GPU residency are outside
that bound. The pool transfers an exclusive empty array to an encoder, accepts
returns only from the same allocator, and frees unsuitable returns. Device
references must outlive outstanding loans.

[`contracts/command_storage.zig`](../runtime/zig/src/contracts/command_storage.zig)
owns typed build parsing and measurement identities, units, and scopes.
Compilation exhausts the metric enum when generating diagnostic metadata.
Missing metadata is a compile error; this does not prove counter accuracy or
resource lifetime. Native ownership, allocation-failure, and concurrency tests
remain independent requirements.

The additive build policy
[`native-command-storage-observation.json`](../config/native-command-storage-observation.json)
selects `ordinary`, `counters`, or `timed`. It does not change the retention policy.
Ordinary has no diagnostic state or snapshot. Counters observe actual pool
transfers and ordinary command-recording reservations. Timed also observes
contended mutex acquisition, including the cost of observation itself.

Capacity growth is separate from a reuse miss and from an allocator call.
Reservation counters cover `doe_command_recording.reserve`; private fused
constructors and reference-list allocations are outside that scope. Retained
capacity and its high-water observation describe host command storage, not
process memory or GPU residency. Counters saturate and disclose overflow;
unmeasured lock values and failed clock observations remain unavailable.

After the last device reference releases its idle storage, diagnostic builds
can append a `command_storage_released` record to the existing explicit
`DOE_PROGRAM_IDENTITY_TRACE_PATH` journal. The row binds device/process identity,
operation identity, exact policy hashes, element size, capacity, and typed
measurements. It is a device-lifetime summary, not a per-invocation trace.
The fixed output buffer and saturating counters bound observation storage.
Absent or incomplete journal output is missing evidence, never a zero-cost
result. No new public JavaScript API or command interpreter is introduced.

## Calibration before candidate decisions

```bash
python3 -m bench.runners.run_compute_program_calibration \
  --output bench/out/compute-program/<new-command-storage-calibration-run>
python3 -m bench.gates.compute_program_calibration_gate \
  --report bench/out/compute-program/<new-command-storage-calibration-run>/report.json
```

[`compute-program-calibration.json`](../config/compute-program-calibration.json)
selects the accepted qualification and repeated cohorts. Both labels install the
same archives. Fresh processes alternate execution order; successive cohorts
reverse their initial order. The original startup and tail policies own sample
counts and regression limits. Nothing is tuned to admit a preferred candidate.

Calibration passes its referenced tail policy explicitly to the executor's
`--policy` argument. The default remains the canonical repository policy.
Each cohort retains the selected policy and derived invocation policy. Review
requires both to match calibration, including warmup, timed samples, work,
and thresholds; a calibrated candidate cannot select a different procedure.
This additive repository-only CLI contract allows a separately retained warmup
revision to qualify against identical accepted archives before it is promoted.
Existing schema versions and original policy bytes remain unchanged.

The calibration retains the existing regression checks in both label directions.
Its metric rows retain apparent improvements as well as losses. The report
binds inputs, package bytes, logs, raw outputs, and available boundary hwmon
temperature observations. Storage policy version 2 checks free space before each
cohort and shares identical completed numerical outputs through hash-verified
hard links. Every original path and byte remains available to replay. Atomic
report replacement preserves the last valid report if a write fails. Existing
per-process Linux DRM admission still rejects
observed foreign GPU activity. Boundary sampling does not establish an isolated
machine, and builds must not run during the physical measurement cohort.

Calibration version 3 uses the separately versioned
[`compute-program-decision.json`](../config/compute-program-decision.json).
Each matched pair contributes one ratio for each process cost and each
within-process invocation percentile. The executor records the actual child
identity, report hash, and start/completion boundaries. Replayed processes,
missing pairs, overlapping pairs, and reversed execution order fail admission.
Repeating invocations cannot increase the number of independent observations.

The decision layer computes non-interpolated binomial order-statistic intervals
for the median paired ratio, with a Bonferroni correction across applications,
metrics, and both execution orders. The orders remain separate. The interval
construction is based on the sign test; see
[NIST median confidence limits](https://www.itl.nist.gov/div898/software/dataplot/refman1/auxillar/mediancl.htm).
The configured family error budget applies to one complete assessment, assuming
independent pairs with a common median within each order stratum. Boundary host
observations retain CPU pressure, load, frequency governors, affinity, and
available temperatures. They neither prove statistical independence nor isolate
the host. This workflow currently requires Linux child-process identity sources.

`consistent` means all finite adjusted A/A intervals include the identity ratio.
It establishes no improvement and does not assert tight equivalence. The
separate `promotionResolutionPassed` field requires every interval to fit within
the unchanged regression band in both directions. Missing bounds or unresolved
precision cannot permit promotion. A consistent but imprecise calibration can
admit an experiment that ends in rejection or an inconclusive result.

These intervals describe typical paired processes. A within-process tail ratio
is not a confidence bound on pooled invocation tails or population startup p99.
All original pooled and process-quantile guards remain necessary for candidate
acceptance, including extreme observed samples. The gate verifies input
freshness, actual executions, package equality, numerical results, and native
work before recomputing the uncertainty assessment. Historical procedure
versions keep their original verdicts; a new procedure requires a fresh accepted
baseline run before evaluating a candidate.

## Bounded experiment and confirmation

Use an isolated source snapshot and a declared candidate policy. Retention
disabled is an existing supported policy value suitable for a control; it is
not presumed to improve performance. Preserve the accepted archives, workload,
numerical oracles, evaluator, and thresholds. Compile and test lifetime behavior
before physical work. Diagnostic modes may explain resource behavior but cannot
confirm an application advantage.

An eligible candidate requires retained-package qualification, an ordinary
application comparison against the accepted predecessor, and transfer without
retuning. The candidate manifest binds the hypothesis, policy bytes, source
manifest, build measurements, qualified archive, and exact compiled library.
The wrapper archive must match the accepted package. The runtime, evaluator,
oracles, fixtures, and limits remain separate frozen inputs.

```bash
python3 -m bench.runners.run_command_storage_experiment \
  --candidate <retained-candidate.json> \
  --calibration-report <fresh-calibration>/report.json \
  --output bench/out/compute-program/<new-command-storage-experiment>
python3 -m bench.gates.command_storage_review_gate \
  --report bench/out/compute-program/<new-command-storage-experiment>/report.json
```

The runner measures the declared development and transfer applications in
ordinary mode. Uncertainty can establish a regression or rule out the required
useful-work improvement; either rejects the candidate. Unresolved effects are
inconclusive. A possible acceptance must pass every unchanged raw guard,
demonstrate improvement in both orders and transfer applications, exclude
regressions, and have adequate calibration resolution. It then requires a
separate complete confirmation series before becoming an `accepted-proposal`.
The review gate recomputes that decision from physical outputs and checks fresh
child identities across the entire evaluation and confirmation sequence. Reused
processes, overlapping executions, or reversed scheduling cannot provide an
independent confirmation. Its
`--require-accepted` option distinguishes valid failure evidence from an accepted
proposal. No outcome automatically stages, publishes, or replaces the runtime.
The separate evidence replay and `--execution-only` checks can also be composed
for the same unchanged report. Execution identity alone cannot assert acceptance.

Transfer applications are held out from candidate tuning, but are known to the
evaluator and calibration. This is distinct from an unfamiliar external
application or an independent operator's reproduction. Incumbent superiority
also requires a separate comparison.

Build, native, calibration, and bounded-candidate evidence for the initial
implementation lives under
[`20260912-command-storage-contract`](../bench/out/compute-program/20260912-command-storage-contract/).
The completed uncertainty procedure, qualified policy control, ordinary
application experiment, and retained decision are indexed in the
[completion record](../bench/out/compute-program/20260912-command-storage-completion/README.md).

## Migration

Retention policy version 1 and ordinary WebGPU signatures remain unchanged.
The observation policy is an additive versioned repository contract. Calibration
policy/report version 2 adds bounded working-space admission and lossless output
retention; version 1 remains readable as historical evidence. It does not change
sampling, thresholds, or numerical acceptance. Version 3 adds the uncertainty
policy, actual process identity, host observations, and a separate promotion
resolution result. The legacy maximum-violation count is absent in version 3;
raw violations remain recorded and keep blocking candidate acceptance. New
candidate and experiment schemas describe bounded declarations and reviewable
decisions. The native journal schema adds a distinct diagnostic
event without changing existing execution rows. Legacy journals confer no new
storage observations; old candidate verdicts are not reassessed automatically.
