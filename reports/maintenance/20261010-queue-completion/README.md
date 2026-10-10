# Queue completion during device cleanup

Unchanged Doppler's buffer pool handles device loss by destroying owned buffers.
It calls `onSubmittedWorkDone()` during that cleanup. Doe's host adapter treated
the call as new work on a destroyed queue and rejected it, producing the retained
deferred-destruction warning. The [captured stack](../../benchmarks/amd-vulkan/20261010-doppler-descriptor-retirement/diagnostics/cleanup-profile.json.gz)
locates the rejection in Doe's shared host adapter, not model arithmetic.

The corrected adapter settles the last requested completion after explicit device
destruction without accessing released native objects. Completion that resumes
after destruction skips native bookkeeping. Calls still fail for invalid new
submissions, and live-device completion errors propagate. The
[WebGPU completion algorithm](https://gpuweb.github.io/gpuweb/#dom-gpuqueue-onsubmittedworkdone)
specifies a completion promise rather than new GPU-work admission.

## Evidence and limits

- [Unit failure before correction](cleanup-unit-before.log) and
  [passing unit checks](cleanup-unit-after.log) cover pending completion, ordering
  across destruction, no native access after destruction, submission rejection
  and live-device error propagation.
- [Physical Vulkan mapping/completion](cleanup-native-after.log),
  [rendering](render-ownership.log), and [command lifetime](command-ownership.log)
  pass with the unchanged repaired native library.
- [Doe qualification](doe-qualification.json) and
  [Dawn qualification](dawn-qualification.json) preserve the frozen generation
  cases, exact CPU-reference outputs, cancellation and following generation.
  [Doe log](doe-qualification.log) no longer contains the deferred-destruction
  warning. [Observed cleanup](doe-profile.json.gz) has no recorded failed calls;
  the [profile log](doe-profile.log) also preserves process-exit output.
- [Package contracts](package-contracts.log) and
  [admission/observer tests](admission-tests.log) pass. The latter also checks that
  diagnostic observation preserves return values and thrown/rejected errors.

[Provider identities](providers.json) bind the corrected host source snapshot and
unchanged native library. The original dependency and model custody limitations
remain those of the [generation runbook](../../../bench/external-projects/doppler-generation/README.md).
`SHA256SUMS` binds retained artifacts; `source-SHA256SUMS` binds changed host/test
sources, workload, oracle and inspected Doppler cleanup source. No Doppler code,
qualified release binary, numerical threshold or shader changed.

This qualifies the observed explicit-destruction path on native Node/Vulkan.
It does not qualify arbitrary driver loss, all callback orderings, total process
leak freedom or another backend. Timings are incidental and grant no performance
credit. The separate descriptor-retirement experiment remains rejected.

Reproduce the unit check and physical integration commands from the mapping repair
runbook, using the repaired native library. Requalify the existing generation
runner with a provider manifest binding the corrected host source. Its original
receipt alone does not fail on logged cleanup warnings; inspect both retained
logs and profile failure events as done here.

Component: package queue-completion lifecycle. Intent: preserved.
Acceptance evidence: unit, physical Vulkan, package contracts and unchanged
generation receipts above. Boundary effects: host completion handles explicit
device destruction; native runtime, compiler and Doppler behavior are unchanged.
