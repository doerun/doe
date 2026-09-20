# Bounded Metal operational waits

Base: `fadf266bb48e88f8c89cddfa937d4f9b21964d94` (pushed and remote verified
before this continuation). The prior dispatch and calibration checkpoints remain
separate evidence.

## Failure mechanism and repair

Command-runtime retirement previously called `waitUntilCompleted` for each
submitted buffer. The configured WebGPU FFI timeout did not apply to native
Metal. A stalled submitted command could therefore block an operation without a
declared native wait budget. Treating a timeout as terminal would instead allow
premature reuse or destruction of buffers still referenced by the GPU.

The new versioned `config/metal-command-wait-policy.json` is strictly parsed at
build time and supplies immutable values to each runtime build tier. The
completion owner uses one monotonic elapsed budget across the batch. Native
status is queried without blocking; sleeps are capped to the remaining budget.
The polling and blocking bridge paths share terminal status classification.

Terminal references are released individually. Pending, unknown and clock-failure
outcomes retain ownership. Timeout blocks new submission through the completion
owner; a later explicit flush can retire the same work without resubmission.
Earlier observed native failure remains latched and is included when a timeout
is reported through the backend command diagnostic. Queue recycling and deferred
release remain after successful retirement of every pending reference.

The supported destruction path remains a blocking drain. Unknown status sleeps
between drain attempts rather than busy-spinning. It is not cancellation, and
reentrant destruction remains unresolved. No bounded-teardown claim follows.

## Contract migration

See `docs/metal-command-waits.md` for scope, errors, retry, ownership and migration.
Policy version 1 adds a native command-runtime build contract and explicit
`MetalWaitTimeout` and `MetalWaitClockUnavailable` errors. Unknown remains distinct
from pending and failed. Existing serialized result fields and old bridge ABI
entrypoints are preserved; the new nonblocking polling entrypoint is additive.
The schema target, build parser, bridge manifest, declarations and non-Metal stub
are updated together. The polling stub reports unavailable completion, not a synthetic
terminal GPU failure.

No ordinary native WebGPU callback behavior, accepted package, evaluator,
workload, numerical reference, acceptance threshold or completed calibration
artifact is changed. Polling affects CPU work and completion observation latency;
physical comparisons are required before any performance or package claim.
The separate native `QueueWaitMode` mapping is not implemented by this change.
The schema/correctness/trace/verification requirements in `docs/process.md` remain
authoritative; this checkpoint is not package release acceptance.

## Examination and verification

Whole-file examinations cover:

- `src/backend/metal/metal_completion.zig`: reference transfer, batch compaction,
  terminal/native error identity, shared deadline, timer failure, retry, reentry,
  allocation boundary and blocking destruction. Reentrant destruction and
  physical Metal behavior remain findings.
- `src/backend/metal/metal_wait_policy.zig`: sole typed build parser and immutable
  values, strict serialized types/version/fields, bounds and allocation cleanup.
- `src/backend/metal/metal_runtime_queue_ops.zig`: streaming submission ownership,
  cleanup placement after retirement, failure propagation, timestamps and
  deferred barriers. Wait-mode mapping, remaining void encoder boundaries and
  aggregate retained capacity remain findings. No code change was needed there
  to preserve resources when the new retirement error propagates.

Supporting runtime, bridge, build and fixture edits receive no automatic review
credit. Directory and relationship scopes are not completed by this checkpoint.

Run from the repository root with the pinned Zig toolchain:

```bash
(cd runtime/zig && zig build test -Dtest-filter='Metal ' --summary all)
(cd runtime/zig && zig build test test-core test-full doe-runtime -Doptimize=ReleaseFast --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref fadf266bb48e88f8c89cddfa937d4f9b21964d94
python3 runtime/zig/tools/review_log.py --check --base-ref fadf266bb48e88f8c89cddfa937d4f9b21964d94
```

[Focused Debug acceptance](focused-final.log) covers partial retirement under one
budget, capped final sleep, refusal of new submission, later recovery, original
native errors, unknown status, unavailable clock, reentrant waits, strict policy
parsing and allocation failure. [ReleaseFast acceptance](acceptance.log) contains
aggregate/core/full suite results, Linux runtime build and structural checks.
The suites overlap and their totals are not unique coverage.

The [first focused attempt](focused.log) exposed a stale bridge fingerprint and
an old host test that treated a non-Metal stub as terminal GPU failure. The test
now verifies unknown completion and retained queue references/resources. A
separate terminal-failure state test preserves the cleanup/error contract;
injected completion tests still cover actual failure-result handling.

The [physical availability check](physical-availability.log) could not reach the
Apple host. The added event-blocked Metal fixture checks uncommitted rejection,
timeout retention, refusal of new submission, and retirement after a separate
queue signals the event. Its cleanup signals and drains before releasing the
event even on assertion failure. Linux explicitly skips it. Apple SDK compilation,
physical Metal success, device-failure behavior and polling cost are unqualified.

## Next action

Finish the queue wait-mode contract and remaining native/render encoder failure
paths. Establish a safe ownership-transfer contract for reentrant destruction,
then execute Apple SDK and physical checks and qualify a corrected package.
The next never-examined queue file remains `src/backend/ports/telemetry.zig`.

Component: Metal command completion; build configuration; native bridge
Intent: preserved
Acceptance evidence: focused and ReleaseFast receipts, schema and link checks,
physical-availability receipt, append-only review ledger
Boundary effects: native command operational timeout and error semantics; additive
native bridge ABI; no ordinary package or evidence-policy behavior changes
