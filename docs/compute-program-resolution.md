# Compute program measurement diagnosis

This repository-only workflow investigates variation in the existing ordinary
WebGPU application executor. It uses the accepted qualified package and frozen
application semantics. A diagnostic result cannot accept a runtime candidate or
replace the calibration and application gates.

## Reproduce

```bash
python3 -m bench.runners.run_compute_program_resolution \
  --output bench/out/compute-program/<new-runtime-resolution-run>
python3 -m bench.gates.compute_program_resolution_gate \
  --report bench/out/compute-program/<new-runtime-resolution-run>/report.json
```

[`compute-program-resolution.json`](../config/compute-program-resolution.json)
selects the historical calibration, extended warmup, sample partition, and V8
sampling interval. The calibration policy owns accepted package selection and
free-space admission. The existing tail policy owns application selection,
diagnostic process repetitions, timed invocations, and host-event capacity.
No acceptance threshold changes through this workflow.

## Physical treatments

The original and extended-warmup treatments use ordinary execution. Their order
alternates across fresh processes. Only the declared warmup changes; inputs,
shaders, dispatches, completion, readback, numerical acceptance, and timed sample
counts remain identical. Warmup outputs are retained and checked. A resident
fixture must have independent expected outputs for the entire sequence; the
executor rejects insufficient coverage instead of resetting state.

Host API instrumentation and V8 profiling run as separate treatments after the
ordinary cohort. Host instrumentation changes call overhead and can change JIT
behavior. V8 profiles include startup, the application, numerical oracles, file
writes, runtime calls, and idle observations. Neither treatment supplies ordinary
performance confirmation. V8 self samples can locate a host/native boundary;
they do not separate native CPU execution from blocking inside that call.

The current executor verifies every process before starting its successor.
Those checks and source hashing occur outside application timing but can affect
the surrounding host state. Child identities and boundaries retain execution
order. Host observations describe a shared machine, not exclusive hardware or
fixed CPU/GPU clocks. Builds and other heavy verification must run outside the
physical cohort.

## Analysis contract

`historical-blocks.tsv` and `blocks.tsv` preserve each process, application,
treatment, metric, consecutive block, invocation range, sample count, and block
median. Every timed invocation belongs to a block. `historical-summary.tsv` and
`summary.tsv` weight processes equally and retain the first/last block medians,
median within-process ratio, and direction counts. They are descriptive ordered
observations, not confidence bounds or an automatic steady-state decision.

| Field | Meaning |
| --- | --- |
| `wallMs` | The executor's complete application invocation interval |
| `cpuMs` | Process CPU consumed during that interval |
| `upload`, `encode`, `submitWait`, `readback`, `total` | Original application receipt scopes |
| `gpuMs` | Observed compute-pass timestamp interval; unavailable when disabled |
| `outsideReceiptMs` | Invocation wall minus the receipt's total interval |
| `unassignedReceiptMs` | Receipt total minus its named host phases |

GPU time overlaps host execution and waiting. It is never subtracted from the
host phase decomposition. Timing differences preserve their signed value;
negative values are not clamped into apparently valid zero cost.

The V8 projection retains function/source identity, self-sample count, original
signed timestamp-delta sum, and negative-delta count. Negative profiler deltas
remain visible in both the raw profile and projection. Delta sums are profiler
observations, not independently measured CPU time. Host asynchronous settlement
rows overlap synchronous method rows and must not be added to them as separate
work.

## Identity and migration

The additive policy and report schemas introduce a diagnostic artifact family.
Existing calibration, candidate, application, and runtime contracts keep their
versions and verdicts. Reports bind the evaluator inputs, retained source bytes,
exact qualified package, child reports, profiles, and numerical outputs. The
review gate replays numerical/work checks and recomputes ordered projections;
it rejects changed treatments, missing processes, reused executions, and dropped
host events. Earlier failed diagnostic attempts remain separate evidence.

Historical replay must retain the evaluator bytes used by the physical cohort.
If the reviewer has subsequently gained stricter checks, retain that reviewer
separately and mount the original inputs read-only for replay. Record both
identities and the replay command. Restoring frozen inputs must not replace the
new reviewer's checks or rewrite the original report. An interrupted physical
attempt cannot supply missing processes to a completed cohort.

Warmup changes require a new versioned evaluation procedure and fresh accepted
baseline calibration before candidate decisions. A smaller warmup effect alone
does not establish sufficiently precise regression bands, an optimization, or
an advantage over another provider.
