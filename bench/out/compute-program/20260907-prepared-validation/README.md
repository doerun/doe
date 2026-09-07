# Retained-package Vulkan validation

These observations use the unchanged archives from
`../20260907-render-validation-qualified/`, at the source revision in
`baseline.txt`. They precede the buffer-copy admission correction and do not
inherit its library identity. `SHA256SUMS` binds the retained logs and installed
library identity.

The package was installed into a fresh private project for the preceding render
checkpoint. This run copied that qualification's Node prepared-program, command,
reflection, timestamp, normalization, and resource-retention fixtures into the
same installed project. The exact fixture sources remain in the qualification
directory. Both ordinary and timestamp-enabled prepared-program runs preserve
their original output, lifecycle, cancellation, state-update, and ownership
assertions.

Runs enabled the Khronos layer with `VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_validation`
and `VK_LAYER_VALIDATE_SYNC=1`. `VK_LAYER_PATH` and `LD_LIBRARY_PATH` identify the
extracted layer bound by `../20260907-texture-transfers/validation-tool.sha256`.
There are no Vulkan validation or synchronization-hazard diagnostics in the
completed fixture logs. These are correctness observations, not timings suitable
for comparison.

`textures.log` preserves an initial import-path failure before GPU execution.
`textures-installed.log` uses the existing native texture integration fixture
with its helper's repository import changed to `doe-gpu`; it checks upload,
texture copy, and storage dispatch/readback without changing the shaders or
accepted bytes. The fixture/helper snapshots are retained beside these logs.
A skipped provider is not accepted as a successful texture execution.

Reproduce with the retained-package install recipe in
`../20260907-render-validation/README.md`. Copy the qualified Node fixture to
`<fixture>.mjs` with its retained helper and normalization files. Run
`node <fixture>.mjs` with the same layer environment, and run prepared programs
again with `--timestamps`. Require successful exit, the fixture's completion
messages, and absence of native validation errors in either output stream.

This evidence covers the exercised AMD Vulkan paths only. It does not establish
complete API validation, concurrent queue safety, physical Metal/D3D12,
driver-loss recovery, peak GPU memory, publication, or a performance advantage.
