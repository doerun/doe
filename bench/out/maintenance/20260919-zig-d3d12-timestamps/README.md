# D3D12 timestamp review

Batch base: `ec905c6df9f92db5db85e8385156bfc5a9909a93`.
Scope: `file:src/backend/d3d12/commands/d3d12_gpu_timestamps.zig`.
The complete file was examined with its runtime, dispatch, provider, native C,
configuration, and measurement consumers. The ledger owns the verdict. Supporting
edits do not grant other files or directories review credit.

## Responsibility and ownership

The timestamp owner now measures actual command-oriented D3D12 compute work.
Previously it had no recording/readback callers, owned unused command objects,
substituted a clock frequency when unavailable, and mapped without establishing
completion. Its multiplication could overflow before division, and partially
successful initialization could leak or appear initialized on retry.

The owner retains a timestamp query pair and a readback buffer for its runtime's
native device and queue. The query count and buffer size follow the algorithm;
they are not deployment knobs. Acquisition publishes state only when both native
objects exist and a valid queue frequency is available. Failure releases acquired
objects; retry does not inherit partial state. Caller command lists and fences
are borrowed from that same serialized runtime and remain alive through its
completion/retirement barrier. Timestamp state adds no command allocator/list or
Zig heap allocation. Native resource costs remain explicit.

Recording requires initialized state, a future fence value, and one matching
command list. The begin/end timestamp commands bracket direct dispatch,
ExecuteIndirect, or the kernel's repeated dispatch loop. Resolution follows the
end query. Pre-submit failure cancels the pending observation; submitted work
retains it through signal/wait errors. Reuse and mapping require the recorded
fence to complete. The native lost-device sentinel is classified before numeric
comparison. A failed map can be retried after completion. A subsequent invocation
may replace an already completed, uncollected observation; it cannot overwrite
queries still in flight. Destruction follows the existing runtime completion or
terminal-device-loss barrier.

Readback declares the actual CPU read range and no CPU writes on unmap. Timestamp
values are read as little-endian bytes without an alignment assertion. Conversion
uses a wide intermediate and rejects reversed timestamps, zero frequency, and
unrepresentable output. An observed zero duration remains valid; unavailable
measurements retain a false validity flag. Native pointers and HRESULT handling
remain within the D3D12 adapter. The same typed state implementation is used by
production and recording tests.

These checks follow the native [readback synchronization contract](https://learn.microsoft.com/en-us/windows/win32/direct3d12/readback-data-using-heaps)
and [Map range contract](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12resource-map).
They do not establish physical clock accuracy.

## Existing configuration and receipt migration

The existing `GpuTimestampMode`, `QueueSyncMode`, and `DispatchMetrics` contracts
remain authoritative. No serialized field or schema version is added.

| Existing selection | Compute receipt behavior |
| --- | --- |
| `off` | No timestamp acquisition, commands, or mapping; attempted and valid remain false. |
| `auto`, synchronous | Attempts native acquisition; unavailable frequency leaves attempted true and valid false. Native allocation, device-loss, recording, readback, or conversion failures propagate. |
| `require`, synchronous | Missing frequency is `SyncUnavailable`; other failures remain errors. Successful completed observations populate the existing timestamp fields. |
| `auto`, deferred | No timestamp measurement in the immediate receipt; attempted and valid remain false. |
| `require`, deferred | `TimingPolicyMismatch` before runtime initialization, pending-work flush, shader loading, or warmup. |

Provider failures preserve whether timestamp acquisition was attempted and reset
that observation for each new command. Device loss reported during acquisition
or collection marks the runtime lost. Kernel warmup explicitly disables timestamp
capture; the measured kernel span covers the repeated dispatch batch. Duration
uses the native queue frequency, not a fabricated fallback or CPU clock. It
excludes host preparation, waiting, and readback; it is not a CPU/GPU clock
calibration or per-invocation breakdown of a repeated batch.

Host setup includes timestamp preparation. Submission/wait includes native
submission, synchronization, and completed timestamp collection. Deferred kernel
submission now records its actual host submission cost and submission count,
without claiming GPU completion. These existing-field semantic corrections mean
old and new receipts must retain their build identity; earlier reports are not
reinterpreted. No accepted package, release threshold, comparator, or measurement
procedure is changed. `docs/process.md` blocking-gate policy remains applicable.

This scope does not review ordinary WebGPU query sets, render timestamps, all
kernel resource semantics, or the full D3D12 provider. Those retain separate
queue obligations. There is no Windows GPU execution, linked Windows package,
D3D12 debug-layer evidence, latency result, or hardware-support promotion here.

## Acceptance evidence

- [aggregate-final.log](aggregate-final.log): final unfiltered Zig suite, including
  generated test inventory, formatting, architecture/import, and ABI checks.
  Executed and skipped counts remain in the log. The provider admission regression
  calls the real command wrapper on the host instead of skipping it by platform.
- [bridge-probe.log](bridge-probe.log): actual production C timestamp-frequency
  and readback mapping bodies exercised with recording COM methods. It verifies
  failed calls cannot publish a frequency, device-loss classification, read ranges,
  no-write unmap ranges, and failed mapping. Source/body hashes are retained.
- [windows-compile-receipt.txt](windows-compile-receipt.txt): complete bridge
  cross-compilation with pinned Zig and the retained Windows object's digest.
  This validates compilation, not native execution.
- [schema.log](schema.log), [doc-links.log](doc-links.log): schema and documentation
  checks after the implementation and status update.

Zig tests cover transaction rollback and retry, clock errors, timestamp-mode
admission, command-list/device ownership, absent and duplicate recording,
readback before completion, device loss, failed mapping/retry, unmapping on
conversion failure, zero/reversed/overflow arithmetic, direct and indirect query
ordering, cancellation on close failure, and preservation after signal failure.
These are host control-flow checks using production implementations. Kernel
integration is compiled and source-traced; its physical execution remains untested.
Earlier targeted/aggregate logs retain the development attempts, including the
initial fixture compilation error. Only the final artifacts define acceptance.

## Reproduction and continuation

From the repository root with Zig 0.15.2 on PATH:

```bash
(cd runtime/zig && zig build test --summary all)
python3 bench/out/maintenance/20260919-zig-d3d12-timestamps/probe-bridge.py
zig cc -target x86_64-windows-gnu -c runtime/zig/src/backend/d3d12/d3d12_bridge.c -I runtime/zig/src/backend/d3d12 -o /tmp/doe-d3d12-timestamps.obj
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref ec905c6df9f92db5db85e8385156bfc5a9909a93
python3 runtime/zig/tools/review_log.py --check --base-ref ec905c6df9f92db5db85e8385156bfc5a9909a93
```

Next scope: `file:src/backend/d3d12/commands/d3d12_map_async.zig`.
Trace resource selection, map admission, callback/completion delivery, errors,
and retained lifetimes through callers before recording its own verdict.

Component: Zig D3D12 timestamp measurement.
Intent: preserved; real execution now uses the existing native measurement owner.
Acceptance evidence: commands and hash-bound artifacts above.
Boundary effects: command dispatch and provider receipts, kernel submission timing,
internal native clock/map adapters, and test inventory. Public schema unchanged.
