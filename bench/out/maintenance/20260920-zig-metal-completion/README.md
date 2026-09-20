# Metal completion and surface-port checkpoint

Batch base: `bd1a81618031db0ebc7d759d863fd6a7027fd003`.
This continues the [texture-safety checkpoint](../20260920-zig-metal-texture-safety/README.md).
[File examinations](file-reviews.md) distinguish complete source review from
supporting bridge, runtime, fixture and inventory edits.

## Failure and repair

Deferred rollover previously released the preceding command-buffer reference
without reading its result. A later successful command could therefore conceal
an earlier failure. Waiting on a shared-event signal also supplied no native
command error and could wait forever if failed GPU work never signaled.

`metal_completion.zig` now owns every submitted command reference until its
individual result is checked. Reservation occurs before commit, so allocation
failure preserves the unsubmitted command and open encoder. Queue flush waits
all pending submissions and the current submission, retires their references,
recycles resource storage, then reports the first failure. Successful successors
cannot clear it. The command adapter rejects later requests on a failed runtime;
reconstruction is required to resume execution.

The new internal bridge wait checks `MTLCommandBufferStatusCompleted` and copies
the native `NSError.code` on failure. Missing error detail remains a failure with
an unavailable code, not success. The existing status-message field includes the
first native code for command/dispatch errors; direct callers receive the typed
`MetalCommandFailed` error and can inspect the runtime-owned code. This does not
retain the complete NSError object or its underlying-error chain.

Apple documents that completion waiting includes completion handlers, and that
failed execution has a distinct status and error. The implementation checks both
waiting and outcome instead of inferring success from queue ordering.
[Command-buffer execution model](https://developer.apple.com/library/archive/documentation/Miscellaneous/Conceptual/MetalProgrammingGuide/Cmd-Submiss/Cmd-Submiss.html).

Dispatch, warmup, kernel completion, presentation and flush use the same owner.
Presentation retires earlier command-runtime work inside its measured wait scope
and cleans the drawable before returning a completion failure. Map operations
propagate latched errors before native allocation. Teardown drains committed work
before destroying its resources; its void destructor cannot return an error.

## Costs and contract migration

The pending-reference array uses the runtime allocator and may grow at deferred
submission boundaries. Capacity is retained until teardown; live entries are
bounded by submissions since the last flush, not by a new fixed policy limit.
There is no new allocator, global state, worker, cache or configuration switch.
Recording all deferred results adds host storage and status-check work. Command
runtime waits now use the checked native completion wait; the old upload-size
heuristic and its unused constant are removed. Legacy bridge wait symbols remain
for their separate ordinary-native consumers. No performance claim follows.
Flush no longer creates an empty GPU command solely because CPU-only upload
state is marked deferred. Wait timing includes completion inspection and handle
retirement; fresh physical evidence is required before comparing these sources
with the accepted package.

The single outstanding-handle field becomes a named completion owner. Header,
Zig declaration, non-Metal stub, symbol manifest and test inventory migrate
together. The non-Metal stub explicitly fails. No public command field or
serialized schema field changes; existing error status and message contracts
carry the failure. Charter authority, accepted binaries, thresholds and release
qualification remain unchanged. Existing blocking gates in `docs/process.md`
continue to apply.

## Reproduction and acceptance

Run from the repository root with Zig 0.15.2 on PATH:

```bash
python3 bench/out/maintenance/20260920-zig-metal-completion/reproduce_predecessor.py
(cd runtime/zig && zig build test --summary all)
(cd runtime/zig && zig build test-core -Doptimize=ReleaseFast --summary all)
(cd runtime/zig && zig build test-full --summary all)
(cd runtime/zig && zig build test -Dtest-filter='Metal repair proof' --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref bd1a81618031db0ebc7d759d863fd6a7027fd003
python3 runtime/zig/tools/review_log.py --check --base-ref bd1a81618031db0ebc7d759d863fd6a7027fd003
```

- [Predecessor failure](predecessor-rollover.log) comes from the predecessor's
  extracted rollover/retirement functions with a recording bridge. The
  [reproducer](reproduce_predecessor.py) retains the
  [probe](predecessor-rollover-probe.zig). It establishes loss of the earlier
  reference without status inspection, not an induced physical GPU failure.
- [Aggregate](aggregate-final.log), [ReleaseFast core](core-release-fast-final.log)
  and [full-lane](full-final.log) receipts include build, architecture, ABI,
  formatting, bridge and inventory checks. Host tests distinguish success from
  absent error detail, preserve the first failure across successful successors,
  release every handle exactly once after waiting, reject allocation before
  encoder transitions and leave a failed queue drained but observably failed.
- [Physical availability](physical-availability.log) records explicit skips on
  Linux. The Metal fixture now forces deferred rollover between independent
  staged writes; its independent readback oracle and caller-source poisoning
  remain intact. Apple SDK compilation, real device failure and presentation
  behavior are unestablished here. Host injection is separate evidence.
- [Schema](schema.log) and [documentation links](doc-links.log) retain repository
  checks. Intermediate logs remain diagnostic; the initial aggregate compilation
  failure identified an old test referring to the removed field, fixed before
  final acceptance.

## Remaining work

Native encoder methods still have void failure boundaries; checked completion
cannot detect work that was never encoded. Queue wait-mode and timeout settings
need an explicit supported contract and bounded waiting that keeps resources
alive after timeout. `waitUntilCompleted` itself is not a timeout guarantee.
Ordinary native WebGPU queue callbacks and wait consumers require a separate
lifetime/error review; this checkpoint covers the command runtime.

Surface configuration/layer replacement still need transactional state, and the
Metal command capability query still only creates an entry. Those findings keep
the surface-port implementation examination open. Preserve the predecessor
surface-runtime findings instead of granting completion for a new port comment.
Continue these concrete repairs and physical qualification; the next
never-examined file is `runtime/zig/src/backend/ports/telemetry.zig`.

Component: Metal command submission/completion and surface port.
Intent: preserved.
Acceptance evidence: commands and retained receipts above.
Boundary effects: internal bridge ABI, command reference ownership and error
messages, test inventory and review history. No public schema or authority
change; no ordinary-native, physical Metal, performance or release qualification.
