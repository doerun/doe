# Fawn

Fawn is a Chromium fork that replaces Dawn with Doe as its WebGPU implementation.

**Doe** (`doe-webgpu`, `libdoe_webgpu.so`) is a WebGPU runtime written in Zig. It is a ground-up reimplementation of what Dawn does in C++, built for explicit control of the hot path: no hidden allocators, no vtable dispatch, no bindings layers, direct C ABI calls to Vulkan/Metal/D3D12.

![Fawn logo](nursery/fawn-browser/assets/logo/compiled/linux/fawn-icon-main-256.png)

## Two value propositions

### 1. Zig reimplementation (general-purpose)

Rewriting Dawn's C++ in Zig gives structural performance gains with no proof infrastructure required:

- **Explicit allocators** — no hidden allocation, every alloc/free is visible in source
- **No abstraction tax** — no vtable dispatch, no RTTI, no implicit indirection
- **Direct backend calls** — Zig calls Vulkan/Metal C ABIs natively without marshaling
- **Comptime specialization** — device profile and quirk resolution at build time, not per-command branching at runtime
- **Small auditable binaries**

C++ and Rust can achieve the same with enough discipline. Zig makes these properties the default. This alone produces measurable wins on CPU-bound GPU workloads.

### 2. Lean proof elimination (isolated applications)

For specific, controlled deployment targets (verified WASM games, known-safe assets, embedded GPU workloads), Lean 4 enables a second tier of gains:

- Prove validation invariants offline — bounds checks, compatibility constraints, structural command validity
- Delete the corresponding Zig runtime branches entirely, not just optimize them
- The hot path gets physically shorter: fewer instructions, fewer branches, less code to execute

"Leaning out" means removing runtime code because a proof made it unnecessary. It does not mean adding a proof interpreter to the hot path.

This mode requires ahead-of-time verification of the workload. It is not a general-purpose browser path — it targets isolated applications where the input space is known and provable.

### How both modes work

The architecture splits validation into two categories:

**Hoistable checks** — resolvable from known state at init, build, or proof time:
- Static compatibility constraints
- Structural command validity
- Device limit and profile compatibility

**Dynamic checks** — must stay in the runtime regardless:
- Device loss and async lifecycle
- Queue/timeline synchronization
- Memory residency pressure

For hoistable checks:
1. Mine driver quirks from upstream Dawn/wgpu source automatically
2. Normalize them into a schema-first dataset
3. In Lean mode: prove and delete runtime branches when proof-to-artifact wiring is enforced
4. In Zig-only mode: pre-filter once at startup by device profile — no per-command quirk matching

The runtime binds a device profile at startup, filters the quirk set once, and buckets by command kind. Command dispatch uses pre-resolved actions without per-command quirk matching or profile-table search in hot loops.

## Why this is the future

WebGPU is becoming the portable GPU API. Every browser ships it. Native embeddings are growing. The workloads running through it — ML inference, real-time rendering, compute pipelines — are getting more demanding, and CPU-side runtime overhead is becoming the bottleneck.

The incumbent runtimes were built for correctness and portability first. The spec is stabilizing now, the conformance surface is known, and the driver quirk space is enumerable. That makes it possible to build a runtime that doesn't trade correctness for performance.

## Where we are faster today

Measured on AMD Vulkan (RADV, GFX11), Doe vs Dawn, with strict apples-to-apples comparability enforcement. All results use operation-level timing, are replay-validated via deterministic hash-chain trace artifacts, and pass claimability checks at both local (7+ samples) and release (15+ samples) thresholds.

### Buffer upload throughput

| Workload | p50 faster | p95 faster |
|----------|-----------|-----------|
| 1 KB | +23% | +18% |
| 64 KB | +45% | +40% |
| 1 MB | +36% | +33% |
| 4 MB | +35% | +30% |
| 16 MB | +37% | +34% |

### Compute dispatch

| Workload | p50 faster |
|----------|-----------|
| Workgroup atomic (1024) | +12% |
| Workgroup non-atomic (1024) | +12% |

### Shader compilation

| Workload | p50 faster |
|----------|-----------|
| Pipeline stress (ShaderRobustnessPerf) | +9% |

### How we measure

- Delta: `((dawn_ms - doe_ms) / dawn_ms) * 100` — positive means Doe is faster
- Timing: operation-level from execution trace metadata, not wall-clock
- Comparability: strict mode with fail-fast on mismatched workload contracts
- Claimability: positive deltas required at p50, p95, and p99 for release claims
- Replay: every sample validated via deterministic hash-chain trace
- Workloads: matched command shape, repeat count, buffer usage flags, submit cadence, and normalization divisors

Full comparison reports, trace artifacts, and visualization tooling are in `bench/`.

## What's left

**Working, not yet claimable:**
- Render draw path — native render-pass submission with Dawn-like vertex buffers, depth/stencil, pipeline caching, and bind groups. Currently slower than compute proxy in directional benchmarks. Non-claimable by contract.
- Texture/raster path — compute texture sampling plus render-draw raster step. Currently slower than dispatch-only proxy. Non-claimable by contract.

**Not yet implemented:**
- Lean theorem packs with CI/build proof execution — proofs exist for core dispatch invariants; automated proof-driven branch elimination is not wired end-to-end
- Upstream quirk mining automation — prototype works; nightly drift ingest is not running
- Metal backend — Vulkan-first; Metal is the second lane
- GPU timestamp readback — returns zero on some adapter/driver combinations
- Broader device/driver coverage for substantiated incumbent comparison claims

**The path from here:**
1. Harden render and texture paths to claimable parity
2. Wire Lean proof-driven branch elimination into the build pipeline
3. Bring up Metal backend
4. Expand device coverage beyond AMD Vulkan
5. Automate nightly quirk mining from upstream
6. Reach substantiated "beats incumbents" status across the workload matrix

## Project structure

```
fawn/
  thesis.md          — goals, priorities, success criteria
  architecture.md    — module boundaries, data contracts
  process.md         — pipeline stages, gate policy
  status.md          — current state, benchmark snapshots
  agent/             — upstream quirk mining
  config/            — schemas, gates, benchmark definitions
  lean/              — Lean 4 proofs, verification boundary
  zig/               — runtime (~12,000 LOC)
  bench/             — benchmark harness, Dawn comparison, visualization
  trace/             — replay and trace tooling
  examples/          — worked examples, command seeds
```

## Building and running

Requires Zig 0.14+. From `fawn/zig/`:

```bash
zig build run -- --commands path/to/commands.json --backend native --execute --trace
```

Run Dawn-vs-Doe comparison (requires Dawn build, see `bench/README.md`):

```bash
python3 bench/compare_dawn_vs_doe.py \
  --config bench/compare_dawn_vs_doe.config.amd.vulkan.json
```
