# Fawn

Fawn is a Chromium-based browser that replaces Dawn with Doe as its WebGPU implementation.

Doe (`doe-webgpu`, `libdoe_webgpu.so`) is a WebGPU backend written in Zig. It reimplements what Dawn does in C++, built for explicit control of the hot path: direct C ABI calls to Vulkan/Metal/D3D12, explicit allocators, comptime specialization from device profiles.

![Fawn logo](nursery/fawn-browser/assets/logo/compiled/linux/fawn-icon-main-256.png)

## Benchmark snapshot

Current benchmark evidence is split across two active claim lanes.

### AMD Vulkan (RADV, GFX11)

Latest local strict comparable matrix artifact:
`bench/out/amd-vulkan/extended-comparable/20260302T182311Z/dawn-vs-doe.amd.vulkan.extended.comparable.json`

- top-level result: `comparisonStatus=comparable`, `claimStatus=diagnostic`
- comparable workloads: 14
- claimable workloads in that full local matrix: 12
- claimable in the full matrix:
  - uploads: `1 MB`, `4 MB`, `16 MB`
  - compute: `workgroup atomic (1024)`, `workgroup non-atomic (1024)`
  - matrix-vector multiply: `3` variants
  - shader compilation: `Pipeline stress (ShaderRobustnessPerf)`
  - contract lanes: `resource_table_immediates_macro_500`, `surface_presentation_contract`, `concurrent_execution_single_contract`
- current full-matrix non-claimables: `1 KB` and `64 KB` upload

Focused AMD Vulkan reruns in the same local artifact set show claimable single-workload results for
`1 KB` and `64 KB` upload as well:

- `bench/out/amd-vulkan/singles/20260302T192559Z/dawn-vs-doe.amd.vulkan.single.par_buffer_upload_1kb.json`
- `bench/out/amd-vulkan/singles/20260302T192649Z/dawn-vs-doe.amd.vulkan.single.par_buffer_upload_64kb.json`

So AMD Vulkan is the strongest local Dawn-vs-Doe evidence lane in this checkout, but the latest full
comparable matrix is not yet fully claimable end-to-end.

### Apple Metal (M3)

Current status snapshot (`status.md`, dated 2026-03-06) reports:

- `19 of 30` workloads claimable on Apple M3
- stable range: `18-19 / 30`
- claimable workload families:
  - uploads: `1 KB`, `64 KB`, `1 MB`, `4 MB`, `16 MB`, `256 MB`, `1 GB`, `4 GB`
  - compute: workgroup atomic, workgroup non-atomic, `3` matrix-vector variants,
    concurrent execution, zero-init workgroup memory
  - render: redundant pipeline/bindings, draw-throughput macro `200k`
  - misc: async pipeline diagnostics, pixel local storage barrier

Full comparison reports, trace artifacts, and visualization tooling are in `bench/`.

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

Zig gives structural performance gains with no proof infrastructure required. Every allocation is visible in source. Backend calls go through Vulkan/Metal C ABIs directly without marshaling. Device profile and quirk resolution happens at build time through comptime specialization, not per-command branching at runtime.

### Lean proof elimination

For specific deployment targets (verified WASM games, known-safe assets, embedded GPU workloads), Lean 4 enables a second tier. Prove validation invariants offline, then delete the corresponding Zig runtime branches entirely. The hot path gets physically shorter: fewer instructions, fewer branches, less code to execute.

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

Working, with claimable benchmark evidence on two device families:
- AMD Vulkan: latest local strict comparable matrix is `comparable` with `12 / 14` workloads claimable; focused reruns also show claimable `1 KB` and `64 KB` upload slices.
- Apple Metal M3: current status snapshot reports `19 / 30` workloads claimable, stable range `18-19 / 30`.

Still in progress:
- render draw path with native render-pass submission, vertex buffers, depth/stencil, pipeline caching, and bind groups; still slower than the strongest Dawn paths on part of the matrix
- texture/raster path with compute texture sampling plus render-draw raster step; still slower than dispatch-only proxy lanes
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
  nursery/webgpu-core/ canonical npm package implementation for @simulatte/webgpu
```

## Package

The canonical npm package is `@simulatte/webgpu`. Its current implementation
lives in `nursery/webgpu-core/` while directory consolidation is deferred. It
contains the headless Doe bridge, Node/Bun provider entrypoints, and CLI tools
for benchmarking/CI workflows.

```bash
# build the drop-in library
cd fawn/zig && zig build dropin

# publish (from current package implementation root)
cd fawn/nursery/webgpu-core && npm publish --access public
```

## Building and running

Requires Zig 0.14+. From `fawn/zig/`:

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

Blocking in v0: schema, correctness, trace, verification.
Advisory in v0: performance.

Release requires all blocking gates green. See `process.md` for gate policy and `config/gates.json` for thresholds.

## License

See `licensing.md`.
