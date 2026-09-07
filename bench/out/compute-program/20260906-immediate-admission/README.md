# Immediate-data admission

`baseline.txt` and `source.patch` bind the native correction, regressions,
capability records, regenerated reports, and acceptance contract. `SHA256SUMS`
binds the retained checkpoint files.

Native compute/render/bundle immediate-data entrypoints previously checked
payload metadata without delivering the bytes to shaders. Some invalid writes
only logged a message, leaving recording and submission usable. Non-empty
payloads now fail with the shared `ImmediateDataUnsupported` cause, report through
existing device validation scopes, and invalidate command/bundle recording.
Non-zero `immediateSize` layouts reject before allocation or binding retention.
Empty calls at offset zero remain harmless. Pass lifetime is checked before
reading its state. Recording failure messages have one shared contract owner.

This is an explicit unsupported boundary, not immediate-data execution. Existing
public signatures and field schemas are unchanged. The behavior migration and
acceptance requirements live in `docs/process.md`. The capability inventory and
backend spec-index cells distinguish native payload execution from ABI wrappers
and provider-backed diagnostic surfaces. `generated-reports.log` checks derived
report content while excluding each generator's `generatedAt` timestamp.

Canonical tests cover compute, render, and bundle rejection, original typed
failure and error-scope text, failed command/bundle publication, null payloads,
layout admission before retaining bindings, and subsequent ordinary layouts.
`debug.log` and `release-fast.log` retain the canonical test and native build-tier
results.

The C fixture `runtime/zig/tests/native_recorded_compute.c` crosses the actual
WebGPU ABI, checks rejection at recording/submission and layout creation, then
executes valid fused compute and ordinary dispatch/texture-copy/readback on the
same physical AMD Vulkan device. Its integer results are independently checked.
`baseline-native-run.log` retains the unsupported-payload assertion failure with
the preceding checkpoint's library, extracted from the platform archive in
`../20260906-pass-lifecycle-qualified/` and bound by `baseline-library.sha256`.
`native-run.log` retains the corrected result from the same fixture executable.

`native.jsonl`, retained SPIR-V, and `native-validation.json` bind compute
execution and completion. They do not replace the C fixture's output assertions.
`native-library.sha256` and `loaded-libraries.log` identify the corrected loaded
library. Its hash equals every host row in
`../20260906-immediate-admission-qualified/summary.json`; the archives there
retain the exact package bytes. Electron qualification covers its main process.

Reproduce from the repository root:

```bash
cd runtime/zig
zig build test test-wgsl dropin dropin-compute dropin-full -Doptimize=ReleaseFast --summary all
zig build test test-wgsl --summary all
cd ../..
mkdir -p bench/out/compute-program/immediate-qualification-tmp
TMPDIR="$PWD/bench/out/compute-program/immediate-qualification-tmp" \
cc -std=c11 -Wall -Wextra -Werror runtime/zig/tests/native_recorded_compute.c \
  -I runtime/zig/vendor/webgpu-headers -L runtime/zig/zig-out/lib \
  -Wl,-rpath,"$PWD/runtime/zig/zig-out/lib" -lwebgpu_doe \
  -o bench/out/compute-program/immediate-qualification-tmp/native-recorded-compute
timeout 30 bench/out/compute-program/immediate-qualification-tmp/native-recorded-compute
cd packages/doe-gpu-linux-x64
node ../doe-gpu/scripts/stage-platform-package.js
cd ../..
TMPDIR="$PWD/bench/out/compute-program/immediate-qualification-tmp" \
python3 bench/cli.py program qualify-package \
  --output bench/out/compute-program/immediate-admission-reproduction \
  --node /usr/bin/node --bun /home/x/.bun/bin/bun \
  --electron /home/x/deco/doe/bench/out/toolchains/electron-43.4.0/node_modules/electron/dist/electron \
  --platform-package doe-gpu-linux-x64 --lifecycle-cycles 3 --timeout-ms 120000
python3 bench/cli.py program verify-native \
  --trace bench/out/compute-program/20260906-immediate-admission/native.jsonl \
  --out bench/out/compute-program/immediate-qualification-tmp/native-validation.json
python3 scripts/generate_webgpu_surface_reports.py
```

The retained run uses `depth-qualification-tmp` for disk-backed scratch storage.
It does not establish native immediate-data execution, complete WebGPU
conformance, physical Metal/D3D12, driver-loss recovery, peak GPU memory,
publication, or an application performance advantage. Existing diagnostic and
historical artifacts retain their original hashes and boundaries.
