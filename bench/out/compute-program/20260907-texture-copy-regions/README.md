# Texture copy regions and admission

`baseline.txt`, `source.patch`, and `SHA256SUMS` bind the correction and retained
evidence. The standard C bridge previously discarded texture origins and aspects
when forwarding buffer/image copies to flattened native entrypoints. The failing
pixel oracle is retained in `baseline-native.log`, alongside the initial C
fixture, executable, and `baseline-library.sha256`. That library is retained in
`../20260907-submit-availability-qualified/`; running the old executable against
a newer library does not reproduce the baseline identity.

A neutral format-layout owner and texture-copy contract now determine block
footprints, mip bounds, selected planes, strides, and the last accessed byte.
Native recording validates device ownership and usages before reserving command
storage or retaining resources. The WebGPU bridge preserves complete origin and
aspect metadata and enforces WebGPU alignment and omitted-stride rules. Existing
flattened native exports keep compact-stride compatibility. Empty copies still
validate their descriptors. Unsupported D3D12 buffer/image recording rejects
explicitly. The internal metadata migration is documented in `docs/process.md`;
public signatures and receipt schemas are unchanged.

The independent C oracle initializes array and volume mips, patches nonzero
origins using padded buffer strides, reads both complete mips and nonzero regions,
and checks modified and untouched pixels. Depth and stencil cases select a single
copyable plane, including combined depth/stencil storage. Invalid ranges, mips,
strides, aspects, and usages must poison recording and reject submission; valid
subsequent work must still complete. Caller references are released before GPU
submission. Canonical tests also exercise arithmetic overflow, compressed physical
mip bounds, empty-copy layout validation, and allocation failure without leases.

Reproduce from the repository revision containing this patch:

```sh
cd runtime/zig
zig build test test-wgsl --summary all
zig build test test-wgsl dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
```

Compile `runtime/zig/tests/native_recorded_compute.c` with the C recipe in
`../20260907-texture-transfers/README.md`, using the newly built native library.
Enable Khronos synchronization validation using that README's extraction and
environment recipe. Reject `Validation Error:` and `SYNC-HAZARD` diagnostics even
when the process exits successfully. Its `validation-tool.sha256` identifies the
layer used here. `vulkan-validation.log` runs the final C fixture with that layer;
`native-run.log` retains the final ordinary physical run. Both pass their output
and error oracles. `native.jsonl` contains earlier and final fixture processes;
`native-validation.json` validates each process sequence, completion, and shader
identity. It does not substitute for the C output oracle.

`debug-initial.log` retains an intermediate compile failure from a Vulkan aspect
constant's namespace. The final canonical runs are `debug.log` and
`release-fast.log`; their exit summaries establish acceptance. `stage.log` records
staging the resulting native binary. `native-library.sha256`,
`loaded-libraries.txt`, and `package-identity.txt` bind the direct C run to the
adjacent `../20260907-texture-copy-regions-qualified/summary.json`. Fresh Node,
Bun, and Electron main-process installations use the same retained archives and
native library. Their streams were checked for validation and synchronization
errors with positive layer activation.
`retained-package-native.log` reruns the final public C fixture against a library
extracted from that exact retained platform archive. Its hash equals the built
library; `retained-package-loaded-libraries.txt` identifies the extracted file
actually selected by the dynamic loader. This checks the public bridge across
the retained binary boundary, independently of the Zig helper tests.

This establishes the exercised AMD Vulkan regions, admission, and lifetimes.
Metal bridge metadata and array/volume routing were updated but not physically
tested. D3D12 testing is also excluded. This evidence does not establish full
WebGPU conformance, concurrent queue safety, physical driver-loss recovery, peak
device memory, registry publication, or an application performance advantage.
