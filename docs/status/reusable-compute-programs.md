# Reusable compute programs

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
