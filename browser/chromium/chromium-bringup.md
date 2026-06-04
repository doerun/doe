# Chromium bring-up and early integration (draft)

## Goal

Start Chromium bring-up for the browser integration layer quickly while keeping:

1. large build artifacts out of git,
2. Dawn fallback intact,
3. integration scope limited to WebGPU runtime seam.

Current milestone state is tracked in:

1. `browser/chromium/bench/workflows/browser-milestones.json`
2. validate with `python3 browser/chromium/scripts/check-browser-milestones.py`
3. gate through `python3 bench/runners/run_blocking_gates.py --with-browser-milestones-gate`

Chromium source checkout readiness is checked separately from repo-owned
browser evidence:

1. diagnostic: `python3 bench/tools/check_chromium_source_checkout.py --source-root browser/chromium/src --root . --json`
2. source-ready gate: `python3 bench/runners/run_blocking_gates.py --with-chromium-source-checkout-gate`
3. source selector gate: `python3 bench/runners/run_blocking_gates.py --with-chromium-source-checkout-gate --chromium-source-require-runtime-selector`
4. Doe dylib proc surface: `python3 bench/runners/run_blocking_gates.py --with-doe-chromium-proc-surface-gate`

## Layout options

Two layouts are supported:

1. Repo-local integration layer:
   - `browser/chromium/`
   - docs, scripts, contracts, and diagnostic artifacts
2. Chromium checkout/build lane:
   - `browser/chromium_webgpu_lane/` for in-tree use, or an external path
     selected by `FAWN_CHROMIUM_LANE_DIR`
   - Chromium source, `depot_tools`, `out/`, and large build artifacts

For a small self-contained setup, you can keep everything under
`browser/chromium`:

1. `depot_tools/`
2. `src/` (Chromium checkout)
3. `artifacts/` (reports, traces, integration notes)
4. `cache/` (optional local caches)

All above are gitignored at repository root.

## Prerequisites

1. Host dependencies for Chromium build environment.
2. `git`, Python 3, and standard Linux build toolchain.
3. Network access to Chromium/depot_tools sources.

## Lane-local helper scripts

Use lane-local scripts so bring-up does not depend on system package installs:

1. `scripts/bootstrap-host-tools.sh`
   - downloads and extracts missing host tools (`gperf`, `bison`, `flex`, `m4`)
     into lane-local cache.
2. `scripts/env.sh`
   - prepends `depot_tools` and cached host-tool binaries to `PATH`.

This keeps a self-contained setup isolated inside `browser/chromium/`.

## Bring-up steps (machine commands)

Example flow from `` root:

```bash
cd browser/chromium
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

## macOS external volume workflow (APFS)

When local disk is constrained, keep Chromium checkout/build state on an APFS
external volume and sync only release artifacts back to local disk.

From `` root:

```bash
cd browser/chromium
./scripts/setup-macos-external-lane.sh /Volumes/chromium-lane
source ./scripts/env.sh

# one-time checkout and sync (runs on external volume via lane symlinks)
fetch --nohooks chromium
cd src
gclient sync --nohooks --no-history --jobs 1
gclient runhooks
gn gen out/fawn_release --args='is_debug=false is_official_build=true dcheck_always_on=false chrome_pgo_phase=0 symbol_level=0 blink_symbol_level=0 v8_symbol_level=0 is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false'
autoninja -C out/fawn_release chrome

# copy runnable release artifacts to local lane output
cd ..
./scripts/sync-release-artifacts-local.sh
```

For incremental rebuilds after initial setup:

```bash
cd browser/chromium
./scripts/build-release-external.sh
```

If you changed only Doe runtime code on macOS and want the current Fawn app
bundle to launch with the newest Doe library without rebuilding Chromium:

```bash
cd browser/chromium
./scripts/refresh-doe-app.sh
```

## Linux external volume workflow (ext4/xfs)

When local disk is constrained, keep the Chromium checkout and caches on an
external path and sync only release artifacts back locally:

From `` root:

```bash
cd browser/chromium
./scripts/setup-linux-external-lane.sh /mnt/chromium-lane
source ./scripts/env.sh

