# Bring-Up Status (2026-02-24)

## Completed

1. Created lane-local working directories:
   - `artifacts/`
   - `cache/`
   - `notes/`
2. Bootstrapped `depot_tools` at:
   - `nursery/fawn-browser/depot_tools`
3. Started Chromium checkout with:
   - `fetch --nohooks --no-history chromium`
4. Verified Chromium source tree exists at:
   - `nursery/fawn-browser/src`
5. Recorded local `src` revision:
   - `5ffed8f84d` (short SHA at check time)
6. Added `.gitignore` coverage for large lane artifacts and metadata:
   - `.gclient*`, `.gcs_entries`, `_bad_scm/`, `depot_tools/`, `src/`, `out/`, `artifacts/`, `cache/`.
7. Added Chromium integration touchpoint mapping:
   - `notes/chromium-touchpoints.md`
8. Added module/runtime contract skeleton set under:
   - `contracts/`
9. Unblocked one major sync failure by temporarily disabling one local DEPS entry:
   - `src/content/test/data/gpu/meet_effects` condition set to `False` in local `src/DEPS`
   - reason: repeatable checksum mismatch on `meet-gpu-tests/873777508.tar.gz`
10. Re-ran `gclient sync --nohooks --no-history --jobs 1` successfully after the local DEPS workaround.
11. Repaired empty-`HEAD` git dependency checkouts (16 repos), then re-synced to healthy state.
12. Ran `gclient runhooks` to resolve missing generated metadata (`LASTCHANGE.committime`).
13. `gn gen out/fawn_debug --args='is_debug=true'` now succeeds.
14. Unblocked missing `gperf` build dependency without root install by staging a lane-local extracted package.
15. Added lane-local tool/env scripts:
    - `scripts/bootstrap-host-tools.sh`
    - `scripts/env.sh`
16. Staged rootless host-tool binaries in lane cache for:
    - `gperf`, `bison`, `flex`, `m4`
17. Host build tools are now available system-wide (`/usr/bin/gperf`, `bison`, `flex`, `m4`).
18. Verified Chromium build target is now healthy:
    - `autoninja -C out/fawn_debug chrome` -> success (`no work to do` on re-run)
19. Verified built browser binary:
    - `out/fawn_debug/chrome --version` -> `Chromium 147.0.7701.0`
20. Implemented Track A Edit Set 0 scaffolding in local Chromium source:
    - added `--use-webgpu-runtime=auto|dawn|doe`
    - added `--disable-webgpu-doe`
    - added `GpuPreferences` fields for runtime selection and kill switch
    - added mojom + traits serialization wiring and preference parse wiring
21. Revalidated after Edit Set 0:
    - `autoninja -C out/fawn_debug chrome` succeeds
    - `autoninja -C out/fawn_debug gpu_unittests` succeeds
    - `./out/fawn_debug/gpu_unittests --gtest_filter=GpuPreferencesTest.EncodeDecode` passes
22. Implemented Track A Edit Set 1 runtime-selection bridge in local Chromium source:
    - `gpu/ipc/service/webgpu_command_buffer_stub.cc`
    - typed runtime selection decision and fallback reason mapping
    - trace telemetry event for selection decision
    - forced `doe` mode now fails fast when unavailable/disabled
23. Revalidated after Edit Set 1:
    - `autoninja -C out/fawn_debug chrome` succeeds
24. Added Set 2-lite denylist precondition in selector bridge:
    - uses `GPU_FEATURE_TYPE_ACCELERATED_WEBGPU` status from `GpuFeatureInfo`
    - maps denylisted profile precondition to typed fallback reason `profile_denylisted`
25. Revalidated after Set 2-lite:
    - `autoninja -C out/fawn_debug chrome` succeeds
26. Added Track A runtime artifact path plumbing:
    - new switch `--doe-webgpu-library-path`
    - new `GpuPreferences` field `doe_webgpu_library_path`
    - mojom/traits/parse/unittest wiring updated
27. Expanded runtime probe fallback taxonomy in selector seam:
    - `runtime_artifact_missing`
    - `runtime_artifact_load_failed`
    - `symbol_surface_incomplete`
28. Extracted selector policy into reusable helper:
    - `src/gpu/ipc/service/webgpu_runtime_selection.{h,cc}`
29. Added selector policy unit tests:
    - `src/gpu/ipc/service/webgpu_runtime_selection_unittest.cc`
    - verifies mode/denylist/kill-switch/unavailable precedence and outcomes
30. Revalidated after helper + tests:
    - `autoninja -C out/fawn_debug gpu_unittests` succeeds
    - `autoninja -C out/fawn_debug chrome` succeeds
    - `gpu_unittests`:
      - `GpuPreferencesTest.EncodeDecode` passes
      - `WebGPURuntimeSelectionTest.*` passes
31. Updated decoder creation flow to take explicit runtime enum (`kDawn|kDoe`) instead of assuming Dawn.
32. Added concrete Doe execution branch in `WebGPUDecoderImpl`:
    - loads `libdoe_webgpu.so`,
    - builds proc table via `wgpuGetProcAddress`,
    - creates/injects `WGPUInstance`,
    - scopes thread procs during execution/polling,
    - releases instance/library at teardown.
