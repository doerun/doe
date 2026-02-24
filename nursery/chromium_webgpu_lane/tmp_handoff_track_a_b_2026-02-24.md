# Chromium WebGPU Lane Handoff (Track A/B)

Date: 2026-02-24
Owner handoff scope: Fawn runtime integration into Chromium WebGPU lane, with Dawn fallback preserved.
Workspace root: `/home/x/deco/fawn/nursery/chromium_webgpu_lane`
Chromium source root: `/home/x/deco/fawn/nursery/chromium_webgpu_lane/src`

This document is intended for the next engineer to continue quickly without re-discovering context.

## 1) What was completed

The lane now has a real runtime-selection pipeline and a partial real execution path for Fawn in Chromium WebGPU, while keeping Dawn as fallback.

Implemented and validated:

1. Runtime selection plumbing exists and is wired end-to-end from preferences/switches to WebGPU command buffer startup.
2. Forced mode behavior is strict: `--use-webgpu-runtime=fawn` returns fatal failure if Fawn cannot be used.
3. Fawn availability check moved from a trivial symbol probe to full proc-surface validation via `wgpuGetProcAddress` across a generated proc-table list.
4. Decoder creation now receives an explicit runtime enum (`kDawn` or `kFawn`) instead of assuming Dawn.
5. `WebGPUDecoderImpl` has a Fawn branch that:
   - loads `libfawn_webgpu.so`
   - builds a `DawnProcTable` from `wgpuGetProcAddress`
   - creates `WGPUInstance`
   - injects that instance into the wire server
   - scopes thread procs during command execution and polling
   - releases instance/library during teardown
6. GPU process proc bootstrap changed to thread-dispatch mode with Dawn native as default thread procs. This is required so Fawn can override procs on the relevant thread without global breakage.
7. Crash fix added in `WebGPUCommandBufferStub` destructor: guard `decoder_context()` before calling `Destroy(false)`.

Net effect: Track A seam is no longer just config/telemetry; it has a concrete Fawn runtime execution lane in decoder and proc dispatch.

## 2) Key files changed

Primary changed files:

- `gpu/command_buffer/service/webgpu_decoder.h`
- `gpu/command_buffer/service/webgpu_decoder.cc`
- `gpu/command_buffer/service/webgpu_decoder_impl.h`
- `gpu/command_buffer/service/webgpu_decoder_impl.cc`
- `gpu/command_buffer/service/webgpu_proc_table_entries.inc` (new)
- `gpu/ipc/service/gpu_init.cc`
- `gpu/ipc/service/webgpu_command_buffer_stub.cc`

There are also previously existing lane changes in prefs/switches/mojom/runtime selection helper files that were already in progress and kept.

## 3) Build/test status

Successfully built:

- `autoninja -C out/fawn_debug gpu_unittests`
- `autoninja -C out/fawn_debug chrome`

Successfully ran:

- `out/fawn_debug/gpu_unittests --gtest_filter=WebGPURuntimeSelectionTest.*:GpuPreferencesTest.EncodeDecode`

No failing compiler or linker issues remain for the above targets.

## 4) Smoke evidence gathered

### A) Forced-Fawn Chromium launch

Used:

`/home/x/deco/fawn/zig/zig-out/lib/libfawn_webgpu.so`

Command shape (headless):

`out/fawn_debug/chrome --headless=new --no-sandbox --disable-dev-shm-usage --use-webgpu-runtime=fawn --fawn-webgpu-library-path=/home/x/deco/fawn/zig/zig-out/lib/libfawn_webgpu.so`

Result: browser process launches, but WebGPU adapter request in headless currently resolves to `adapter-null` because runtime selection rejects forced Fawn with reason `profile_denylisted` (GPU feature status in this environment is software/denylisted).

Important: before the destructor null-guard fix, this path caused a GPU-process crash; now it fails cleanly without that null dereference.

### B) 3-workload strict benchmark subset

Ran strict comparable subset:

- `buffer_upload_64kb`
- `workgroup_atomic_1024`
- `texture_sampler_write_query_destroy_contract`

Report:

`/home/x/deco/fawn/bench/out/20260224T140709Z/dawn-vs-fawn.tracka.smoke3.json`

Outcome:

- `comparisonStatus = comparable`
- `claimStatus = claimable`

This confirms the Fawn side runtime is viable in the benchmark harness for representative upload/compute/texture-contract coverage.

## 5) Active background process to avoid disrupting

There is an active long-running comparison process already running outside this handoff task:

- PID seen: `2679440`
- Command: `python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.release.json ...`

Do not kill it unless explicitly asked. It is producing full39 releaseclaim evidence in `/home/x/deco/fawn/bench/out/runtime-comparisons.amd.vulkan.full39.releaseclaim.refreshed`.

## 6) Current git state snapshot

In `src/`, modified and untracked files include the WebGPU runtime-selection and decoder integration files listed above, plus pre-existing lane files (prefs/switches/mojom/runtime-selection helpers). The tree is intentionally dirty as part of ongoing integration. Do not reset/clean indiscriminately.

## 7) What remains to continue (recommended next steps)

Priority continuation plan:

1. Validate forced-Fawn on a non-denylisted GPU configuration.
   - The current headless environment reports `profile_denylisted` for WebGPU.
   - Use a real GPU session (non-headless or appropriately configured test host) and confirm `navigator.gpu.requestAdapter()` returns non-null under forced Fawn.

2. Add focused unit/integration coverage for Fawn decoder branch.
   - Current tests mostly validate runtime selection logic; branch-specific decoder behavior has limited direct test coverage.
   - Add tests around constructor failure paths (library load failure, missing proc symbol, null instance) and clean teardown.

3. Audit Dawn-native dependencies still present in `WebGPUDecoderImpl` and classify by Fawn compatibility.
   - Some paths still have Dawn-native assumptions; one path already guarded (`IsTextureSubresourceInitialized`).
   - Continue reducing implicit native coupling where runtime is Fawn.

4. Add explicit telemetry histogram entries for the new rejection/availability reasons if product owners require non-trace visibility.

5. Run the same acceptance subset with higher iteration counts once host is stable and non-contended.

## 8) Useful commands for next person

Environment:

`cd /home/x/deco/fawn/nursery/chromium_webgpu_lane`
`source ./scripts/env.sh`

Build:

`cd src`
`autoninja -C out/fawn_debug gpu_unittests`
`autoninja -C out/fawn_debug chrome`

Unit smoke:

`out/fawn_debug/gpu_unittests --gtest_filter=WebGPURuntimeSelectionTest.*:GpuPreferencesTest.EncodeDecode`

Forced Fawn launch:

`out/fawn_debug/chrome --use-webgpu-runtime=fawn --fawn-webgpu-library-path=/home/x/deco/fawn/zig/zig-out/lib/libfawn_webgpu.so`

Benchmark subset:

`cd /home/x/deco/fawn`
`python3 bench/compare_dawn_vs_fawn.py --config bench/compare_dawn_vs_fawn.config.amd.vulkan.extended.comparable.json --workload-filter buffer_upload_64kb,workgroup_atomic_1024,texture_sampler_write_query_destroy_contract --iterations 3 --warmup 1 --out bench/out/dawn-vs-fawn.tracka.smoke3.json`

## 9) Practical cautions

- This lane has unrelated in-flight modifications; do not use destructive git commands.
- Forced-Fawn plus denylist is an expected failure mode right now in this environment; treat `profile_denylisted` as environment gating, not necessarily integration breakage.
- Keep `libfawn_webgpu.so` path pinned to `zig/zig-out/lib/libfawn_webgpu.so` and avoid `.zig-cache` artifacts.