# one-time checkout and sync (runs on external path via lane symlinks)
fetch --nohooks chromium
cd src
gclient sync --nohooks --no-history --jobs 1
gclient runhooks
gn gen out/fawn_release --args='is_debug=false is_official_build=true dcheck_always_on=false chrome_pgo_phase=0 symbol_level=0 blink_symbol_level=0 v8_symbol_level=0 is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false'
autoninja -C out/fawn_release chrome

# copy runnable release artifacts to local lane output
cd ..
./scripts/sync-release-artifacts-local.sh
```

For incremental rebuilds after initial setup:

```bash
cd browser/chromium
./scripts/build-release-external.sh
```

Default local release artifact path:

- `browser/chromium/out/fawn_release_local` (literal current output folder name)
- local app bundle is synchronized into the lane-local branded app bundle
- if upstream still emits `Chromium.app`, sync maps it into the branded local app during artifact copy

## Integration starting point

Start with Track A (browser) seam-only work:

1. Keep Chromium behavior identical with default Dawn path.
2. Add explicit runtime selector policy:
   - `dawn`,
   - `doe`,
   - `auto`.
3. Add kill switch and adapter denylist controls.
4. Add structured fallback reason telemetry.

Do not begin with compositor/layout/media refactors.

## Current lane artifact usage (Track A browser)

Use existing drop-in artifact lane as initial test substrate:

1. `runtime/zig/zig-out/lib/libwebgpu_doe_full.{so,dylib,dll}`
2. `config/doe-chromium-proc-surface.json`
3. symbol and behavior gate tools in `bench/`.

Forced-Doe source selection now validates a browser-facing WGPU proc surface,
loads the generated Dawn wire proc table through `wgpuGetProcAddress`, creates
a Doe `WGPUInstance`, and injects that instance into Chromium's WebGPU wire
server. The proc-surface gate proves the Doe dylib exports the direct symbols,
resolves the wire table, maps required browser shared texture, shared buffer,
shared fence, and error-object procs through Doe-local resolver entries before
native fallback, checks that error-object procs allocate tagged Doe handles,
checks that macOS IOSurface shared texture import is native, checks that shared
buffer/fence imports stay explicitly unsupported, and can bootstrap an
instance; it does not by itself promote browser smoke to claimable performance
evidence.

Initial criterion is deterministic compatibility and observability, not performance.

## Integration milestones (early)

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

## Current snapshot (2026-05-30)

Repo-owned browser diagnostics and wrapper selectors exist. The mounted
Chromium source checkout now exposes the source-level runtime selector markers:

- `use-webgpu-runtime`,
- `disable-webgpu-doe`,
- `doe-webgpu-library-path`,
- `runtime_artifact_load_failed`,
- `runtime_initialization_failed`,
- `symbol_surface_incomplete`,
- `wire_proc_table_incomplete`,
- `profile_denylisted`,
- `adapter_denylist_detail`,
- `vendor_id`,
- `blocklist_reason`,
- `doe_shared_image_iosurface_bridge`,
- `doe_present_shared_texture_end_access`,
- `doe_shared_buffer_unsupported`,
- `unknown_selection_error`.

Those markers are checked by
`bench/tools/check_chromium_source_checkout.py --require-runtime-selector`, and
the lane env checkout passes that source selector gate. Forced-Doe selection now
also loads the selected Doe library, checks the browser-facing WGPU proc
surface, resolves the full generated wire table through `wgpuGetProcAddress`,
and owns the injected `WGPUInstance` for forced-Doe wire execution. Source-binary
forced-Doe smoke is now linked through the integration overlay as diagnostic
evidence; promotion to `chromium_runtime_active` still requires acceptance of
the capability rows as passing. Active Doe texture mailbox association now
imports macOS IOSurface-backed shared texture memory through the loaded Doe proc
table, injects the raw Doe `WGPUTexture` into the wire server, and ends shared
texture access on present before marking the shared image cleared. Shared buffer
association now fails closed before wire injection while no native buffer handle
source exists. The Doe drop-in also owns explicit unsupported shared buffer and
shared fence proc mappings so the generated wire table cannot pass by falling
through to native Dawn for browser interop names.
Chromium adapter filtering now formats source-level denylist detail at the
adapter selection point: `adapter_denylist_detail` carries the typed
`profile_denylisted` reason, vendor/device IDs, adapter/backend type, and the
blocklist reason before the adapter is rejected. The source selector gate
requires those detail markers and the formatter unit test.

## Common wrapper scripts

Use wrappers under `browser/chromium/scripts` to avoid hardcoded paths:

1. `scripts/preflight.sh`
   - checks host dependencies and resolves default Chrome + Doe library paths.
2. `scripts/bringup-linux.sh`
   - Linux bring-up wrapper for bootstrap -> fetch -> sync -> hooks -> build.
3. `scripts/run-smoke.sh`
   - runs Playwright smoke harness with resolved `--chrome` and `--doe-lib`.
4. `scripts/run-bench.sh`
   - runs layered superset orchestrator with resolved `--chrome` and `--doe-lib`.
5. `scripts/refresh-doe-app.sh`
   - macOS-only helper that rebuilds Doe drop-in and reapplies the app-bundle
     Doe runtime wrapper after local runtime changes.

## Browser smoke harness

A small Playwright harness now exists for real-browser WebGPU smoke + mini bench comparison:

- `browser/chromium/scripts/webgpu-playwright-smoke.mjs`
- standalone checker: `browser/chromium/scripts/check-browser-smoke-report.py`
- schema: `config/browser-smoke-report.schema.json`
- classification: diagnostic browser evidence (`L1`), not a strict `L0` claim artifact
- checks:
  - `navigator.gpu` + adapter/device availability
  - adapter features + selected limits capture
  - compute correctness smoke (`[1,2,3,4] -> [2,3,4,5]`)
  - render smoke (triangle draw + center pixel validation)
  - render bundle smoke (`createRenderBundleEncoder`/`executeBundles` + center pixel validation)
  - render indirect smoke (`drawIndirect` + center pixel validation)
  - timestamp query smoke (`timestampWrites` + `resolveQuerySet` readback)
  - explicit `requestAdapter({ xrCompatible: false })` forwarding on the package-browser path
  - `queue.copyExternalImageToTexture` end-to-end readback using browser image sources plus `flipY`/origin dictionaries
  - `device.importExternalTexture` plus `externalTexture` bind-group layout/resource sampling from a `VideoFrame`
  - mini timing probes (`queue.writeBuffer` 64KB and compute dispatch us/op)
- output metadata now includes invocation + environment fields (`argv`, `cwd`, node/platform), browser/user-agent evidence, and hash-chain traceability over mode results.

Run from repo root:

```bash
# install runtime dependency once (uses your Chromium binary, no Playwright browser download required)
npm --prefix browser/chromium ci

