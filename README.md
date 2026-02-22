# Fawn

A performance-first WebGPU runtime in Zig and Lean 4.

## The problem

WebGPU runtimes like Dawn (C++) and wgpu (Rust) spend most of their CPU time on work that isn't submitting commands to the GPU. Repeated runtime validation, abstraction layering, IPC serialization, and driver workaround branching dominate high-frequency small-dispatch workloads. These costs are structural. You can optimize them within the existing architecture, but you can't eliminate them without changing the architecture.

## Why Zig + Lean

**Zig** — we chose Zig because we need full control of the hot path:

- Allocations are explicit. The language has no hidden allocator, so we know exactly where memory is allocated and freed in the runtime.
- The compiled code does what the source says. We don't deal with vtable dispatch, runtime type info, or implicit indirection — the language doesn't generate them.
- Calling Vulkan/Metal is direct. Zig calls C ABIs natively without bindings layers or marshaling.
- Binaries are small and easy to inspect.

C++ and Rust can achieve the same performance characteristics with enough discipline. Zig makes them the default. For a GPU runtime where CPU-side overhead is the bottleneck, that matters.

**Lean 4** — we use Lean to prove that specific runtime checks are unnecessary, then delete them:

- If Lean can prove a condition holds for all valid inputs, the corresponding runtime branch gets removed from the Zig hot path
- Machine-checked invariants on state machine transitions (command validity, resource lifecycle)
- The runtime gets faster over time as more conditions are proven and removed

The combination is the point. Zig handles execution with minimal overhead. Lean proves which checks can be hoisted out of the runtime entirely. "Leaning out" means deleting runtime code, not adding a proof interpreter to the hot path.

## How we do better

The architecture splits validation into two categories:

**Hoistable checks** — provable from known state at init or compile time:
- Static compatibility constraints
- Structural command validity
- Device limit and profile compatibility

These get resolved once at startup or build time, then never checked again.

**Dynamic checks** — must stay in the runtime:
- Device loss and async lifecycle
- Queue/timeline synchronization
- Memory residency pressure

For the hoistable category:

1. Mine driver quirks from upstream Dawn/wgpu source automatically
2. Normalize them into a schema-first dataset
3. Prove what we can in Lean — delete the runtime branch when proven
4. Pre-filter the rest once at startup by device profile — no per-command quirk matching

The runtime binds a device profile at startup, filters the quirk set once, and buckets by command kind. After that, command dispatch is straight-line execution against pre-resolved actions. No per-command policy lookup. No toggle branching in hot loops. Future work will push more of this to comptime where the profile is known at build time.

## Why this is the future

WebGPU is becoming the portable GPU API. Every browser ships it. Native embeddings are growing. The workloads running through it — ML inference, real-time rendering, compute pipelines — are getting more demanding, and CPU-side runtime overhead is becoming the bottleneck.

The incumbent runtimes were built for correctness and portability first. The spec is stabilizing now, the conformance surface is known, and the driver quirk space is enumerable. That makes it possible to build a runtime that doesn't trade correctness for performance.

- Zig's comptime system opens a path to make per-device specialization a build artifact instead of a runtime cost
- Lean's proof system means validation elimination is mechanically checked, not reviewed by hand
- Both produce small, auditable, reproducible outputs
- As more conditions are proven and hoisted out of the runtime, the hot path gets shorter without losing correctness

## Where we are faster today

Measured on AMD Vulkan (RADV, GFX11), Fawn vs Dawn, with strict apples-to-apples comparability enforcement. All results use operation-level timing, are replay-validated via deterministic hash-chain trace artifacts, and pass claimability checks at both local (7+ samples) and release (15+ samples) thresholds.

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

- Delta: `((dawn_ms - fawn_ms) / dawn_ms) * 100` — positive means Fawn is faster
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
- Lean theorem packs with CI proof execution — proofs exist for core dispatch invariants; automated proof-driven branch elimination is not wired end-to-end
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

Run Dawn-vs-Fawn comparison (requires Dawn build, see `bench/README.md`):

```bash
python3 bench/compare_dawn_vs_fawn.py \
  --config bench/compare_dawn_vs_fawn.config.amd.vulkan.json
```