33. Added generated proc-surface include list:
    - `gpu/command_buffer/service/webgpu_proc_table_entries.inc`
34. Updated GPU process proc bootstrap for thread-dispatch mode with Dawn native as default thread procs.
35. Added crash fix in `WebGPUCommandBufferStub` destructor:
    - guard `decoder_context()` before `Destroy(false)` call.
36. Revalidated decoder/proc-dispatch integration:
    - `autoninja -C out/fawn_debug gpu_unittests` succeeds
    - `autoninja -C out/fawn_debug chrome` succeeds
    - `./out/fawn_debug/gpu_unittests --gtest_filter=WebGPURuntimeSelectionTest.*:GpuPreferencesTest.EncodeDecode` passes
37. Forced-Doe headless launch now fails cleanly (no GPU-process null-deref crash) when environment preconditions fail.
38. Ran strict 3-workload comparison subset:
    - `upload_write_buffer_64kb`
    - `compute_workgroup_atomic_1024`
    - `texture_sampler_write_query_destroy`
39. Captured strict subset report with comparable + claimable classification:
    - `/home/x/deco/fawn/bench/out/20260224T140709Z/dawn-vs-doe.tracka.smoke3.json`

## Current State

1. Core Chromium source tree is present and usable for seam mapping and integration edits.
2. `third_party/rust-toolchain` is now present (`VERSION` exists).
3. `gn gen out/fawn_debug --args='is_debug=true'` is healthy.
4. `autoninja -C out/fawn_debug chrome` completes successfully.
5. Chromium output binary is present and executable (`out/fawn_debug/chrome`).
6. Prior `gperf` failure entry in `siso_output.1` is historical and superseded by current successful build state.
7. Track A seam now includes real (partial) Doe decoder/runtime execution wiring, not only selector telemetry.
8. In this host's headless profile, forced Doe is currently rejected as `profile_denylisted`; this is environment gating, not immediate proof of integration failure.

## Smoke Evidence (2026-02-24)

1. Forced-Doe launch command shape:

```bash
out/fawn_debug/chrome --headless=new --no-sandbox --disable-dev-shm-usage --use-webgpu-runtime=doe --doe-webgpu-library-path=/home/x/deco/fawn/zig/zig-out/lib/libdoe_webgpu.so
```

2. Observed result:
   - browser starts,
   - adapter request path resolves null under denylisted profile,
   - rejection reason is `profile_denylisted`,
   - prior destructor crash is no longer observed.
3. Strict comparison subset report:
   - `/home/x/deco/fawn/bench/out/20260224T140709Z/dawn-vs-doe.tracka.smoke3.json`
   - `comparisonStatus = comparable`
   - `claimStatus = claimable`

## Operational Cautions

1. Chromium `src/` in this lane is intentionally dirty with in-flight Track A edits.
2. Do not run destructive cleanup/reset in `src/` unless explicitly requested.
3. A long-running benchmark process may already be active:
   - `python3 bench/compare_dawn_vs_doe.py --config bench/compare_dawn_vs_doe.config.amd.vulkan.release.json ...`
   - keep it running unless explicitly asked to stop it.

## Immediate Next Bring-Up Commands

From `fawn/` root:

```bash
cd nursery/fawn-browser
./scripts/bootstrap-host-tools.sh
source ./scripts/env.sh
fetch --nohooks chromium
cd src
gclient sync --nohooks --no-history --jobs 1
gclient runhooks
gn gen out/fawn_debug --args='is_debug=true'
autoninja -C out/fawn_debug chrome
```

If sync retries persist, keep `--jobs 1` and retry until repo health is restored.

If build fails, inspect the first concrete failed action:

```bash
cd nursery/fawn-browser/src
ls -1 out/fawn_debug | rg failed_commands
```

Then ensure lane-local tool path is active and resume build:

```bash
cd nursery/fawn-browser
source ./scripts/env.sh
cd src
autoninja -C out/fawn_debug chrome
```

## Integration Readiness Impact

1. Track A seam mapping can begin now against local files.
2. Local environment is now set for repeated bring-up without root package installs.
3. Full local `chrome` build milestone is complete.
4. Track A Edit Set 0 (selector+kill-switch plumbing) is complete.
5. Track A Edit Set 1 (runtime selection bridge) is complete with Dawn-default behavior preserved.
6. Track A Edit Set 2 is partially complete:
   - selector preconditions include denylist + runtime artifact probing with typed reasons.
7. Track A Edit Set 3 has unit-test coverage for selector decision policy.
8. Runtime execution wiring is now partially landed in decoder/proc-dispatch path.
9. Next milestones:
   - validate forced-Doe on non-denylisted GPU host/session,
   - add direct tests for decoder Doe init/teardown failure paths,
   - continue adapter-level denylist detail propagation and Dawn-native dependency audit in Doe path.
