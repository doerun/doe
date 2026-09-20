# Metal notification and queue-control integration

Component: Zig Metal command runtime
Intent: preserved
Acceptance evidence: `focused-accepted.log`, `acceptance.log`, `schema.log`, `doc-links.log`, and `physical-availability.log` in this directory.
Boundary effects: backend queue-control adaptation, private Objective-C bridge, command completion, streaming submission, dispatch and presentation. Ordinary native WebGPU callbacks and accepted release packages are unchanged.

## Baseline and proposal provenance

The applying checkout began clean at the commit retained in `base-commit.txt`.
The user supplied an external diff and unfinished review specifications against
`8d647be84ee46c72697a4e647f3525d05082b6c8`. That proposal was not mechanically
applied: the newer checkout already contained checked direct/indirect dispatch,
configuration-owned bounded polling, timing/accounting corrections and retained
failure evidence. The proposal's claimed bundle checksum and extracted-source
checks were not independently replayed here and grant no acceptance credit.

This integration preserves the current implementation and adds the missing
precommit notification and queue-control behavior. It does not replace current
source with the older proposal or import its proposed historical review records.

## Responsibility and behavior

`metal_completion.zig` owns reservation, precommit preparation, submitted
references, operational retirement and the first observed native error. The
private native callback captures only a retained semaphore. Command association
and block capture keep the notification alive independently of a timed-out Zig
stack or completion owner. Preparation is serialized with submission and is
idempotent only before commit. A rejected preparation leaves the unsubmitted
reference with the caller.

`metal_runtime_queue_ops.zig` prepares streaming and deferred barrier commands
before commit. Upload recycling and deferred releases still occur only after all
submitted references reach native terminal states. The immediate barrier uses
one flush/retirement pass with its requested mode; a deferred barrier remains
an ordering acknowledgment rather than evidence of successful completion.

`metal_dispatch_runtime.zig` preserves reservation before encoding, resource-free
program admission, checked direct/indirect encoding, argument capacity and reuse
checks, setup timing, synchronous commit/wait timing, deferred commit accounting
and submission counts. Notification rejection releases the unsubmitted command
exactly once, with no commit. The proposal's replacement dispatch implementation
would have dropped some of these newer guarantees, so it was not copied.

The existing queue port now delivers wait mode and timeout to its own completion
owner. Build configuration remains the default. Zero observes without blocking;
finite waits share one elapsed budget across the batch; the maximum u64 explicitly
requests indefinite operation waiting. Polling retains configured sleeps rather
than switching to the proposal's scheduler-yield spin. Event waits consume the
remaining budget, then inspect all native statuses; a semaphore signal alone
cannot authorize retirement or successful output. First native errors, including
code zero, survive timeout and later completion. Byte-write diagnostics now use
the same original-failure reporting as command execution.

The existing blocking destructor remains unchanged. Permanently unknown work and
same-stack reentrant destruction remain unresolved liveness findings. Operation
timeout is never permission to destroy potentially live resources.

## Contract migration

See `docs/metal-command-waits.md`. Existing typed queue-port inputs acquire
implemented Metal behavior; no public ABI or serialized execution-result field
changes. The JSON build policy retains its positive finite default schema. Its
schema descriptions now distinguish the default from explicit instance calls.
Private preparation and notification bridge symbols are added consistently to
the implementation, header, Zig declarations, unavailable-host stubs and manifest.
Unsupported-host preparation fails explicitly.

`docs/process.md` blocking schema, correctness, trace and verification obligations
remain authoritative. No evaluator, workload, oracle, threshold, accepted binary,
calibration record or performance claim changes. A rebuilt source tree is not an
accepted package. Polling and notification costs need physical application checks.

## Examination and verification

Complete file examinations cover completion, queue operations and command
dispatch. Their ledger entries remain `needs_changes` for the concrete findings
below. Other touched sources and non-Zig contracts are supporting context only;
there is no directory, relationship or automatic touched-file review credit.

Commands from the repository root using Zig 0.15.2:

```bash
(cd runtime/zig && zig build test -Dtest-filter='Metal ' --summary all)
(cd runtime/zig && zig build test test-core test-full test-wgsl doe-runtime -Doptimize=ReleaseFast --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref 426bdb91288c516de9c0f0083868a99ee6bf98a0
python3 runtime/zig/tools/review_log.py --check --base-ref 426bdb91288c516de9c0f0083868a99ee6bf98a0
```

The test logs own executed counts; suite totals overlap. Focused checks cover
shared notification budgets, zero/indefinite waits without a clock, missing
notifications, late terminal results, native error code zero, preparation
allocation failure, retirement reentry, precommit rejection in both dispatch
modes, original dispatch accounting and per-instance port controls. Linux stubs
and host recording probes are not simulated GPU acceptance.

`focused.log` retains an initial test pointer-type compilation error.
`focused-final.log` retains a reentry-test assertion that wrongly expected unknown
completion to override an already recorded native failure. The corrected test
preserves the production first-failure precedence; `focused-accepted.log` is the
subsequent passing execution. These failures are not erased or counted as passes.

The physical fixture prepares notifications before commit, times out under both
modes and zero budget while an event blocks work, then signals from another queue
and retires without resubmission. Failure cleanup signals and drains before
releasing the event. This fixture is explicitly skipped on Linux. The Apple host
connection attempt in `physical-availability.log` timed out: Apple SDK compilation,
ARC/associated-object lifetime, native completion errors, early release,
concurrent-device behavior and numerical Metal execution remain unqualified.

## Remaining work and next scope

Completion still needs a safe close/deferred-destruction ownership contract for
reentrant or permanently unknown work. Queue operations retain void native
encoder/finalization boundaries and unbounded aggregate retained-capacity concerns.
Dispatch still depends on a broad structural runtime context and requires native
SDK/readback acceptance. These findings are not closed by host tests.

Run Apple SDK compilation and the retained physical repair fixtures against an
isolated build before package qualification. Continue the never-examined queue at
`file:src/backend/ports/telemetry.zig`; supporting edits here do not advance that
scope. The append-only review log and generated queue own current review status.
