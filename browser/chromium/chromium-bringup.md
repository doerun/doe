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
gn gen out/fawn_release --args='is_debug=false is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false'
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
gn gen out/fawn_release --args='is_debug=false is_chrome_for_testing=false is_chrome_for_testing_branded=false is_chrome_branded=false'
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
2. symbol and behavior gate tools in `bench/`.

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

## Current snapshot (2026-05-29)

Repo-owned browser diagnostics and wrapper selectors exist, but the mounted
Chromium source checkout inspected on this host did not contain the source-level
runtime selector markers:

- `use-webgpu-runtime`,
- `disable-webgpu-doe`,
- `doe-webgpu-library-path`,
- `runtime_artifact_load_failed`,
- `symbol_surface_incomplete`.

Those markers are now checked by
`bench/tools/check_chromium_source_checkout.py --require-runtime-selector`.
Until that gate passes against `browser/chromium/src`, forced-Doe browser smoke
artifacts remain diagnostic wrapper evidence and must not be described as
Chromium-owned Doe runtime execution.

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
artifacts remain diagnostic until source selector markers and hidden-fallback
state are present in the Chromium checkout.
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

Remaining source-checkout targets:

1. Land the fail-closed source selector markers checked by `--require-runtime-selector`.
2. Add decoder-branch tests for Doe init/load/proc-surface/instance failure and teardown paths.
3. Continue adapter-level denylist detail propagation and Dawn-native dependency audit in `WebGPUDecoderImpl`.
