# Metal program identity and completion checkpoint

Base: `df3385ca131596218b1534c83c1503ca95b05585`. This continues the
[completion checkpoint](../20260920-zig-metal-completion/README.md), preserving
the texture and sampler repairs. This is command-runtime source and host-test
evidence, not ordinary-package or physical Metal qualification.

## Implemented contracts

`metal_completion.zig` owns submitted references until each native status is
terminal. Its result distinguishes success, native failure and unknown completion.
An unknown status retains the reference and prevents upload recycling, deferred
release and surface replacement. A later success cannot erase an earlier native
error code. Reentrant submission or retirement during a native wait is rejected.
Reservation precedes submission; allocation failure cannot lose a committed
reference. Terminal failure permits retirement but remains a reported error.
The void destructor waits for terminal ownership; it has no bounded timeout.

`metal_runtime_resources.zig` resolves the requested WGSL path and reads its
actual bytes before looking up a pipeline. Cache entries own source bytes and
native references; identity includes the canonical path, selected entrypoint and
compiler source identity. Translation options are fixed by that compiler build;
this command API supplies no override values. Changed bytes compile a replacement
before the previous owner is retired. Failed translation, native acquisition,
publication or retirement preserves the old owner. A missing source cannot be
rescued by a stale cache entry. Warmup keys retain the exact absolute path and
entrypoint. There is one WGSL translation attempt, without a sibling MSL file or
alternate translator substituting for the requested program.

The compiler returns selected-entrypoint workgroup and binding metadata from the
same analyzed module used for MSL emission. Buffer metadata includes a checked
minimum byte extent. `metal_kernel_dispatch.zig` checks the complete binding list,
group-to-slot mapping, duplicate slots, resource kind, visibility, declared buffer
type, aligned offsets, minimum size and checked ranges before buffer acquisition
or encoding. Aliases reserve their largest required extent independent of order.
Pipeline creation currently precedes binding validation because it supplies the
metadata. Unsupported layouts fail explicitly; they are never skipped.

The checked compute-encoder bridge validates pipeline workgroup limits, device
identity and buffer extents before encoding. It preserves offsets and passes
binding-visible lengths to runtime-array bounds. Warmup, streaming and timed
kernel execution use this path. The legacy no-op/indirect dispatch and render
bridge entrypoints still need equivalent encoder-failure contracts.

## Migration and costs

Extensionless command kernels resolve to `.wgsl`; explicit `.wgsl` names remain
exact. Explicit `.metal` command kernels now return `UnsupportedKernelLanguage`:
this path lacks a compiler-owned raw-MSL layout contract. Ordinary native MSL
entrypoints are separate and unchanged. Nonbuffer, overflowing or reserved-slot
command layouts return `UnsupportedBindingLayout`; both errors map to the
existing `unsupported` status. Invalid ranges and missing bindings remain errors.
The default no-op dispatch now requests the existing WGSL source explicitly.

Private bridge signatures, the symbol manifest, internal Zig reflection metadata,
pipeline ownership and test inventory change together. Public descriptor and
receipt fields keep their schemas; existing status/message fields carry these
errors. No policy knob, threshold, accepted binary or evaluator is changed.
Schema and correctness gates in `docs/process.md` remain applicable. This is an
internal contract migration, not a claim that the ordinary native API is fully
qualified or that raw-MSL command execution has been implemented.

Every cache lookup now reads the source, and entries retain its bytes. Pipeline
and buffer-pool total retention still lack the bounded policy examination in the
queue. No cache expansion or performance claim is justified by these repairs.

## Reproduction and acceptance

Run from the repository root with Zig 0.15.2 on PATH:

```bash
(cd runtime/zig && zig build test test-core test-full test-wgsl doe-runtime -Doptimize=ReleaseFast --summary all)
(cd runtime/zig && zig build test -Dtest-filter='Metal repair proof' --summary all)
python3 bench/gates/schema_gate.py
python3 -m unittest bench.tests.test_doc_link_coverage
python3 runtime/zig/tools/review_log.py --write --base-ref df3385ca131596218b1534c83c1503ca95b05585
python3 runtime/zig/tools/review_log.py --check --base-ref df3385ca131596218b1534c83c1503ca95b05585
```

The final receipts are linked in [acceptance.md](acceptance.md). Intermediate
logs are retained as diagnostics: an old pipeline test fixture required the new
owned fields, and treating a non-Metal stub as an indefinitely unknown native
submission caused an intermediate host test to wait indefinitely. The stub now
reports terminal unsupported failure; actual Metal distinguishes unknown status.
No intermediate run grants acceptance.

Host probes cover source replacement, a conflicting `.metal` sibling, alternate
entrypoints, failed replacement, missing source, group/offset preservation,
alias extents, overflow and unsupported layouts. Completion probes cover unknown
then terminal status, first-error preservation, allocation failure and reentrant
waits. These probes inject bridge behavior and do not execute Metal.

The physical repair fixture adds independently expected grouped/offset readback,
guard bytes, short-range rejection, selected workgroup size, runtime-array length
and recompilation after replacing the source. Existing sampler, layered/padded
texture and staged-write fixtures remain. The [Apple host probe](physical-availability.log)
timed out connecting to `mac.lan:22`. Linux skips the hardware fixtures; Apple SDK
compilation and physical outputs remain unestablished.

## Remaining owner actions

- Completion/queue: implement the configured wait/timeout contract without
  retiring unknown work. Ordinary-native callback and teardown reentrancy need
  their own lifetime examination; the command owner guard does not qualify them.
- Kernel/resources: qualify checked Objective-C encoding on Apple hardware;
  extend checked encoding to legacy direct/indirect and render consumers. Inspect
  cache capacity and archive observations with their owners, and retain native
  compile diagnostic text rather than just its typed failure.
- Surface: transactional configuration/layer replacement and real capability
  admission remain open. Flushing before release does not repair those decisions.
- Qualification: run Apple SDK compilation and the physical fixture, then qualify
  a corrected package. Neither the Linux executable build nor passing host tests
  replaces accepted release archives. A/A calibration remains a separate frozen
  accepted-package experiment, restarted only after host builds finish.

The ledger records owner-specific continuation. Supporting compiler, bridge and
fixture changes receive no automatic file-review credit. No directory or Metal
subsystem completion is claimed; the next never-examined file remains
`runtime/zig/src/backend/ports/telemetry.zig` after consequential owner repairs.

Component: Metal command completion, program acquisition and kernel bindings.
Intent: preserved.
Acceptance evidence: acceptance.md and retained command receipts.
Boundary effects: internal compiler reflection and Metal bridge contracts,
command cache ownership and errors; no public schema or charter change.
