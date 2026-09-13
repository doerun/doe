# Reusable compute programs

## GPU interference attribution

The [latest warmup continuation](../../bench/out/compute-program/20260913-warmup-qualification/README.md)
retains another incomplete calibration rejected on observed GPU work. Its
departed client's application identity is unknown. The
[observer repair](../../bench/out/compute-program/20260913-gpu-activity-attribution/README.md)
now retains boot-scoped task identity alongside raw counters, preserving null
attribution for visibility gaps and process races. A separate live observation
identifies Chrome from the Doppler consumer-streaming worktree using the shared
device. A fresh calibration with the revised observer then rejected GPU work
from another captured Chrome process in that worktree. The attributed sidecar
and matching live process identity are retained in the repair record. Counter
admission and accepted runtime bytes remain unchanged. A complete calibration
requires a window without the competing browser GPU work; interrupted cohorts
cannot qualify the procedure or authorize a candidate.

## Process-boundary evidence retention

The [retention repair](../../bench/out/compute-program/20260912-process-output-retention/README.md)
responds to a warmup cohort exhausting disk before end-of-cohort sharing.
Calibration and candidate execution now apply the declared space bound before
each child and retain identical outputs immediately afterward, including failed
children. Observer receipts use atomic replacement. The interrupted files remain
failure evidence; accepted archives, warmup settings, and thresholds are
unchanged. The fresh physical continuation retained outputs successfully but
stopped in its final cohort on observed foreign GPU work. Its incomplete receipt
fails candidate admission and supplies no final precision assessment. A complete
fresh calibration remains required before procedure promotion.

## Explicit measurement policy and warmup qualification

The [warmup revision](../../bench/out/compute-program/20260912-warmup-calibration-v1/README.md)
retains a separately generated procedure with unchanged accepted archives and
thresholds. Calibration now passes its selected policy through execution;
replay rejects differing experiment policies, invocation settings, or child
policy identities. The first A/A attempt stopped on observed foreign GPU
activity; the later continuation is recorded above. Neither interrupted attempt
qualifies the revised procedure or authorizes a candidate. The accepted runtime
and original measurement procedure remain unchanged.

## Ordinary measurement warmup and cost attribution

The [resolution diagnosis](../../bench/out/compute-program/20260912-runtime-resolution-final/README.md)
retains an ordinary warmup comparison, separate host and V8 profiles, and
physical evidence replay against the accepted package. Extended warmup reduces
within-process useful-latency drift while encoding remains variable. Queue
submission/completion and receipt hashing warrant distinct investigation;
whole-process numerical checking and file writing cannot be counted as native
runtime work. The [diagnostic contract](../compute-program-resolution.md)
preserves ordered samples, unavailable observations, signed profiler deltas,
and the original acceptance policy. This establishes no accepted optimization
or resolved calibration precision. Fresh A/A qualification of any revised
measurement procedure remains required before promotion.
Later physical attempts retain observed foreign-GPU admission failures; the
completed cohort's frozen inputs and separate stricter reviewer remain available
for read-only evidence replay.

## Command storage decisions and measurement resolution

The [command-storage record](../../bench/out/compute-program/20260912-command-storage-completion/README.md)
connects build-checked policy, derived diagnostics, package qualification, and
ordinary application evaluation. The accepted Linux library remains unchanged.
The [fresh calibration](../../bench/out/compute-program/20260912-command-storage-calibration-uncertainty/report.json)
separates A/A null consistency from precision adequate for promotion. Unresolved
regression bands still prevent accepting small improvements. The
[bounded experiment](../../bench/out/compute-program/20260912-command-storage-experiment-ordinary/report.json)
retains the rejected policy control and the cost endpoints supporting its
decision; it does not establish a successful runtime optimization or unfamiliar
external application adoption. Earlier threshold-only calibration failures
retain their original meaning. Contracts, assumptions, and migration are in
[command storage development](../command-storage-development.md).

## Structured row comparability and wgpu claim exclusion

