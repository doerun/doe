# Chromium Bring-Up and Early Integration (Draft)

## Goal

Start Chromium bring-up for this lane quickly while keeping:

1. large build artifacts out of git,
2. Dawn fallback intact,
3. integration scope limited to WebGPU runtime seam.

## Local Layout (Recommended)

Use directories under `fawn/nursery/chromium_webgpu_lane`:

1. `depot_tools/`
2. `src/` (Chromium checkout)
3. `artifacts/` (reports, traces, integration notes)
4. `cache/` (optional local caches)

All above are gitignored at repository root.

## Prerequisites

1. Host dependencies for Chromium build environment.
2. `git`, Python 3, and standard Linux build toolchain.
3. Network access to Chromium/depot_tools sources.

## Lane-Local Helper Scripts

Use lane-local scripts so bring-up does not depend on system package installs:

1. `scripts/bootstrap-host-tools.sh`
   - downloads and extracts missing host tools (`gperf`, `bison`, `flex`, `m4`)
     into lane-local cache.
2. `scripts/env.sh`
   - prepends `depot_tools` and cached host-tool binaries to `PATH`.

This keeps all setup isolated inside `nursery/chromium_webgpu_lane/`.

## Bring-Up Steps (Machine Commands)

Example flow from `fawn/` root:

```bash
cd nursery/chromium_webgpu_lane
git clone https://chromium.googlesource.com/chromium/tools/depot_tools.git depot_tools
./scripts/bootstrap-host-tools.sh
source ./scripts/env.sh
fetch --nohooks chromium
cd src
gclient sync
gn gen out/fawn_debug --args='is_debug=true'
autoninja -C out/fawn_debug chrome
```

If `fetch`/`gclient` are unavailable, confirm `depot_tools` is on `PATH`.

## Integration Starting Point

Start with Track A seam-only work:

1. Keep Chromium behavior identical with default Dawn path.
2. Add explicit runtime selector policy:
   - `dawn`,
   - `fawn`,
   - `auto`.
3. Add kill switch and adapter denylist controls.
4. Add structured fallback reason telemetry.

Do not begin with compositor/layout/media refactors.

## Fawn Artifact Usage (Track A)

Use existing drop-in artifact lane as initial test substrate:

1. `zig/zig-out/lib/libfawn_webgpu.so`
2. symbol and behavior gate tools in `bench/`.

Initial criterion is deterministic compatibility and observability, not performance.

## Integration Milestones (Early)

1. `I0`:
   - build Chromium locally with no functional changes.
2. `I1`:
   - wire runtime selection skeleton with no behavior change when disabled.
3. `I2`:
   - add fallback reason telemetry and negative tests.
4. `I3`:
   - run compatibility suites (drop-in + selected browser tests).
5. `I4`:
   - run strict comparability benchmark lanes for claimable paths.

## Artifact Discipline

For each integration run, capture:

1. runtime selector mode and selected runtime,
2. fallback reason code (when applied),
3. trace/meta artifacts,
4. benchmark/correctness reports and gate outcomes.

Store reports under lane-local ignored directories or canonical `fawn/bench/out/` flows as appropriate.

## Guardrails

1. No hidden runtime switching.
2. No unsupported-capability silent fallback.
3. No claim language from non-comparable runs.
4. No promotion from lane without schema/migration/process/status updates.

## Troubleshooting Notes (Observed)

1. If `gclient sync` repeatedly fails on
   `src/content/test/data/gpu/meet_effects:meet-gpu-tests/873777508.tar.gz`
   with checksum mismatch:
   - this may block all GCS-backed dependency fetches.
2. A local-only workaround for bring-up is to disable that single DEPS entry
   in local `src/DEPS` and rerun sync, so required toolchains can still fetch.
3. If `gn gen` fails with missing third-party checkouts where directories exist
   but repo `HEAD` is absent, run targeted dependency repair on those repos
   before attempting full build.
4. If build fails on missing parser/generator tools (`gperf`, `bison`, `flex`,
   `m4`) and root install is unavailable, run:

```bash
cd /home/x/deco/fawn/nursery/chromium_webgpu_lane
./scripts/bootstrap-host-tools.sh
source ./scripts/env.sh
```

Then rerun `autoninja`.

## Current Environment Note

If Chromium tools are not currently installed on the machine path, start with:

1. cloning `depot_tools`,
2. bootstrapping lane-local host tools,
3. sourcing lane-local env path setup,
4. validating `fetch`, `gclient`, `gn`, `autoninja`.
