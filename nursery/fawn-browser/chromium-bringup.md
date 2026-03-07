# Chromium Bring-Up and Early Integration (Draft)

## Goal

Start Chromium bring-up for this lane quickly while keeping:

1. large build artifacts out of git,
2. Dawn fallback intact,
3. integration scope limited to WebGPU runtime seam.

## Local Layout (Recommended)

Use directories under `fawn/nursery/fawn-browser`:

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

This keeps all setup isolated inside `nursery/fawn-browser/`.

## Bring-Up Steps (Machine Commands)

Example flow from `fawn/` root:

```bash
cd nursery/fawn-browser
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

## macOS External Volume Workflow (APFS)

When local disk is constrained, keep Chromium checkout/build state on an APFS
external volume and sync only release artifacts back to local disk.

From `fawn/` root:

```bash
cd nursery/fawn-browser
./scripts/setup-macos-external-lane.sh /Volumes/fawn
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
cd nursery/fawn-browser
./scripts/build-release-external.sh
```

Default local release artifact path:

- `nursery/fawn-browser/out/fawn_release_local`
- local app bundle is synchronized as canonical `Fawn.app`
- if upstream still emits `Chromium.app`, sync maps it into local `Fawn.app` during artifact copy

## Integration Starting Point

Start with Track A seam-only work:

1. Keep Chromium behavior identical with default Dawn path.
2. Add explicit runtime selector policy:
   - `dawn`,
   - `doe`,
   - `auto`.
3. Add kill switch and adapter denylist controls.
4. Add structured fallback reason telemetry.

Do not begin with compositor/layout/media refactors.

## Fawn Artifact Usage (Track A)

Use existing drop-in artifact lane as initial test substrate:

1. `zig/zig-out/lib/libwebgpu_doe.{so,dylib}`
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

## Current Snapshot (2026-02-24)

1. `I0` and selector/fallback plumbing milestones are complete locally.
2. Decoder/proc-dispatch seam has a concrete partial Doe execution path:
   - runtime enum threaded into decoder creation,
   - Doe proc table initialized from `wgpuGetProcAddress`,
   - Doe `WGPUInstance` created/injected into wire server,
   - thread-proc scoping active in execution/polling path.
3. Forced-Doe in this host's headless profile currently rejects with `profile_denylisted`; treat as environment gating signal.
4. Strict 3-workload comparison subset report exists and is marked comparable + claimable:
   - `bench/out/20260224T140709Z/dawn-vs-doe.tracka.smoke3.json`

## Common Wrapper Scripts

Use wrappers under `nursery/fawn-browser/scripts` to avoid hardcoded paths:

1. `scripts/preflight.sh`
   - checks host dependencies and resolves default Chrome + Doe library paths.
2. `scripts/bringup-linux.sh`
   - Linux bring-up wrapper for bootstrap -> fetch -> sync -> hooks -> build.
3. `scripts/run-smoke.sh`
   - runs Playwright smoke harness with resolved `--chrome` and `--doe-lib`.
4. `scripts/run-bench.sh`
   - runs layered superset orchestrator with resolved `--chrome` and `--doe-lib`.

## Browser Smoke Harness

A small Playwright harness now exists for real-browser WebGPU smoke + mini bench comparison:

- `nursery/fawn-browser/scripts/webgpu-playwright-smoke.mjs`
- classification: diagnostic browser evidence (`L1`), not a strict `L0` claim artifact
- checks:
  - `navigator.gpu` + adapter/device availability
  - adapter features + selected limits capture
  - compute correctness smoke (`[1,2,3,4] -> [2,3,4,5]`)
  - render smoke (triangle draw + center pixel validation)
  - mini timing probes (`queue.writeBuffer` 64KB and compute dispatch us/op)
- output metadata now includes invocation + environment fields (`argv`, `cwd`, node/platform), browser/user-agent evidence, and hash-chain traceability over mode results.

Run from repo root:

```bash
# install runtime dependency once (uses your Chromium binary, no Playwright browser download required)
npm install --prefix nursery/fawn-browser playwright-core

# compare Dawn vs Doe in one diagnostic report (positive delta => Doe faster, diagnostic only)
./nursery/fawn-browser/scripts/run-smoke.sh \
  --mode both \
  --out nursery/fawn-browser/artifacts/dawn-vs-doe.tracka.playwright-smoke.diagnostic.json \
  --chrome-arg=--ozone-platform=x11
```

By default the harness writes to timestamped lane-local artifacts:

- `nursery/fawn-browser/artifacts/<YYYYMMDDTHHMMSSZ>/dawn-vs-doe.tracka.playwright-smoke.diagnostic.json`

Guardrail:

- writing under `bench/out` is blocked by default for this harness to avoid accidental claim-lane mixing.
- if you intentionally need `bench/out`, pass `--allow-bench-out` explicitly and keep the artifact labeled diagnostic.

## Artifact Discipline

For each integration run, capture:

1. runtime selector mode and selected runtime,
2. fallback reason code (when applied),
3. trace/meta artifacts,
4. benchmark/correctness reports and gate outcomes.

Store this harness output under lane-local ignored directories by default.
Only publish to canonical `fawn/bench/out/` flows after converting results into strict comparability/claim contracts.

## Layered Browser Superset Harness

The nursery lane now also includes a contract-driven layered harness (`L1` + `L2`) that is generated from the core workload source-of-truth:

- generator: `nursery/fawn-browser/scripts/generate-browser-projection-manifest.py`
- runner: `nursery/fawn-browser/scripts/webgpu-playwright-layered-bench.mjs`
- checker: `nursery/fawn-browser/scripts/check-browser-benchmark-superset.py`
- orchestrator: `nursery/fawn-browser/scripts/run-browser-benchmark-superset.py`

Artifacts and contracts:

- `nursery/fawn-browser/contracts/browser-benchmark-superset.contract.md`
- `nursery/fawn-browser/bench/projection-rules.json`
- `nursery/fawn-browser/bench/generated/browser_projection_manifest.json`
- `nursery/fawn-browser/bench/workflows/browser-workflow-manifest.json`

Run from repo root:

```bash
./nursery/fawn-browser/scripts/run-bench.sh --mode both
```

Environment note:

- in restricted sandboxes where socket operations are blocked, browser launch can fail before tests run; in that case, run this command directly on the host session where Chromium normally runs.

Default outputs are lane-local diagnostic artifacts under `nursery/fawn-browser/artifacts/<timestamp>/...`.
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
3. must carry approvals from `track_b_contracts_owner` and `coordinator`.

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
cd nursery/fawn-browser
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

## Next Continuation Targets

1. Validate forced-Doe adapter acquisition on non-denylisted GPU host/session.
2. Add decoder-branch tests for Doe init/load/proc-surface/instance failure and teardown paths.
3. Continue adapter-level denylist detail propagation and Dawn-native dependency audit in `WebGPUDecoderImpl`.
