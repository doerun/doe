# Recorded Vulkan texture transfers

`baseline.txt` and `source.patch` bind the implementation and acceptance changes.
`SHA256SUMS` binds this checkpoint. Existing WebGPU signatures, descriptor fields,
configuration, and trace schemas are unchanged.

Texture-to-buffer copies now enter the GPU command sequence with the actual
destination buffer. They share layout validation and recording with
buffer-to-texture copies, including mip-relative extents, block geometry,
array/volume depth, row/image strides, and the last accessed byte. Transfer
writes become visible to dependent compute or host readback. Empty copies do
not manufacture recorded work. Missing resources fail explicitly. The obsolete
CPU readback implementation and its unused adapter were removed.

The C fixture `runtime/zig/tests/native_recorded_compute.c` checks independently
computed integer outputs through the real WebGPU ABI after caller references
are released. It covers layered readback, untouched row padding, and a resident
storage restore followed by a dependent dispatch. Clearing storage between the
buffer-to-image and image-to-buffer operations makes a skipped restore observable.
The resident case binds storage beyond the backend's promotion threshold;
`vk_resources.zig` allocates that kind without a CPU mapping. Its buffer remains
GPU-resident through the transfer and dependent dispatch. The smaller case uses
the minimum last-accessed source byte count, without final-row padding.

`baseline-accepted-fixture.log` retains both failing output assertions against
the previous library, bound by `baseline-library.sha256`. The baseline library
was extracted from the platform archive in
`../20260906-immediate-admission-qualified/`. `accepted-native-run.log` retains
the corrected result using the same fixture executable. Earlier `baseline-*`,
`native-run.log`, and `native-final-run.log` are intermediate observations as the
fixture gained resident storage, padding, and explicit view checks.

Synchronization validation then exposed an independent image-view creation
error: copy-only textures were given Vulkan image views despite having no view
usage. `vulkan-validation.log` preserves that failure and a deprecated validation
setting warning. Copy-only textures now retain their image and WebGPU view
metadata without allocating Vulkan image views. Sampled, storage, and attachment
textures retain their existing native view path. The final fixture explicitly
creates and releases a copy-only view.

`accepted-vulkan-validation.log` uses the current synchronization setting and
loader diagnostics to identify the loaded Khronos layer. Its error scan must be
empty. `validation-tool.sha256` binds the downloaded Ubuntu validation package
and extracted layer; it was extracted into scratch storage without changing the
host installation. Validation adds execution evidence, not full conformance.
The relevant Vulkan requirement is
[image view usage admission](https://docs.vulkan.org/spec/latest/chapters/resources.html#VUID-VkImageViewCreateInfo-image-04441).

`debug.log` and `release-fast.log` are final canonical tests and native build-tier
results. `pre-validation-*` logs precede the view correction. The removed CPU
readback extent-only test is superseded by shared copy-region validation and the
physical layered/readback checks. `native-library.sha256` identifies the final
library and must equal each controlled host row in
`../20260907-texture-transfers-qualified/summary.json`. That directory retains
the exact wrapper/platform archives installed into fresh Node, Bun, and Electron
main-process projects. `loaded-libraries.log` records the direct C loader path.

`accepted-native.jsonl`, retained SPIR-V, and `native-validation.json` check
shader identity and submission completion. They do not replace the C output
assertions. The earlier `native.jsonl` precedes the view correction. No journal
was produced for the intermediate `native-final-run.log`, whose trace path was
not pre-created; it supplies output observations only.

Reproduce from the repository root:

```bash
cd runtime/zig
zig build test test-wgsl --summary all
zig build test test-wgsl dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
cd ../..
mkdir -p bench/out/compute-program/texture-transfer-reproduction
TMPDIR="$PWD/bench/out/compute-program/texture-transfer-reproduction" \
cc -std=c11 -Wall -Wextra -Werror runtime/zig/tests/native_recorded_compute.c \
  -I runtime/zig/vendor/webgpu-headers -L runtime/zig/zig-out/lib \
  -Wl,-rpath,"$PWD/runtime/zig/zig-out/lib" -lwebgpu_doe \
  -o bench/out/compute-program/texture-transfer-reproduction/native-recorded-compute
touch bench/out/compute-program/texture-transfer-reproduction/native.jsonl
DOE_PROGRAM_IDENTITY_TRACE_PATH="$PWD/bench/out/compute-program/texture-transfer-reproduction/native.jsonl" \
timeout 30 bench/out/compute-program/texture-transfer-reproduction/native-recorded-compute
python3 bench/cli.py program verify-native \
  --trace bench/out/compute-program/texture-transfer-reproduction/native.jsonl \
  --out bench/out/compute-program/texture-transfer-reproduction/native-validation.json
cd packages/doe-gpu-linux-x64
node ../doe-gpu/scripts/stage-platform-package.js
cd ../..
TMPDIR="$PWD/bench/out/compute-program/texture-transfer-reproduction" \
python3 bench/cli.py program qualify-package \
  --output bench/out/compute-program/texture-transfer-reproduction-qualified \
  --node /usr/bin/node --bun /home/x/.bun/bin/bun \
  --electron /home/x/deco/doe/bench/out/toolchains/electron-43.4.0/node_modules/electron/dist/electron \
  --platform-package doe-gpu-linux-x64 --lifecycle-cycles 3 --timeout-ms 120000
```

For synchronization validation, extract `vulkan-validationlayers` with
`apt-get download` and `dpkg-deb -x`. Set `VK_LAYER_PATH` to its extracted
`usr/share/vulkan/explicit_layer.d`, `LD_LIBRARY_PATH` to its extracted
`usr/lib/x86_64-linux-gnu`, `VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_validation`,
`VK_LAYER_VALIDATE_SYNC=1`, and `VK_LOADER_DEBUG=layer`; run the same fixture
and reject any `Validation Error` or `SYNC-HAZARD` output, independently of its
process exit status.

This checkpoint does not qualify non-zero texture origins, all texture aspects,
general concurrent queue use, physical Metal/D3D12, driver-loss recovery, peak
GPU memory, registry publication, or an application performance advantage.