# compare Dawn vs Doe in one diagnostic report (positive delta => Doe faster, diagnostic only)
./browser/chromium/scripts/run-smoke.sh \
  --mode both \
  --out browser/chromium/artifacts/dawn-vs-doe.browser.playwright-smoke.diagnostic.json
```

By default the harness writes to timestamped lane-local artifacts:

- `browser/chromium/artifacts/<YYYYMMDDTHHMMSSZ>/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`

Validate an existing smoke report without launching Chromium:

```bash
python3 browser/chromium/scripts/check-browser-smoke-report.py \
  --smoke-report browser/chromium/artifacts/<timestamp>/dawn-vs-doe.browser.playwright-smoke.diagnostic.json
```

Optional browser-surface seam:

- pass `--api-surface package-browser` to route the Playwright page through `doe-gpu/browser` instead of talking directly to native `navigator.gpu`
- this path requires the local harness HTTP server because the page imports `packages/doe-gpu/src/browser.js`; the layered harness will fail fast instead of falling back to `data:` URLs in that mode

Guardrail:

- writing under `bench/out` is blocked by default for this harness to avoid accidental claim-lane mixing.
- if you intentionally need `bench/out`, pass `--allow-bench-out` explicitly and keep the artifact labeled diagnostic.

## Artifact discipline

For each integration run, capture:

1. runtime selector mode and selected runtime,
2. fallback reason code (when applied),
3. pipeline/trace/meta artifacts,
4. benchmark/correctness reports and gate outcomes.

Store this harness output under lane-local ignored directories by default.
Only publish to canonical `bench/out/` flows after converting results into strict comparability/claim contracts.

## Layered browser superset harness

The nursery lane now also includes a contract-driven layered harness (`L1` + `L2`) that is generated from the core workload source-of-truth:

- generator: `browser/chromium/scripts/generate-browser-projection-manifest.py`
- runner: `browser/chromium/scripts/webgpu-playwright-layered-bench.mjs`
- checker: `browser/chromium/scripts/check-browser-benchmark-superset.py`
- orchestrator: `browser/chromium/scripts/run-browser-benchmark-superset.py`

Artifacts and contracts:

- `browser/chromium/contracts/browser-benchmark-superset.contract.md`
- `browser/chromium/bench/projection-rules.json`
- `browser/chromium/bench/generated/browser_projection_manifest.json`
- `browser/chromium/bench/workflows/browser-workflow-manifest.json`

Run from repo root:

```bash
./browser/chromium/scripts/run-bench.sh --mode both
```

To exercise the package browser surface explicitly:

```bash
./browser/chromium/scripts/run-bench.sh --mode both --api-surface package-browser
```

Environment note:

- in restricted sandboxes where socket operations are blocked, browser launch can fail before tests run; in that case, run this command directly on the host session where Chromium normally runs.

Default outputs are lane-local diagnostic artifacts under `browser/chromium/artifacts/<timestamp>/...`.
This includes:

- layered report JSON,
- checker JSON,
- summary JSON.

Writing to `bench/out` is blocked by default; pass `--allow-bench-out` only when intentionally publishing a diagnostic artifact path under `bench/out/scratch`.

Runtime note:

- local HTTP server bind is fail-fast by default (no implicit fallback).
- use `--allow-data-url-fallback` only for explicitly diagnostic sandbox troubleshooting.

Cadence:

1. Daily browser smoke run.
2. Twice-weekly layered benchmark run.
3. Weekly promotion review.

Promotion candidates:

1. must keep projection hashes synchronized with active workloads/rules,
2. must include explicit `status` + `statusCode` for required `L1/L2` rows,
3. must carry approvals matching the roles declared by the workflow manifest.

## ORT WebGPU diagnostic harness

There is now a focused Chromium-side ORT WebGPU benchmark runner at:

- `browser/chromium/scripts/webgpu-playwright-ort-bench.mjs`

What it does:

- launches Chromium in `dawn`, `doe`, or `both` runtime modes
- serves the repo root over the same local HTTP harness used by the browser
  smoke path
- loads `onnxruntime-web`'s browser WebGPU bundle from `bench/node_modules`
- benchmarks a small ORT identity workload and a small ORT matmul workload in
  the page, capturing session-create, first-run, and steady-state timings

Run from repo root:

```bash
# diagnostic Dawn-only proof on stock Chrome
node browser/chromium/scripts/webgpu-playwright-ort-bench.mjs \
  --mode dawn \
  --chrome /usr/bin/google-chrome

