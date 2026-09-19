# D3D12 dispatch synchronization review

Batch base: `e727aa663252526f32d54e4d2b9242c7653e5142`.
Scope: `file:src/backend/d3d12/commands/d3d12_dispatch.zig`.
This continues the [preceding examination](../20260919-zig-d3d12-dispatch/README.md)
and closes its synchronization and tracking-ownership findings. The ledger
records the current verdict; supporting edits receive no additional file,
directory, relationship, or physical Windows review credit.

## Ownership and failure conclusions

The command file retains its D3D12 dispatch responsibility. Its preparation,
argument serialization, command acquisition, encoding, submission, metrics,
error paths, and destruction were reexamined against the changed consumers.
The prior real-bytecode and indirect-buffer repairs remain intact.

After `ExecuteCommandLists`, cleanup cannot be governed by a Zig error return
alone. The dispatch result now carries the submitted handles, actual submission
count, completion observation, and any synchronization error together. The
runtime adopts deferred handles into pre-reserved storage and clears the local
owner before exposing the error. Cached synchronous commands retain their fence
identity and reject reuse until recovery establishes completion. Recovery wait
cost remains in submission/wait timing. Native errors do not erase the observed
submission count from provider telemetry.

Checked signal and wait operations distinguish `QueueSignalFailed`,
`FenceWaitFailed`, and `DeviceLost`. These error names use the existing error
status/message contract; no public field or schema version is added. Native
HRESULT values are classified at this narrow boundary, not serialized as new
fields. Missing completion remains an error with retained ownership.

The wait uses the documented synchronous null-event form of
[`SetEventOnCompletion`](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12fence-seteventoncompletion).
It checks both the call result and the resulting fence observation. There is no
separate Win32 event creation, registration lifetime, or handle-close path.
The native device-loss sentinel is checked before numeric completion comparison.

Shared upload flush records which lists were already submitted. A failed signal
or wait retains those resources; retry signals a new completion marker without
executing those lists again. Streaming-copy state likewise retains a submitted
fence and prevents allocator reset until its wait succeeds. Completion accounting
reads the native fence, never the requested value. Terminal device loss does not
advance completed-work counters and prevents further dispatch admission.

Tracking allocation failure preserves all caller-owned handles and array storage.
Before returning that failure, a blocking retirement barrier establishes that
caller cleanup is safe. The former copied-list destruction and duplicate caller
cleanup are removed. Compute, render-batch forwarding, and ordinary native queue
callers now follow this transfer-on-success contract. Native queue errors use the
existing error-delivery path.

Teardown first attempts the ordinary checked flush. If that fails, it drains
through a private retirement fence before releasing any submitted objects. A
terminal device-loss outcome authorizes destruction without asserting successful
execution. The retirement fence is allocated during device creation, remains
instance-owned, and is released at teardown. Its barrier requires serialized
ownership of the runtime queue and fence, as do the existing mutable runtime
submission lists.

The retirement barrier and legacy void synchronization adapters cannot return an
unknown-completion outcome to cleanup. They retry failed native signaling or poll
completion after a failed native blocking wait, yielding between attempts. This
is an explicit blocking ownership contract: a permanently stalled device that
neither completes nor reports removal can keep teardown blocked. No timeout,
retry count, or fabricated completion authorizes premature destruction. Normal
checked invocation paths return their errors instead of entering that recovery
loop. The private fence adds native device-creation cost; no latency or memory
improvement is claimed.

The Windows cross-compile exposed pre-existing aggregate-return ABI mismatches in
resource-description and adapter-LUID calls. Those calls now use the native
header's COM wrappers, including its explicit aggregate-return support. This is
a compile-time ABI adaptation, not a runtime capability fallback.

## Acceptance evidence

- [aggregate-accepted.log](aggregate-accepted.log): final unfiltered Zig suite, including
  formatting, source-layout/import checks, generated test inventory, and contract
  checks. Executed/skipped counts remain in the artifact.
- [targeted-first.log](targeted-first.log): focused D3D12 run before the additional
  streaming-retry regression. The aggregate includes the final test set.
- [bridge-probe-accepted.log](bridge-probe-accepted.log): actual production C
  synchronization bodies compiled and exercised against recording COM methods.
  It injects signal failures, synchronous wait-registration failure, delayed
  completion, private-fence reuse, and device loss before and during a drain.
  The probe records the source and extracted-body hashes.
- [windows-compile-receipt.txt](windows-compile-receipt.txt): pinned-toolchain
  cross-compilation of the complete bridge and hash of the retained
  [Windows object](bridge-windows.obj). This is not a linked or executed runtime.
- [schema.log](schema.log), [doc-links.log](doc-links.log): contract and documentation
  checks. The existing blocking-gate policy in `docs/process.md` is unchanged.

The Zig regressions inject post-submit signal/wait failures, preserve cached
commands, verify transfer before error propagation, exercise tracking allocation
failure under completed and lost-device outcomes, reject false completion, and
confirm upload/streaming retry does not duplicate execution. These tests use the
real ownership/control-flow code with explicit recording adapters. They are not
GPU execution or timing evidence.

`windows-compile.log` retains the initial ABI failure. Earlier aggregate and probe
logs remain historical observations; final artifacts above define acceptance.
The source-level examination of supporting modules is limited to these ownership
and synchronization handoffs. Other backend semantics and legacy adapters still
require their own queue reviews.

No Windows GPU, D3D12 debug-layer execution, linked Windows package, benchmark,
calibration, or accepted release binary is promoted by this review. The Linux
correctness milestone remains closed; accepted packages are unchanged.

## Reproduction and continuation

From the repository root, with Zig 0.15.2 on PATH:

```bash
(cd runtime/zig && zig build test --summary all)
python3 bench/out/maintenance/20260919-zig-d3d12-synchronization/probe-bridge.py
zig cc -target x86_64-windows-gnu -c runtime/zig/src/backend/d3d12/d3d12_bridge.c -I runtime/zig/src/backend/d3d12 -o /tmp/doe-d3d12-bridge.obj
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref e727aa663252526f32d54e4d2b9242c7653e5142
python3 runtime/zig/tools/review_log.py --check --base-ref e727aa663252526f32d54e4d2b9242c7653e5142
```

Next queue scope: `file:src/backend/d3d12/commands/d3d12_gpu_timestamps.zig`.
Examine real query availability, command ordering, fence completion, readback
ownership, timestamp frequency/conversion, error reporting, and measurement scope.
Do not infer timestamp support or physical accuracy from host-side fixtures.

Component: Zig D3D12 dispatch, synchronization, and submission retirement.
Intent: preserved.
Acceptance evidence: commands and artifacts above; the ledger binds their hashes.
Boundary effects: internal native C synchronization, shared upload/streaming flush,
provider telemetry, native queue error delivery, and registered host regressions.
