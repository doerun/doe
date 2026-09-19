# D3D12 dispatch file review

Batch base: `ce9d88e0d0fcbe692fb4b09424bc0870f09b1651`.
Scope: `file:src/backend/d3d12/commands/d3d12_dispatch.zig`.
Verdict: **needs_changes**. This examination and its repairs do not complete the
shared synchronization contract. Consumer changes receive no separate file,
directory, relationship, or Windows qualification credit.

## Responsibility and trace

Keep direct and indirect command dispatch under the D3D12 command owner. The
canonical `DispatchIndirectCommand` is an alias of the dimensions payload, not
an externally supplied argument-buffer handle. The provider routes both commands
through `NativeD3D12Runtime`; the runtime owns compiled pipeline preparation and
submission retirement. `DispatchState` owns the pipeline/root/signature and
synchronous command objects. Deferred command lists, allocators, and argument
buffers transfer to a runtime batch whose fence identifies their release point.

The private compile-time adapter supplies the actual C bridge in production and
a recording fixture in tests. It adds no runtime dispatch table. Test handles
and bytecode markers are test-only observations; they are not GPU artifacts.

The complete target was examined for responsibility, API names, dimensions,
unsafe casts, allocation, preparation, encoding, timing, submission, ownership,
errors, retry, and teardown. The callers and native bridge were traced to the
shared completion boundary. The file remains cohesive; no new directory,
registry, or execution interpreter is introduced.

## Resolved findings

- Indirect execution discarded the requested dimensions and read an unwritten
  upload buffer. It now serializes the canonical dimensions before encoding.
  Deferred invocations own distinct buffers, preventing later invocations from
  overwriting earlier GPU inputs. Dispatch-only command signatures pass no root
  signature because they do not update bindings.
- The supposed compiled shader was a handwritten placeholder DXBC array. It is
  removed. The runtime loads `dispatch_noop.wgsl` through the existing kernel
  loader, WGSL-to-HLSL compiler, and DXC path (or its declared compiled-artifact
  candidates). Native pipeline creation consumes those bytes. Compiler/source
  failures remain errors; no invented executable or host substitute is used.
- Partial command acquisition leaked its allocator on command-list failure, and
  block-local cleanup did not cover later encoding failures. Command acquisition
  now publishes only a complete closed pair. Failed acquisition, reset, mapping,
  or close releases locally owned commands and permits retry. Pipeline creation
  also rolls back its root signature on failure.
- A checked C bridge close operation exposes `Close` failure to this path before
  submission. Existing bridge callers keep their ABI; the non-Windows adapter
  explicitly rejects the checked operation. This does not fix the other bridge
  callers' ignored close results.
- Deferred retirement previously allocated after GPU submission. The runtime
  reserves batch and retained-handle storage first, then transfers ownership with
  non-allocating appends. Tests inject allocation failure before native command
  creation. Other paths using `trackDropinSubmission` are not certified by this
  repair.
- Admission uses the same baseline dimension bound as advertised device limits,
  centralized in D3D12 constants. Fence exhaustion is rejected before execution;
  the native device-removal sentinel is never assigned as a submission ID.
- Setup includes pipeline preparation and retirement reservation. Submission
  timing includes execute and signal, plus waiting when requested. Actual
  dispatch submission count is carried in the existing metrics and telemetry
  field; canonical logical operation accounting remains separate. Other command
  kinds clear that observation to unavailable. Historical timings are not
  reinterpreted and no performance comparison is promoted.
- The caller selects synchronous retirement from the configured synchronization
  mode instead of treating nonzero elapsed time as a completion flag. This fixes
  the clock-dependent branch, but the underlying wait still needs the repair
  below.

## Open completion finding

`d3d12_bridge_queue_signal` discards `Signal`'s HRESULT.
`d3d12_bridge_fence_wait` can return after event creation failure, ignores event
registration/wait failures, and treats the device-removal sentinel as completion.
`d3d12_runtime_upload.flushQueue` then calls `noteCompletedFenceWait`, and
`NativeD3D12Runtime.deinit` suppresses flush failure and advances completion.
These paths can retire or reuse resources without established completion.

The next action stays on this scope: introduce checked signal/wait outcomes and
an explicit post-submission failure ownership contract across dispatch, shared
flush, and teardown. Reserve/adopt submitted resources before any fallible
completion operation; preserve them when completion is unknown; distinguish
terminal device loss from completed work. Exercise signal, event-registration,
wait, and device-loss failures before appending a new verdict. Merely returning
an error after submission and running existing cleanup would be unsafe.

Shared `trackDropinSubmission` also frees its copied retained-handle list on
append failure without clearing the caller's copy. The reviewed dispatch path
no longer uses that allocation-after-submit branch, but its other callers need
the same ownership examination during the shared synchronization repair.

## Acceptance and limits

[aggregate.log](aggregate.log) is the complete Zig test run, including formatting,
source layout, import fences, generated inventory, and contract checks.
[targeted-third.log](targeted-third.log) is the focused D3D12 run. Exact executed
and skipped counts belong to those artifacts. Inline regressions are explicitly
registered in aggregate, core, and D3D12 inventories.

Recording tests exercise actual Zig dispatch control flow, argument bytes,
separate deferred ownership, synchronous reuse, acquisition/encoding failures,
retry, and cleanup. The runtime test uses the deliberately unsupported Linux
adapter after retirement reservations and injects allocator failures. Its
success does not mean native D3D12 executed.

Earlier logs are retained: `targeted-first.log` records an incorrect build working
directory, and `targeted-second.log` records a test-fixture name-shadowing error.
Neither is acceptance evidence. The accepted aggregate was run from
`runtime/zig` after correcting those issues.

No Windows device, DXC invocation, native debug-layer execution, ordinary-provider
latency measurement, or physical D3D12 qualification was performed. Accepted
release binaries and frozen performance policy remain unchanged. The Linux
suite validates the affected host code and regression fixtures only.

No public payload, error taxonomy, JSON field, or schema version changes. The
existing command dimensions, sync policy, kernel-root lookup, metrics, and
telemetry contracts are implemented more faithfully. The new checked close
symbol is an additive internal C adapter operation. Existing blocking gate
requirements in `docs/process.md` remain applicable; review coverage itself
remains advisory, and this open finding cannot be converted into verified credit.

## Reproduction

From the repository root, with Zig 0.15.2 on PATH:

```bash
(cd runtime/zig && zig build test -Dtest-filter=D3D12 --summary all)
(cd runtime/zig && zig build test --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref ce9d88e0d0fcbe692fb4b09424bc0870f09b1651
python3 runtime/zig/tools/review_log.py --check --base-ref ce9d88e0d0fcbe692fb4b09424bc0870f09b1651
```

Component: Zig D3D12 command dispatch and submission ownership.
Intent: preserved.
Acceptance evidence: commands and retained logs above; ledger binds their hashes.
Boundary effects: internal C close adapter, runtime retirement, provider metrics,
and generated test inventory. Shared completion remains an open dependency.
