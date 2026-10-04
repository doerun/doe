# Paired direct-WGSL control

## Disposition

Close the unsigned power-of-two acceleration candidate without promotion.
Preserve the qualified compiler/adapter delivery prototype. Numerical admission
passed, but a stable A/A control and an attributable performance benefit remain
unestablished. This does not prove that the transformed shader is intrinsically
slower or equivalent.

The [shader diff](shader.diff) replaces an unsigned division by a literal power
of two with a right shift, and unsigned remainders with masks. It removes no
loads, stores, dispatches, drawing or floating-point computation. It would reduce
GPU work only if the downstream browser/driver compiler leaves those integer
operations expensive. Final native instructions were not captured; source
strength reduction is insufficient evidence that instructions were eliminated.

## Matched execution and stopping

The [frozen plan](frozen-plan.json) was written before measurement and binds its
runner digest. This version of the [runner](../../../../bench/executors/run-browser-wgsl-output.mjs)
launches an independent browser process for each declared session. Every process
executes all permutations of original, disabled and transformed labels. All arms
occupy each position equally, and each directed predecessor relationship occurs
equally. Process offsets rotate permutation order, and timestamped/plain phase
order alternates across processes. The configured warmup gives every arm the
same work before measured trials.

All labels use the same pipeline options, initial particles, timestep, geometry,
precision, camera, draw, resource creation, completion and readback boundaries.
Original and disabled WGSL bytes are identical. No Worker or adapter is created.
Fresh resources are used per trial; persistent driver caches are not reset.
[Environment](environment.json) retains browser/adapter identity and completed
warmup counts. WGSL generation finishes before measurement; browser pipeline preparation stays
measured separately and inside application latency. Every position and velocity
is checked against the independent CPU oracle.

The stopping rule fixes the browser-process count and trial orders. The entire
configured run completed without retries. No additional sampling was selected
from the observed sign, and unfavorable rows remain. The prior context-only,
undeclared-warmup experiment remains in [its original report](../direct-output/README.md).

## Paired results and uncertainty

[Statistics](paired-statistics.json) retain every within-cohort paired absolute
difference and log cost ratio. Process means receive equal weight. A seeded
percentile bootstrap resamples independent browser processes, never pooled
frames, and reports intervals for absolute differences and geometric cost
ratios. See [the analysis owner](../../../../bench/browser/wgsl_output_statistics.py)
and its [tests](statistics-tests.log). The small fixed process sample supports
descriptive uncertainty, not tail claims or universal equivalence.

- A/A: practical control stability is inconclusive in the recorded timing
  scopes. Intervals extend outside the workload's declared practical margin.
  Some timestamped differences favor a label even with identical source; this
  cannot be optimizer benefit. The run does not establish a repeatable material
  label bias either.
- Original/transformed and disabled/transformed: intervals span gains and
  losses. No correct program improvement can be attributed to the rewrite.
- Delivery: the previously qualified final archive and its slower assisted-path
  results remain separate. This check does not assign that loss entirely to
  Worker overhead or justify reintroducing delivery for promotion.

Post-run [process](post-run-process-snapshot.txt) and
[GPU](post-run-gpu-snapshot.txt) snapshots show an existing CPU-active Node process
and automatic GPU performance policy. These were sampled after the benchmark;
they are investigation clues, not synchronized telemetry or established causes.
No unrelated process or GPU policy was changed. Context/process isolation alone
cannot eliminate shared-machine scheduling, thermal, or driver-cache effects.

## Next bounded work

Keep this candidate closed. Preserve the A/A check as a measurement gate. Profile
an independent application with recoverable shader cost, then motivate a general
transformation with the work it would eliminate after downstream compilation.
Qualify its emitted WGSL offline only when the identical-program control is
stable at the declared practical margin. Do not expand packaging, backends or
demo features, and do not rescue this rewrite by selecting favorable cohorts.

## Reproduce

```sh
DOE_PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs \
DOE_BROWSER_PACKAGE_ROOT=/path/to/verified/extracted/package \
node bench/executors/run-browser-wgsl-output.mjs
python3 -m bench.browser.wgsl_output_statistics /path/to/output
```

The desktop supplies its display authorization. The
[versioned settings](../../../../config/browser-compiler-output.json) own warmup,
orders, fixed stopping and uncertainty parameters. Compared with settings version
one, version two makes processes independent, declares warmup and balances all
trial/phase orders. Old evidence retains its own settings. The compiler/package
interface and particle mathematics are unchanged. [Manifest](manifest.json)
binds source, contract, shaders, settings and retained rows.

Component: benchmark/evidence owner.
Intent: preserved. Acceptance evidence: raw sessions, paired uncertainty, schemas
and independent numerical oracle. Boundary effects: browser remains GPU owner;
compiler and public package behavior unchanged. Acceleration remains unproven.
