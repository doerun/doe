# Fawn

Fawn is a Chromium-based browser that replaces Dawn with Doe as its WebGPU implementation.

Doe (`doe-webgpu`, `libdoe_webgpu.so`) is a WebGPU backend written in Zig. It targets explicit allocator control, native Vulkan/Metal/D3D12 backends, and startup-time profile/quirk selection that keeps hot-path policy work out of per-command execution.

![Fawn logo](nursery/fawn-browser/assets/logo/compiled/linux/fawn-icon-main-256.png)

## Benchmark snapshot

Current benchmark evidence is split across strict backend claim lanes and a
separate package-surface comparison lane.

The canonical aggregation layer for those surfaces now lives in the benchmark
cube artifacts:
- timestamped runs under `bench/out/cube/<timestamp>/`
- stable latest outputs under `bench/out/cube/latest/`
- builder: `python3 bench/build_benchmark_cube.py`

### AMD Vulkan (RADV, GFX11)

Latest local strict comparable matrix artifact:
`bench/out/amd-vulkan/20260307T001500Z/dawn-vs-doe.amd.vulkan.release.json`

- top-level result: `comparisonStatus=comparable`, `claimStatus=claimable`
- current strict release lane workload count: 8
- current claimables in the release lane:
  - uploads: `1 KB`, `64 KB`, `1 MB`, `4 MB`, `16 MB`, `256 MB`, `1 GB`, `4 GB`
- current non-claimables in the release lane: none
- current release read: claimable local AMD Vulkan evidence lane for this strict upload matrix

This lane is now fully claimable end-to-end on the local AMD Vulkan host for the strict
8-workload upload release matrix.

### Apple Metal (M3)

Latest local strict comparable matrix artifact:
`bench/out/apple-metal/extended-comparable/20260306T195524Z/dawn-vs-doe.local.metal.extended.comparable.json`

- raw artifact result: `comparisonStatus=comparable`, `claimStatus=claimable`
- publication status: treat this lane as `comparisonStatus=comparable`, `claimStatus=diagnostic`
- comparable workloads in the artifact: 30
- citable claimable workload count: `0 / 30` until the timing-scope audit is closed

**Data quality caveat (blocking publication):** Small-upload workloads in the
Metal extended comparable report show Doe p50 timings in the sub-microsecond
range (e.g. 0.208µs for 1KB upload) while Dawn reports ~189µs for the same
workload. This produces delta percentages exceeding 90,000% which are not
credible speedups. Doe appears to be measuring encode-only latency (no GPU
execution wait) while Dawn includes the full operation. These cells show as
`claimable` in the raw source report, but the timing-scope mismatch must be
resolved before any of these rows are citable.

Full comparison reports, trace artifacts, and visualization tooling are in `bench/`.

### Node package comparison (`@simulatte/webgpu` vs npm `webgpu`)

Latest full local Node provider report:
`bench/out/node-doe-vs-dawn/doe-vs-dawn-node-2026-03-06T214032182Z.json`

- scope: Node.js provider-surface comparison, not strict backend claim substantiation
- host: `darwin arm64`, Node `v22.20.0`
- total compared workloads: `11`
- claimable wins for `@simulatte/webgpu`: `7 / 11`
- current claimable rows in this lane:
  - uploads: `buffer_upload_1kb`, `buffer_upload_64kb`, `buffer_upload_1mb`, `buffer_upload_16mb`
  - overhead: `buffer_map_write_unmap`
  - compute e2e: `compute_e2e_4096`, `compute_e2e_65536`
- current non-claimable rows:
  - comparable but not claimable: `compute_e2e_256`
  - directional/non-comparable: `submit_empty`, `pipeline_create`, `compute_dispatch_simple`

This Node comparison uses package-level workload timing (`performance.now()`) and
should be read as package/runtime positioning evidence, not as a replacement for
strict Dawn-vs-Doe backend reports.

Current caveat:
- Linux Node Doe-native path is wired end-to-end (Linux guard removed).
  No `DOE_WEBGPU_LIB` env var needed when prebuilds or workspace artifacts
  are present.
- Self-contained install ships prebuilt `doe_napi.node` + `libdoe_webgpu` +
  Dawn sidecar per platform. Falls back to node-gyp from source.

Bun has API parity with Node via direct FFI (57/57 contract tests passing).
Bun benchmark lane is at `bench/bun/compare.js` and compares Doe FFI against
the `bun-webgpu` package. Latest validated run (`20260306T215526Z`) shows 7/11
claimable, with compute e2e rows comparable and claimable after readback
validation was added to the timed path. The benchmark cube now isolates the
directional `compute_dispatch_simple` row into its own dispatch-only cell, so
the Bun `compute_e2e` cell reflects the claimable end-to-end rows instead of
being dragged diagnostic by mixed methodology. Cube maturity remains prototype
until cell coverage stabilizes across multiple runs.

Remaining Bun caveats:
- `buffer_map_write_unmap` is slower for Doe (~19µs overhead from synchronous
  `bufferMapSync` polling vs bun-webgpu native async path)
- directional rows (`compute_dispatch_simple`, `submit_empty`) are not
  comparable by design (Dawn async submit vs Doe synchronous)
- upload rows are noisier than compute; claimability is system-state dependent

## How it works

The architecture splits validation into two categories.

Hoistable checks are resolvable from known state at init, build, or proof time: static compatibility constraints, structural command validity, device limit and profile compatibility. Dynamic checks must stay in the runtime regardless: device loss, async lifecycle, queue synchronization, memory residency pressure.

For hoistable checks:
1. Mine driver quirks from upstream Dawn/wgpu source automatically
2. Normalize them into a schema-first dataset
3. Pre-filter once at startup by device profile, bucket by command kind
4. When Lean proofs are available: delete runtime branches entirely via comptime gates