# real Dawn-vs-Doe browser comparison requires a Doe-enabled Chromium binary
node browser/chromium/scripts/webgpu-playwright-ort-bench.mjs \
  --mode both \
  --dawn-chrome /path/to/chrome-or-chromium \
  --doe-chrome /path/to/fawn-or-doe-enabled-chromium \
  --doe-lib runtime/zig/zig-out/lib/libwebgpu_doe_full.so
```

Guardrail:

- this harness is diagnostic only
- if `doe` mode uses a stock browser executable that ignores Doe runtime
  flags, the results are not a valid Doe-vs-Dawn comparison

Rollback triggers:

1. hand-maintained scenario drift from source workloads,
2. hidden toggles affecting comparability semantics,
3. missing runtime-mode evidence,
4. claim phrasing beyond scenario class.

## Guardrails

1. No hidden runtime switching.
2. No unsupported-capability silent fallback.
3. No claim language from non-comparable runs.
4. No promotion from lane without schema/migration/process/status updates.
5. Forced `--use-webgpu-runtime=doe` must hard-fail if runtime cannot initialize; no silent Dawn substitution.

## Troubleshooting notes (observed)

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
cd browser/chromium
./scripts/bootstrap-host-tools.sh
source ./scripts/env.sh
```

Then rerun `autoninja`.