Evaluation matrix schema version 2 introduces structured row-level comparability
contracts in [`config/compute-program-matrix.schema.json`](../../config/compute-program-matrix.schema.json).
Comparison rows now explicitly record `hostRuntime`, `completionModel`,
`readbackModel`, `pollingModel`, `pathAsymmetry`, `exclusionReason`, and
`claimEligible`. Deno/wgpu comparison rows declare `pathAsymmetry: true`,
`exclusionReason: "deno_wgpu_host_polling_asymmetry"`, and `claimEligible: false`,
keeping wgpu evidence visible for host/polling diagnostics while barring it from
superiority claims in [`bench/gates/compute_program_gate.py`](../../bench/gates/compute_program_gate.py).
Unit tests in [`bench/tests/test_compute_program_gate.py`](../../bench/tests/test_compute_program_gate.py)
enforce that asymmetric rows cannot be marked claimable regardless of speed ratios.

## Current A/A findings and correctness repairs

The [accepted-package A/A control](../../bench/out/compute-program/20260908-startup-aa/completion.md)
violates regression limits despite identical archives. It does not waive prior
failures. The subsequent [adapter instance experiment](../../bench/out/compute-program/20260908-adapter-instance/completion.md)
removes repeated instance creation but fails frozen application regression
limits; its optimization remains isolated and rejected.

The separate [helper cleanup repair](../../bench/out/compute-program/20260908-helper-cleanup/README.md)
releases one-shot temporary resources, preserves borrowed inputs and concurrent
calls, repairs Bun callback lifetime, and preserves native allocation failures.
Installed qualification is retained across the controlled package hosts. Public
contracts, original benchmark archives, and accepted instance ownership remain
unchanged. Ordinary-provider advantage and independent operator reproduction
remain open.

## Rejected startup correction and reproducible handoff

The [startup experiment](../../bench/out/compute-program/20260908-startup-enumeration/completion.md)
completed its frozen uninstrumented application comparison after unrelated GPU
work stopped. Native tests, retained-package qualification, numerical outputs,
execution identity, and observed-GPU admission passed. Lower startup medians do
not outweigh the development application's preparation and cold-tail regressions
or the simulation's warm-tail regressions. The native candidate is rejected;
the accepted runtime remains unchanged. Earlier failed attempts stay intact.

The [reproduction bundle](../../bench/out/compute-program/20260908-startup-enumeration/reproduction-bundle.tar.gz)
retains exact packages, workloads, oracles, gates, policies, and declared host
prerequisites. Its offline relocation audit passed with the workspace absent.
This is local reproduction by the producing operator on the same machine,
not independent operator reproduction or a performance result. Ordinary-provider
advantage, independent operation, research acceleration, equipment integration,
and additional physical hardware qualification remain open.

## Corrected startup measurement

The [startup diagnosis](../../bench/out/compute-program/20260908-startup-scope/README.md)
reproduces provider-specific evidence work inside the old device-startup timer.
Current evaluation reports separate device readiness from identity collection
and file retention, and comparison guards reject incompatible startup scopes.
Original observations remain intact. The
[uninstrumented ordinary checks](../../bench/out/compute-program/20260908-startup-scope/validation/outcome.json)
pass numerical and native audits but do not establish an accepted application
advantage. No native change is accepted from this measurement correction.

## Restricted candidate execution

The [isolation and cancellation record](../../bench/out/compute-program/20260908-candidate-isolation/README.md)
closes the reproduced host-access and CLI-cancellation gaps in the existing
candidate evaluator. Current Linux evaluation requires explicit render-device
access, read-only acceptance inputs, network isolation, and verified cgroup
limits. Missing isolation fails explicitly. The command wrapper now transfers
its process to the executor so cancellation reaches its resource owner.

Installed-package GPU execution, rejection, cleanup, and adversarial host checks
are retained alongside the initial native-sidecar and cancellation failures.
Frozen performance rejections remain visible. Versioned evidence preserves
historical semantics; earlier reports receive no retroactive isolation claims.
The accepted native runtime and public package are unchanged. Ordinary
application advantage, unfamiliar research acceleration, independent operation,
equipment integration, and additional physical hardware remain open.

## Ordinary comparison, rejected polling, and offline handoff

The [ordinary Node continuation](../../bench/out/compute-program/20260908-ordinary-node-resume/README.md)
completed under the existing numerical, execution, identity, and observed-GPU
admission rules. It does not establish application advantage over Dawn.
Connected invocation diagnostics motivated the
[bounded completion-polling experiment](../../bench/out/compute-program/20260908-timeline-poll-experiment/README.md).
That candidate improved measured latency but failed the frozen cost limits;
its runtime change is rejected and the accepted main-checkout binaries remain
unchanged. Exact candidate sources, archives, and unfavorable evidence are retained.