The runtime binds a device profile at startup, filters the quirk set once, and buckets by command kind. Command dispatch uses pre-resolved actions without per-command quirk matching in hot loops.

### Zig runtime

Zig keeps allocation and backend control explicit in source. Backend calls go through native Vulkan/Metal C ABIs, and profile/quirk resolution happens once at startup rather than via per-command matching in hot loops.

### Lean proof elimination

Lean 4 provides an optional second tier. When the runtime is built with `-Dlean-verified=true`, proved conditions can remove specific Zig branches from the quirk dispatch path.

"Leaning out" means removing runtime code because a proof made it unnecessary.

## Proof-driven branch elimination

When Doe is built with `-Dlean-verified=true`, four Lean theorems currently eliminate runtime branches in the dispatch path. Proofs run at build time. The compiled binary has fewer branches. There is no runtime proof interpreter.

| Theorem | What it eliminates | Scope |
|---------|-------------------|-------|
| `toggleAlwaysSupported` | 20 `supportsCommand` switch evaluations per `driver_toggle` quirk | init |
| `requiredProof_forbidden_reject_from_rank` | `requires_lean` check for rejected proof levels | init |
| `strongerSafetyRaisesProofDemand` | `requires_lean` check for critical safety class | init |
| `identityActionComplete` | entire `applyAction` call and 12-entry toggle registry scan | per-command |

The per-command elimination (`identityActionComplete`) hoists the toggle registry linear scan from per-command to init time. Saves ~100-180ns per dispatched command matched by an informational toggle quirk. At 10,000 commands (autoregressive decode or diffusion step loops), this is 1-2ms saved from proof alone.

Build chain: Lean typecheck, `extract.sh` emits `proven-conditions.json`, `build.zig` reads artifact, `lean_proof.zig` validates at comptime, `runtime.zig` uses comptime gate, compiler eliminates unreachable branches.

Build without the flag produces identical code to before.

## Measurement methodology

- Delta: `((dawn_ms - doe_ms) / dawn_ms) * 100`, positive means Doe is faster
- Timing: operation-level from execution trace metadata, not wall-clock
- Comparability: strict mode with fail-fast on mismatched workload contracts
- Claimability: positive deltas required at p50, p95, and p99 for release claims
- Replay: every sample validated via deterministic hash-chain trace
- Workloads: matched command shape, repeat count, buffer usage flags, submit cadence, and normalization divisors

## Current status

Working, with one strict backend lane that is now claimable, one backend lane
under timing-scope audit, and one separate Node package-comparison lane:
- AMD Vulkan: the latest strict comparable/release evidence is `comparisonStatus=comparable`, `claimStatus=claimable` for the local 8-workload upload matrix. This is now a citable local backend claim lane, but it is still a narrow workload set, not a broad WebGPU replacement claim.
- Apple Metal M3: feature coverage is strongest here, but the latest broad comparable artifact is under timing-scope audit and should be treated as diagnostic for publication.
- Node package surface: `7 / 11` claimable wins on the latest macOS Node package lane. This is package/runtime evidence, not backend claim substantiation.

Still in progress:
- render draw path with native render-pass submission, vertex buffers, depth/stencil, pipeline caching, and bind groups; remaining work is about broader coverage and stronger margins outside the current local strict comparable claim snapshot
- texture/raster path with compute texture sampling plus render-draw raster step; broader texture-heavy and raster-heavy matrices still need more evidence than the current local strict claim set
- GPU timestamp readback (returns zero on some adapter/driver combinations)
- broader device/driver coverage for substantiated comparison claims
- upstream quirk mining automation (prototype works; nightly drift ingest is not running)

## Project structure

```
fawn/
  thesis.md            goals, priorities, success criteria
  architecture.md      module boundaries, data contracts
  process.md           pipeline stages, gate policy
  status.md            current state, benchmark snapshots
  licensing.md         license terms
  agent/               upstream quirk mining
  config/              schemas, gates, benchmark definitions
  lean/                Lean 4 proofs, verification boundary
  zig/                 Doe runtime (~12,000 LOC)
  bench/               benchmark harness, Dawn comparison, visualization
  trace/               replay and trace tooling
  examples/            worked examples, command seeds
  nursery/webgpu/      canonical @simulatte/webgpu package root
```

## Package

The canonical npm package is `@simulatte/webgpu`, rooted in `nursery/webgpu/`.
It contains the Doe-native Node provider, addon build contract, Bun FFI path,
and CLI tools for benchmarking and CI workflows.

Node is the primary supported package surface. Bun has API parity (57/57
contract tests) via direct FFI; cube maturity remains prototype until cells
are populated by comparable benchmark artifacts.

```bash
# install from npm
npm install @simulatte/webgpu

# build the drop-in library
cd fawn/zig && zig build dropin

# publish
cd fawn/nursery/webgpu && npm publish --access public
```

## Building and running

Requires Zig 0.15.2 (see `config/toolchains.json`). From `fawn/zig/`:

```bash
# run with trace output
zig build run -- --commands path/to/commands.json --backend native --execute --trace

# build with Lean proof elimination
zig build -Dlean-verified=true

# run tests
zig build test

# build drop-in shared library
zig build dropin

# build macOS app bundle
zig build app
```

Run Dawn-vs-Doe comparison (requires Dawn build, see `bench/README.md`):

```bash
python3 bench/compare_dawn_vs_doe.py \
  --config bench/compare_dawn_vs_doe.config.amd.vulkan.json
```

## Verification gates

Blocking in v0: schema, correctness, trace, verification, and drop-in
compatibility for artifact lanes.
Advisory in v0: performance.

Release requires all blocking gates green. See `process.md` for gate policy and `config/gates.json` for thresholds.

## License

See `licensing.md`.
