# Independent dot-loop experiment

Component: WGSL compiler / SPIR-V emission
Intent: preserved
Boundary effects: versioned SPIR-V arithmetic policy, build options, compiler tests; no package API or model changes.

## Hypothesis and repair

The existing multi-dot policy preserves loops to protect accumulated rounding.
The retained Qwen Q4 shader also places independent local-array elements inside
such a loop. Its driver output retains dynamic indexing; requesting unrolling
can enable scalarization without a reduction between iterations.

The candidate recognizes a bounded unsigned induction, unit increment, fixed
local f32 array, same-element reads, and a single element assignment. Unknown
control flow, other writes, pointer aliases, numeric index conversions and
effectful calls retain the previous protection. It recognizes IR structure,
not source names, model identities or WGSL text patterns. Source arithmetic and
robust bounds are unchanged. This remains a driver hint, not a numerical proof.

## Experiment boundaries

`timing/policy.json` freezes a fresh-process balanced comparison of predecessor
Doe, candidate Doe and Node webgpu/Dawn. Each process loads the same retained
Node-qualified Qwen Capsule through the same installed Doppler archive. Models
remain resident. Timing surrounds the awaited public rerank call; independent
oracle evaluation and JSON writing happen afterward. All warmups and timed
calls must satisfy the original oracle. Profiling and experimental interposers
are disabled. Package creation, model loading, and cleanup are outside the
reported query scope and must not be inferred from its latency.

`timing/comparison.json` owns raw-derived statistics and comparison checks.
Full result files retain receipts and independent comparisons. The before/after
GPU observer cannot detect every short-lived client. Recorded model operations
are not native dispatch tracing. This is a local application diagnostic, not a
release claim, a complete search application, or broad GPU qualification.

## Checks and rejected alternatives

`accepted-host.log` records compiler and aggregate tests plus the isolated native
build. `attention-regression.log` compares the retained attention fixture with
its prior model output. Compiler negative cases exercise recurrences, aliases,
side effects, bounds and index conversions. No old numerical tolerance changed.

Earlier diagnostics live beside this directory: pass timestamps and per-dispatch
pass splitting localized the loss but perturb execution; driver shader dumps
suggested the Q4 loop distinction. Forced subgroup size, narrower barrier stage
scope and merely removing DontUnroll did not demonstrate a useful improvement.
Those diagnostic interposers and environment changes are not production changes.
Explicit Unroll motivated this bounded compiler candidate.

`timing-incomplete-analysis-hardening/` retains an interrupted attempt, excluded
from comparisons. Accepted packages, benchmark acceptance thresholds, original
WGSL, model formats, signed release history and frozen source oracle remain
unchanged. Existing rendering regression and Node embedding admission remain
separate unresolved work. No additional systematic review credit is granted.

## Reproduction

Use the exact retained assets named in `timing/policy.json`; missing assets must
fail rather than selecting substitutes. Build with pinned Zig and an isolated
prefix, then use a fresh output directory for `timing/run.py`. Its absolute local
paths are deliberate retained-environment inputs. `timing/compare.mjs` validates
all results before aggregating. These scripts are repository evidence tooling.

## Finalization

`timing/` is the complete initial three-variant cohort. `confirmation/` is a
separate balanced self-comparison after conservative pointer-alias rejection.
These cohorts are not pooled. `identities.json` distinguishes their libraries;
the Q4 shader's SPIR-V is byte-identical across that final safeguard.

The first pointer-alias fixture reached an existing unsupported local-pointer
emission path and failed (`final-host.log`, `alias-debug.log`). The corrected
regression tests actual parser/sema/IR output directly, where the new analysis
runs, and asserts rejection (`alias-fixed.log`). It does not claim local-pointer
SPIR-V support was repaired. Earlier failed and interrupted attempts remain
separate from accepted checks and complete timing cohorts.

Compiler policy version, migration and scope are documented in
`docs/shader-compiler-architecture.md`. Binary sizes and hashes live in
`identities.json`; build logs expose elapsed compile time and maximum RSS.
Those incremental build observations are not a controlled clean-build comparison.
No CPU-work or peak-residency improvement is claimed from query latency.

## Outcome

Both complete cohorts show lower candidate query median and tail latency than
their predecessor controls. The initial incumbent comparison still favors Dawn.
Use each cohort's own `comparison.json` for numbers; do not mix their samples.
All admitted calls pass the original source oracle and cleanup checks.

`diagnostics.tar.gz` retains the earlier comparator, profiling, shader capture,
and rejected-experiment scripts and observations, excluding native executables.
The original local directories remain available; extract this archive beside
this directory to inspect retained paths on another checkout. `compiler.patch`
and `identities.json` bind the candidate implementation and library evidence.

Next: investigate the remaining full matrix-compute cost and repeated-pass
synchronization under the same independent oracle. Further workloads and full
package qualification remain necessary before changing accepted binaries.