The tail runner now applies its existing cost threshold to invocation CPU median
and slow-tail observations. Regression tests reproduce the earlier omission.
Historical comparisons remain intact; the experiment retains a separate stricter
assessment. Report schemas and application acceptance inputs are unchanged.

The [simulation handoff bundle](../../bench/out/compute-program/20260908-live-handoff/README.md)
passed installation, prolonged correctness, cleanup, reset, cancellation, and
reopening with networking disabled and the workspace absent. This is local
reproduction on the same machine. Independent operation, ordinary application
advantage, research acceleration, equipment integration, and broader physical
hardware qualification remain open under the existing journey prerequisites.

## Current demonstration priority

The [target journeys](../thesis.md#prioritized-target-journeys) put unchanged
ordinary Node provider substitution before interactive reuse and agent-assisted
acceleration. Existing live-simulation and candidate-runner records below remain
bounded implementation evidence, not proof that these target outcomes are met.
The ordinary application advantage and independent reproduction remain open;
the retained tail experiment must not be relabeled as a win. Additional hosts,
equipment integrations, and chip-platform evaluations receive no inherited
support or customer status from this priority change.

## Ordinary comparison and terminal integration follow-up

The [ordinary Node recheck](../../bench/out/compute-program/20260908-ordinary-node-recheck/README.md)
keeps the accepted archives and compares ordinary WebGPU with pinned Dawn.
It excludes prepared execution and the unresolved Deno host/polling lane.
The first attempt exposed an order-dependent adapter-identity matcher; the
general matcher now handles name-only and numeric identities in either order,
while rejecting conflicting numeric IDs, missing labels, and fallback adapters.
Adversarial gate tests cover that correction. The separate corrected attempt
passed numerical audits but was rejected for unrelated observed GPU activity.
No timing advantage or new runtime optimization is accepted from these attempts.

The [terminal integration record](../../bench/out/compute-program/20260908-live-terminal/README.md)
extends the existing application with a checked GPU heat-field view, preparation
and preflight reporting, and explicit close/reopen controls. Reopening initializes
fresh state using the last accepted shader, format, and rate; it is not execution
resume or driver-loss recovery. Package qualification is retained
[separately](../../bench/out/compute-program/20260908-live-terminal-qualified/summary.json),
including the physical Node terminal regression. The native platform archive and
loaded library remain identical to the accepted baseline. Presentation stays
outside Zig. Independent operator reproduction and a measured interaction benefit
remain open; this is an application slice, not closure of the interactive journey.

## Focused tail experiment

The [completion record](../../bench/out/compute-program/20260908-tail-experiment/README.md)
retains the original comparison, frozen process repetitions, expanded sampling,
invocation-linked host and native observations, and the rejected candidate.
Slow invocations recur, but the observations do not establish a single tail cause.
Reference-array growth was observed separately from contended lock acquisition.
Retaining empty reference capacity removed observed warm growth; the final
uninstrumented application comparison failed the preregistered acceptance policy.
The runtime and staged package were restored. No runtime correction is accepted
from this experiment, and no performance advantage over Dawn is claimed.

The earlier encode-metadata checkpoint remains historical evidence; its original
benefit was not established as a stable application gain by expanded sampling.
The retained replay bundle supports another operator's reproduction. Its local
relocation check is not independent reproduction; that acceptance remains open.

## Next ordinary-execution work

The [completed revision](https://github.com/doerun/doe/commit/d4cbfe163c457f808e99bc02578423bc52e9a1d8)
and [correction record](../../bench/out/compute-program/20260907-command-storage/README.md)
are the reference for this follow-up. The Linux checklist below stays closed.
Reopen ownership, reflection, reset approval, or worker isolation only with a
new failing reproduction; keep previous accepted artifacts intact.

- [x] Freeze the comparison baseline — runtime and integration owners: exact
  archives, qualification receipts, native/addon identities, frozen inputs and
  policies are bound in the [baseline manifest](../../bench/out/compute-program/20260908-tail-experiment/baseline-manifest.tsv).
  The [replay bundle](../../bench/out/compute-program/20260908-tail-experiment/reproduction-bundle/README.md)
  passed clean installation and application audits outside the checkout.
- [x] Profile heat diffusion's ordinary encoding tail — runtime owner: start from
  [ordinary incumbent measurements](../../bench/out/compute-program/20260907-command-storage/ordinary-incumbents.tsv).
  Completed in
  [heat-diffusion-ordinary-encoding-profile.json](../../bench/out/compute-program/20260907-command-storage/heat-diffusion-ordinary-encoding-profile.json):
  `encode` p99 is 0.327536 ms (max 0.456610 ms); `submitWait` p99 is 0.357644 ms (max 0.382580 ms).
  Responsibility is in `packages/doe-gpu/src/compute-program.js` (`encode` at lines
  127-145, execution path at 246-313). Separation is preserved, and next-step correction
  selection is still pending based on this evidence.
- [x] Correct the demonstrated bottleneck — runtime owner: immutable encode metadata
  derived during `prepareComputeProgram` eliminates per-run Map lookups and array
  spreading in `packages/doe-gpu/src/compute-program.js`, preserving per-run WebGPU
  command-encoding semantics without claiming command-buffer reuse. Qualified in
  `bench/out/compute-program/20260908-encode-metadata-qualified/summary.json`;
  measured against baseline Doe in
  `bench/out/compute-program/20260908-encode-metadata/alternating/comparison.tsv`
  and against incumbents in
  `bench/out/compute-program/20260908-encode-metadata/ordinary-incumbents.tsv`.
  Correctness regressions and cold/preparation costs pass in
  `bench/out/compute-program/20260908-encode-metadata/alternating/process-costs.tsv`.
  Candidate median encode and complete invocation wall latency improved against baseline
  Doe; see `bench/out/compute-program/20260908-encode-metadata/alternating/comparison.tsv`
  for exact quantiles. In the incumbent comparison, ordinary-path heat diffusion tail
  latencies (`encode` and `submitWait` p99) against Dawn remain higher; see
  `bench/out/compute-program/20260908-encode-metadata/heat-diffusion-ordinary-encoding-profile.json`
  for the updated profile. No speedup over Dawn is claimed.
- [ ] Resolve Deno/wgpu comparability — comparison owner: match effective host,
  polling, completion, and readback conditions, or explicitly exclude affected rows
  from runtime superiority claims. Acceptance requires matched-work receipts and
  enforced claim exclusion while any asymmetry remains; retain diagnostic records.
- [ ] Deliver independent application reproduction — integration owner: package one
  application's exact binaries, inputs, frozen tests, controls, and commands without
  workspace paths, caches, or checkout dependencies. Acceptance requires another
  developer's retained correctness and repeat measurements on declared hardware,
  demonstrating a repeatable useful-operation benefit without changing the tests.

## Separately scoped follow-ups

These are outside the completed Linux milestone and the optimization acceptance
above. Support and release authority remain in [runtime status](runtime-backends-and-bench.md)
and [compiler and WebGPU status](compiler-and-webgpu.md).

- [ ] Metal qualification: define a physical host/package lane; require matching
  correctness, lifecycle, and application evidence before extending support.
- [ ] D3D12 qualification: define a physical Windows lane with its own retained
  package, capability, correctness, lifecycle, and application acceptance.
- [ ] Registry publication and signing: define release artifacts and admission;
  require authorized signing/publication and independent registry installation.
- [ ] Physical driver failure: define an isolated fault/recovery exercise and
  acceptance for recovery, cleanup, and accepted output; device destruction is distinct.
- [ ] Broader conformance: define the required shader/CTS scope and supported tuples;
  retain failures and complete physical evidence before making conformance claims.

## Ordinary command preparation

Native devices retain bounded empty command-array capacity after resource release.
Policy, ownership checks, qualification, and complete application comparisons:
`bench/out/compute-program/20260907-command-storage/README.md`.

## Concurrent native ownership

Independent Node workers now have isolated addon state and a stable native
library binding. Async pipeline snapshots, callback leases, and worker startup
have allocation-failure coverage. Public C and retained-package acceptance are
indexed at `bench/out/compute-program/20260907-async-pipeline-ownership/README.md`.
Shared-device mutation and physical driver loss remain outside this evidence.

## Bounded candidate development

`bench/cli.py program candidate` accepts candidate WGSL against a separately
pinned reference job. It retains numerical outputs, validates native shader and
submission identity, enforces declared resource/process limits, and requires
fresh acceptance when comparing execution environments. The candidate can change
its declared shader; acceptance inputs and policy remain hash-bound. The live
simulation and candidate evaluator share the same process deadline/termination
implementation without adding another public package API.

The job, execution, and report contracts and migration are described in
[reusable compute programs](../reusable-compute-programs.md#bounded-candidate-jobs).
Qualification of the exact package is retained at
`bench/out/compute-program/20260906-candidate-qualified/summary.json`.
Search results, rejected candidates, environment comparisons, raw outputs,
native journals, and reproduction commands are indexed by
`bench/out/compute-program/20260906-candidate-runner/README.md`.
These CPU-reference jobs remain diagnostic. They do not establish an incumbent
GPU-provider advantage, general acceleration of unfamiliar routines, complete
dependency isolation, peak GPU memory, or physical driver-loss recovery.
Prolonged Linux checks and remaining execution work are indexed in the
Linux/Vulkan completion checklist below.

## Live simulation editing

The shipped Node terminal example has a resident heat simulation, parameter
changes, candidate preflight in a bounded process, obsolete-edit cancellation,
independent numerical acceptance, explicit reset decisions, and activation at
an iteration boundary. Every active frame is checked against the CPU stencil.
The original simulation advances during preflight; replacement preparation on
its device still pauses execution and reports its duration. This is an
application loop over the existing program contract, with policy outside Zig.

`packages/doe-gpu/test/integration/test-integration-live-simulation.js` exercises
invalid and numerically wrong shaders, overlapping edits, unchanged state,
changed state interpretation, stale/declined/approved resets, cancellation, and
reopening. Package qualification runs the application on Node only. Physical
Metal and an application performance advantage remain separate acceptance work;
prolonged Linux checks are indexed below. Commands and limits are in
[reusable compute programs](../reusable-compute-programs.md).
The same retained wrapper and native package pass controlled host qualification
at `bench/out/compute-program/20260906-live-simulation-qualified/summary.json`.
Application comparisons from those exact packages are retained at
`bench/out/compute-program/20260906-live-simulation-applications/summary.json`;
the Deno/wgpu rows trigger the suspicious-speedup audit and remain diagnostic.
See `bench/out/compute-program/20260906-live-simulation-correction/README.md`
for source identities, test commands, archive extraction, and current limits.

## Explicit simulation state changes

Descriptor version 3 adds application-owned resident state formats and exact-edit
reset assessment. Destructive edits require explicit approval bound to the old
program instance and invocation revision; rejected or failed updates preserve
the old state. Earlier descriptor versions retain their existing behavior.
The migration and error contract are in
[reusable compute programs](../reusable-compute-programs.md#state-update-approval-migration).
The physical integration regression exercises each available execution mode.
State-update and independent-device qualification is retained in
`bench/out/compute-program/20260906-state-update-qualified/summary.json`.
Addon reflection failure qualification is retained in
`bench/out/compute-program/20260906-explicit-failures-qualified/summary.json`;
earlier package hashes retain their original scope. Subsequent native rendering
ownership acceptance is tracked in [compiler and WebGPU](compiler-and-webgpu.md).
The live-edit example above supplies application preflight and activation;
this contract alone does not establish asynchronous pipeline preparation.

## Native recorded command ownership

Deferred compute, copy, and rendering ownership is covered by the completed
Linux checklist below. New failures require a retained public-boundary reproduction.

## Evidence schema routing

Package and matrix summaries use explicit report kinds; unknown kinds fail.
The contract remains in [schema enforcement](../config-schema-enforcement.md#schema-target-registry-migration).

## Resource lifetime correction

The completed Linux checklist bounds allocation, cancellation, and device cleanup
claims. Peak residency and physical driver loss remain outside that evidence.

## Current boundary

`doe-gpu/compute-program` is the declared fixed-shape interface. Programs retain
resources, support invocation/program buffer lifetimes, optional GPU-only
output, and same-device composition through owned references. Updates preserve
unchanged resources and roll back failed preparation. Submitted cancellation
waits for completion and invalidates potentially modified resident state.

Vulkan `gpu-recorded` retains GPU commands; `native-recorded` replays host
commands in Zig; `webgpu` retains resources and reencodes. Pipeline and descriptor
reuse checks complete native identities. Changed declarations rebuild recordings
and private descriptor state. Receipt version 5 binds provenance, actual work,
and concurrent queue/mapping completion. Requested bytes are not peak memory.

The scalar SPIR-V arithmetic policy is explicit in
`config/spirv-compute-arithmetic-policy.json`. Ordinary and recorded Doe pass the
unchanged continuous HoloScript WGSL, inputs, frozen membrane tolerances, and
exact spike oracle on the qualified AMD Vulkan host. Other backend qualification
and general numerical improvement are not inferred.

## Qualification and reproduction

The AMD external evaluation policy now rejects timing runs with observed
unrelated DRM activity. Raw process-boundary observations are bound to each
measured output and rechecked by the matrix gate. This detects visible
contention without interrupting other clients; it does not establish exclusive
access or cover clients absent from both snapshots. Numerical audits remain
separate. The policy migration and visibility limits are documented in
[reusable compute programs](../reusable-compute-programs.md).
Guarded application records are in
`bench/out/compute-program/20260906-gpu-activity-matrix/summary.json`;
the controlled physical rejection and compatibility checks are retained in
`bench/out/compute-program/20260906-gpu-activity-correction/`.

`program qualify-package` retains the same archives for fresh Node, Bun, and
Electron main-process installation. Qualification version 2 uses relative
artifact filenames so the evidence directory can move without rewriting hashes.
`program evaluate --package-qualification` consumes those archives, validates
installed files and loaded native identities, and keeps the complete package
inputs. Public contracts and migrations are in
[reusable compute programs](../reusable-compute-programs.md).

Earlier relocated-package and clean-checkout runs remain historical evidence,
not independent developer reproduction or registry publication.

## Linux/Vulkan completion checklist

- [x] Verify retained package hashes and clean Node, Bun, and Electron main-process
  installation. Run public C-boundary copy regressions against the retained
  native binary, including origins, untouched pixels, dimensions, and aspects.
- [x] Close demonstrated downstream shader and model failures with independent
  accepted outputs; retain reproductions and cross-program regressions.
- [x] Prolonged ordinary and prepared sessions with independently checked output.
- [x] Stable sampled post-close allocations while closed programs remain reachable.
- [x] Independent device objects, recreated Node workers, and a surviving parent.
- [x] Bounded cancellation, explicit device destruction, closing, and reopening.
- [x] Recheck reflection failure propagation, compilation-owned diagnostics, and
  state-reset approval against implementation and retained-package regressions.
- [x] Run the frozen application comparisons with equivalent inputs, correctness,
  caches, transfers, and completion. Record preparation, complete-operation
  latency, CPU use, memory, and long-session behavior; optimize the largest
  demonstrated bottleneck and rerun affected acceptance checks.

The bounded implementation checklist is complete. Current package, model,
comparison, and prolonged checks are indexed at
`bench/out/compute-program/20260907-command-storage/README.md`; earlier resource
and worker evidence remains linked from that correction record.
Peak residency, physical driver failure, shared-device mutation, and arbitrary
worker termination are unqualified and outside this bounded milestone.
Canonical model acceptance uses the retained package and explicit P0 control at
`bench/out/external-projects/doppler/20260907-command-storage-p0-qualified/result.json`.

Dawn and wgpu resident-oracle failures cannot supply equivalent-work timings.
Large Deno ratios remain suspicious host-path observations until audited;
correct invocation-local workloads still include incumbent tail losses. Passing
implementation checks does not establish a performance advantage.

Physical Metal and D3D12 testing are excluded from this milestone; AMD evidence
does not qualify them or Electron renderer execution. Independent adoption is a
separate product outcome. Release admission and authorized publication retain
their own requirements. Broader shader, conformance, and model-transcript scope
lives in [compiler and WebGPU](compiler-and-webgpu.md); Fawn remains experimental.

## Ground truth

- Policies: `config/compute-program-evaluation.json` and
  `config/compute-program-external-evaluation.json`.
- Matrix verification: `python3 bench/cli.py program verify`, with the retained
  matrix policy. Native replay and SPIR-V use `program verify-native`.
- Physical regressions:
  `packages/doe-gpu/test/integration/test-integration-compute-program.js`.
- Frozen resident fixture:
  `bench/out/compute-program/20260905-holoscript-resident-sequence-fixture/fixture.json`.
- Correction records: `bench/out/compute-program/20260905-resident-fusion-correction/`,
  `bench/out/compute-program/20260905-installed-package-correction/`, and
  `bench/out/compute-program/20260905-portable-package-correction/`.
- Blocking requirements: [process](../process.md).
- Preserved failures and previous boundaries:
  [historical records](archive/2026-09-reusable-compute-programs.md).
