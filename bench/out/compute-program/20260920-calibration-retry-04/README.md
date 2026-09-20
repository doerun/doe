# Idle-window retry after Metal host validation

## Completed series and precision boundary

The watcher launched the unchanged frozen procedure after its observed quiet
interval and the complete series exited successfully. The
[report](../20260920-command-storage-calibration-window-03/report.json) retains
every declared cohort; no fragment from an interrupted attempt was spliced in.
The [admission replay](admission.log) passed. It independently rechecked frozen hashes,
qualification, numerical outputs, resource/submission work, process order and GPU
observation sidecars before recomputing the uncertainty decision. The
[replay receipt](replay-receipt.md) binds the command, outcome, and retained inputs.

The report's `status=consistent` means its paired-process intervals are consistent
with identical-package observations under the declared procedure. It does not
establish equivalent performance to arbitrary precision. The
[uncertainty assessment](../20260920-command-storage-calibration-window-03/uncertainty.json)
has `regressionBandsResolved=false`, matching
`promotionResolutionPassed=false`. The [precision table](precision.tsv) exposes
each metric and execution-order stratum without changing or combining them.
Heat-diffusion encoding and operation-wall tails remain too imprecise for their
declared regression bands. Other applications also retain unresolved tail and CPU
intervals. Raw cohort guardrail failures remain diagnostic and do not establish a
regression in identical binaries.

`candidateEvaluationAllowed` is permission to evaluate under the existing frozen
procedure, not a promotion verdict. No optimization is accepted here. Before
claiming a small benefit, establish adequate precision and independently confirm
the candidate's raw guardrails and uncertainty requirements. Any revised
measurement procedure must be versioned before a new baseline series; thresholds
must not be loosened to rescue a candidate.

Large raw process/numerical artifacts remain in the local cohort directory.
Retained summary, policy-input and replay receipts do not replace those bytes for
an independent replay. Accepted packages, evaluation code, workloads, reference
outputs and thresholds remain unchanged.

## Launch provenance

The preceding watcher was stopped before launching a calibration so that source
builds and tests would not overlap the frozen experiment. Its suspension receipt
is retained in `../20260920-calibration-retry-03/watch-suspended.json`.

This watcher is an unchanged copy of that scheduling script with a fresh control
directory and fresh observations. It targets the previously unused complete
`../20260920-command-storage-calibration-window-03` cohort. The launch guard checks
unchanged frozen inputs and required free space, then waits for sustained observed
GPU inactivity. The guard does not establish exclusive GPU access or change the
per-process interference rejection policy. It does not stop Doppler or Chrome.

Run from the repository root:

```bash
python3 -u -c 'import runpy; runpy.run_path("bench/out/compute-program/20260920-calibration-retry-04/watch_and_run.py", run_name="__main__")'
```

`watch.log`, `launch-guard.json`, and `watch-*.json` retain scheduling observations.
If launched, `command.json`, `execution-commit.txt`, `launch-working-tree.txt`,
`execution.log` and `execution-result.json` record the independent attempt.
Absence of `execution-result.json` is not successful calibration. No interrupted
cohort is combined with this attempt, and no candidate or accepted package is
changed.

## Acceptance and handoff

Replay from the repository root, with the retained raw cohort and package inputs
available at their bound paths:

```bash
python3 -m bench.gates.compute_program_calibration_gate --report bench/out/compute-program/20260920-command-storage-calibration-window-03/report.json
```

Documentation links passed `python3 -m unittest bench.tests.test_doc_link_coverage`;
see [the check log](doc-links.log). No new evaluator, schema, or threshold was
introduced. Regenerate `precision.tsv` directly from the `rows` in the linked
uncertainty artifact; each column uses the same field name and value.

Component: Benchmark and evidence system; documentation status
Intent: preserved
Acceptance evidence: `admission.log`, `replay-receipt.md`, `doc-links.log`
Boundary effects: no runtime, package, evaluator, or acceptance-policy changes