## Current environment note

If Chromium tools are not currently installed on the machine path, start with:

1. cloning `depot_tools`,
2. bootstrapping lane-local host tools,
3. sourcing lane-local env path setup,
4. validating `fetch`, `gclient`, `gn`, `autoninja`.

## Next continuation targets

Local forced-Doe adapter acquisition is recorded in
`artifacts/20260526T223345Z/dawn-vs-doe.browser.playwright-smoke.diagnostic.json`.
That run also emits browser flight-recorder, shader-link, canvas/WebGPU fusion,
media-path, recovery-parity, CTS-subset, scheduler, WebGPU-effect,
local-AI-workload, pipeline-cache, and fallback-explanation artifacts. These
artifacts remain diagnostic until source-binary forced-Doe smoke is linked to
the integration overlay.
The smoke report itself is now independently checkable through
`scripts/check-browser-smoke-report.py`, including diagnostic partition,
runtime identity, hidden-fallback state, strict-mode evidence, report hash, and
mode-result hash chain.
The smaller runtime-identity artifact is also independently checkable through
`scripts/check-browser-runtime-identity.py`; wrapper probes cannot claim Doe
execution, and Chromium selector evidence must carry explicit no-hidden-fallback
state before `doeRuntimeActive` can be true.
Flight-recorder replay can also run as a standalone blocking-runner gate with
`--with-browser-gpu-flight-recorder-replay-gate`.

Closed in the current source checkout:

- decoder-branch tests now cover successful Doe wire runtime table load,
  instance creation, event processing, owned-instance release, and teardown
  clearing through `DoeWireRuntimeOwnsAndReleasesInstanceLifecycle`.
- active-Doe texture mailbox association now imports macOS IOSurface shared
  texture memory through Doe, begins access on the imported texture, injects the
  raw Doe `WGPUTexture` into the wire server, and ends access during present
  teardown.
- active-Doe shared buffer mailbox association returns `kInvalidArguments`
  before wire injection while no native buffer handle source exists, instead of
  using Dawn-owned shared representations, placeholder buffers, or generated
  Dawn C++ wrappers with Doe handles.
- Doe-local proc mappings now own the browser error-object constructors before
  native fallback; those constructors return Doe-owned releasable handles tagged
  as error objects.
- Doe-local proc mappings now own the browser shared texture, shared buffer,
  and shared fence names before native fallback. Shared texture memory imports
  macOS IOSurface handles through Doe; shared buffer and shared fence paths
  remain explicit unsupported until native handle sources land.
- browser diagnostic selectors now propagate adapter denylist detail through
  forced modes and `auto` fallback rows via `adapterDenylist`.
- Chromium source adapter filtering now emits `adapter_denylist_detail` with
  the profile-denylisted reason, adapter identity fields, and blocklist reason,
  and the source-checkout gate requires that formatter and test marker.

Source-checkout continuation targets:

1. Add a real active-Doe shared-buffer import path once Chromium exposes a supported native buffer handle source.
