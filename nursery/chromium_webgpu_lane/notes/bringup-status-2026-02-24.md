# Bring-Up Status (2026-02-24)

## Completed

1. Created lane-local working directories:
   - `artifacts/`
   - `cache/`
   - `notes/`
2. Bootstrapped `depot_tools` at:
   - `nursery/chromium_webgpu_lane/depot_tools`
3. Started Chromium checkout with:
   - `fetch --nohooks --no-history chromium`
4. Verified Chromium source tree exists at:
   - `nursery/chromium_webgpu_lane/src`
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
    - added `--use-webgpu-runtime=auto|dawn|fawn`
    - added `--disable-webgpu-fawn`
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
    - forced `fawn` mode now fails fast when unavailable/disabled
23. Revalidated after Edit Set 1:
    - `autoninja -C out/fawn_debug chrome` succeeds
24. Added Set 2-lite denylist precondition in selector bridge:
    - uses `GPU_FEATURE_TYPE_ACCELERATED_WEBGPU` status from `GpuFeatureInfo`
    - maps denylisted profile precondition to typed fallback reason `profile_denylisted`
25. Revalidated after Set 2-lite:
    - `autoninja -C out/fawn_debug chrome` succeeds
26. Added Track A runtime artifact path plumbing:
    - new switch `--fawn-webgpu-library-path`
    - new `GpuPreferences` field `fawn_webgpu_library_path`
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

## Current State

1. Core Chromium source tree is present and usable for seam mapping and integration edits.
2. `third_party/rust-toolchain` is now present (`VERSION` exists).
3. `gn gen out/fawn_debug --args='is_debug=true'` is healthy.
4. `autoninja -C out/fawn_debug chrome` completes successfully.
5. Chromium output binary is present and executable (`out/fawn_debug/chrome`).
6. Prior `gperf` failure entry in `siso_output.1` is historical and superseded by current successful build state.

## Immediate Next Bring-Up Commands

From `fawn/` root:

```bash
cd nursery/chromium_webgpu_lane
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
cd nursery/chromium_webgpu_lane/src
tail -n 200 out/fawn_debug/siso_failed_commands.sh
```

Then ensure lane-local tool path is active and resume build:

```bash
cd nursery/chromium_webgpu_lane
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
8. Next milestone is adapter-level denylist detail propagation and actual Fawn runtime execution wiring (current seam still executes Dawn path).
