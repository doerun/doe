# Buffer copy admission

`baseline.txt`, `source.patch`, and `SHA256SUMS` bind the correction and retained
evidence. The C reproduction crosses the WebGPU ABI with misaligned offsets and
sizes, out-of-range copies, identical buffers, missing usages, and an empty copy
with invalid usage. `baseline-native.log` records the previous library accepting
the first invalid operation without a device validation error. That baseline is
bound by `baseline-library.sha256` and retained in the platform archive under
`../20260907-render-validation-qualified/`.

Native buffer-copy admission now has one owner, `doe_buffer_copy.zig`. Ordinary
recording checks objects, device identity, usages, alignment, bounds, and distinct
buffers before allocating command/reference storage. Whole-size requests resolve
against the source offset with overflow-safe range checks. Valid empty copies
record no command and acquire no leases; invalid empty copies still fail.
Typed copy failures poison the encoder and enter existing WebGPU validation
scopes. Subsequent finish/submission cannot turn partial recording into success.

Fused native constructors share device/usage/range validation while preserving
their separate disjoint-alias and omitted-copy contract. Public WebGPU commands
reject same-buffer copies, including disjoint ranges. The native fused entrypoint
allows disjoint ranges of one buffer and rejects overlapping ranges; its explicit
zero-sized optional copy remains omitted. No public fields or signatures change.
The migration and acceptance requirements are in `docs/process.md`.

Canonical tests cover whole-size normalization, empty copies, alias policy,
foreign and missing device ownership, invalid objects, missing usages, alignment,
overflow/range failures, admission before failed allocation, and first-error
preservation. Existing allocation-fault and lifetime tests retain their cleanup
assertions using valid buffer declarations. `debug-initial.log` preserves the
initial test failure caused by an old fused-constructor fixture missing device
and usage metadata. `debug.log` and `release-fast.log` are the final canonical
test and native build-tier results.

`native-run.log` requires rejected recording and rejected submission, then valid
single/batched compute and layered GPU transfer output on the same physical AMD
Vulkan device. `vulkan-validation.log` checks the same fixture with Khronos
synchronization validation enabled; no native validation errors are permitted.
The layer identity and extraction recipe remain at
`../20260907-texture-transfers/validation-tool.sha256` and its README.

`native-library.sha256` must equal every controlled-host library hash in
`../20260907-buffer-copy-admission-qualified/summary.json`. That directory retains
the exact package archives installed into fresh Node, Bun, and Electron main
processes. `native.jsonl`, retained SPIR-V, and `native-validation.json` verify
shader identity and completion; C assertions establish the accepted outputs.

Reproduce using the C/build/package recipe in
`../20260907-texture-transfers/README.md`, selecting this checkpoint's current
`runtime/zig/tests/native_recorded_compute.c` and fresh output directories. Enable
the same Khronos layer for the C run and reject validation diagnostics regardless
of process exit. The native admission test deliberately rejects bad requests
before Vulkan sees them.

Earlier prepared-program, timestamp, reflection, resource-retention, and texture
validation observations against the preceding retained package are indexed in
`../20260907-prepared-validation/README.md`. They do not inherit the new library
identity. This correction does not establish complete queue-time resource
validation, texture-origin/aspect conformance, physical Metal/D3D12 behavior,
driver-loss recovery, peak GPU memory, publication, or an application advantage.
