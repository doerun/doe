# Checked direct and indirect Metal dispatch

Base: `8d647be84ee46c72697a4e647f3525d05082b6c8`. This continues the
[program/completion checkpoint](../20260920-metal-program-contract/README.md).

## Failure mechanism and repair

`metal_dispatch_runtime.zig` previously created a command buffer, called a void
encoding bridge, then committed and reported a dispatch. Missing native encoders
or rejected encoding could not reach the caller through that interface. Checked
command completion alone cannot establish that a requested command was encoded.

Direct and indirect commands now share one validation, preparation, encoding and
submission path. Complete command-reference capacity is reserved before native
encoding in both immediate and deferred modes. A missing command, missing encoder
or rejected encoding returns `MetalEncodingFailed`; unsubmitted references are
released and no dispatch result is returned. A created encoder ends on success
and failure. Successful submission transfers exactly one reference into the
existing completion owner, which preserves unknown status and prior failures.

The fixed dispatch program must expose no resource bindings. Its exact compiler
workgroup metadata reaches the bridge without a heuristic replacement. Indirect
argument writes wait for earlier users, check mapped capacity and preserve the
requested dimensions. Checked native indirect dispatch validates argument-buffer
device identity, alignment, extent and workgroup limits before encoding. Direct
and indirect workgroup validation share one native implementation.

The argument layout and alignment follow Apple's
[indirect dispatch contract](https://developer.apple.com/documentation/metal/mtlcomputecommandencoder/dispatchthreadgroups%28indirectbuffer%3Aindirectbufferoffset%3Athreadsperthreadgroup%3A%29?language=objc).
Existing ordinary-native void bridge consumers are unchanged and unqualified by
this repair; the new command path no longer calls them.

## Contract migration

Header, Objective-C implementation, Zig declarations, non-Metal stub, symbol
manifest and generated test inventory change together. The non-Metal bridge
rejects execution explicitly. No public command or serialized receipt field is
added; existing errors carry rejection.

Dispatch measurements now include preparation and earlier-work retirement in
`setup_ns`, synchronous commit plus retirement in `submit_wait_ns`, and deferred
commit cost in `encode_ns` with no claimed wait. Actual submitted commands populate
`submit_count`. These corrections require fresh physical comparisons; historical
timings retain their original meaning. Accepted packages, configurations,
thresholds and comparison procedures are unchanged. Existing schema, correctness,
trace and verification gates from `docs/process.md` remain required.

## File examination and evidence

The whole dispatch file was examined: request admission, pipeline metadata,
argument-buffer ownership, recording rollback, completion transfer, accounting
and host probes. The runtime owns the allocator, cached argument buffer and queue;
the completion owner owns submitted references. Helpers borrow those owners.
Supporting bridge, manifest and fixture edits receive no automatic review credit.

Reproduce from the repository root with Zig 0.15.2:

```bash
(cd runtime/zig && zig build test -Dtest-filter='Metal ' --summary all)
(cd runtime/zig && zig build test test-core test-full doe-runtime -Doptimize=ReleaseFast --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --check --base-ref 8d647be84ee46c72697a4e647f3525d05082b6c8
```

- [Focused host receipt](focused-final.log): injected command/encoder/encoding
  failure, allocation failure before recording, rejection of unexpected shader
  bindings, and successful deferred transfer with exact dimensions/workgroups.
- [ReleaseFast acceptance](acceptance.log): aggregate/core/full suites and Linux
  runtime build, including formatting, imports, source layout, ABI, symbol and
  test-inventory checks. The suites overlap; totals are not unique coverage.
- [Physical availability](physical-availability.log): Apple-host SSH timed out.
  The added Metal fixture checks nonzero indirect offset, short/misaligned ranges,
  invalid workgroups, exact written values and untouched guards, then exercises
  direct and deferred command submission. Linux skips this fixture. Neither Apple
  SDK compilation nor physical Metal success is established here.

Intermediate focused logs retain a test-only pointer coercion compilation error
and an initially stale architecture fingerprint; neither grants acceptance.

## Remaining work

Native render encoders and ordinary-native void consumers still need their own
failure contracts. Queue wait-mode/timeout behavior and teardown of permanently
unknown work remain unresolved. The new native indirect path needs Apple SDK
compilation and physical acceptance, including device-failure cases. Then qualify
a corrected package separately. The next never-examined queue file remains
`src/backend/ports/telemetry.zig`; this repair does not complete Metal.

Component: Metal command dispatch and native bridge.
Intent: preserved.
Acceptance evidence: linked receipts, physical fixture and append-only ledger.
Boundary effects: private bridge ABI, command recording failure propagation,
submission accounting and timing completeness; no public schema change.
