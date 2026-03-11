# Fawn

> **Using the package?** This README is for contributors and developers working
> on Fawn itself. If you installed `@simulatte/webgpu` from npm and want
> quickstart, smoke tests, and API examples, see the
> [package README](nursery/webgpu/README.md).

Fawn is the development platform for Doe, a Zig-first WebGPU runtime centered
on a core technical move: separate hoistable validation from truly dynamic
runtime behavior, keep hot paths explicit, and use Lean only where proofs can
remove runtime branches.

Around that core, Doe follows a broader operating discipline: config as code,
explicit fail-fast behavior, deterministic traceability, and artifact-backed
benchmarking. Fawn develops, verifies, benchmarks, packages, and integrates
Doe across headless execution, Node/Bun package surfaces, and Chromium
bring-up.

Simulatte is the parent organization, Fawn is the development platform and
repo, Doe is the WebGPU runtime, and `@simulatte/webgpu` is the packaged
distribution surface.

Doe (`doe-webgpu`, `libwebgpu_doe.so`) is Fawn's execution engine. It combines
startup-time profile and quirk binding, a native WGSL pipeline (`lexer ->
parser -> semantic analysis -> IR -> backend emitters`), and explicit
Vulkan/Metal/D3D12 execution paths in one system.

Dawn is the incumbent WebGPU implementation in Chromium and the primary
baseline Fawn measures against. Doe is the replacement runtime Fawn is
building: a Zig-first engine with explicit execution paths, selective
Lean-based branch elimination, and benchmark results that are only cited from
reproducible artifacts.

Fawn currently targets Vulkan, Metal, and D3D12. It does not currently pursue
older compatibility backends such as OpenGL or OpenGL ES: the project is
biased toward modern GPU APIs, modern hardware, and modern workloads, and that
narrower target is an advantage because it avoids inheriting legacy backend
complexity just to preserve incumbent-style compatibility breadth.

Lean is additive here, not foundational: it proves and removes specific
hot-path conditions when possible. Zig owns dynamic execution, explicit
fail-fast paths, and the runtime behavior that must remain live.

Doe is the engine. Fawn is everything required to make that engine real,
measurable, and shippable.

![Fawn logo](nursery/webgpu/assets/fawn-icon-main-256.png)

## Benchmark snapshot

Performance claims in Fawn are earned, not asserted. Citable results come
from reproducible artifacts with explicit workload contracts, explicit
comparison modes, and enough timing evidence to satisfy the claim gates in
`process.md` and the Dawn-vs-Doe methodology in `performance-strategy.md`.

Backend-native strict lanes and package-surface comparison lanes are tracked
separately. The evolving ground truth lives in `status.md` and `bench/out/`;
the summary below is only the current top-line read.

### AMD Vulkan (RADV, GFX11)

Latest local strict release artifact:
`bench/out/amd-vulkan/20260310T153903Z/dawn-vs-doe.amd.vulkan.release.json`

- top-level result: `comparisonStatus=comparable`, `claimStatus=diagnostic`
- current strict release lane workload count: 7
- current claimables in the release lane:
  - uploads: `64 KB`, `1 MB`, `4 MB`, `16 MB`, `256 MB`, `1 GB`
- current non-claimable workload: `upload_write_buffer_1kb`
- current release read: strict upload comparability is fixed; the remaining
  blocker is a real tiny-upload gap, not a structural mismatch

This lane is now a workload-specific strict comparable AMD Vulkan evidence
lane. It is not a broad "Doe Vulkan is faster than Dawn" claim.

### Apple Metal (M3)

Current Apple Metal comparable contract:
`bench/workloads.apple.metal.extended.json`

- comparable workloads in contract: 31
- latest full artifact:
  `bench/out/apple-metal/extended-comparable/20260310T121546Z/dawn-vs-doe.local.metal.extended.comparable.rerun.v7.json`
- important caveat: that v7 artifact predates the all-domain repeat-symmetry
  fix; 6 reported claimable rows need a clean Metal rerun before they can be
  treated as trusted claims
- conservative pre-rerun trusted subset: 25 workloads

This lane is not currently a broad "Doe Metal is faster than Dawn" claim. A
fresh Metal rerun is still required to cite the full 31-workload matrix.

### Package surfaces

Package-level Node/Bun evidence is tracked separately from backend-native
strict lanes. Read it through the package README, package-specific compare
reports, and the benchmark cube outputs under `bench/out/cube/latest/`; do not
use those package rows as substitutes for strict backend claim substantiation.

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

Working, with one narrow AMD Vulkan release lane still short of claimability,
one broader Metal comparable lane awaiting a clean rerun, and one separate
package-surface evidence lane:
- AMD Vulkan: `comparisonStatus=comparable`, `claimStatus=diagnostic` for the local 7-workload release matrix. Only remaining blocker in the latest full artifact is `upload_write_buffer_1kb`. This is a narrow workload set, not a broad WebGPU replacement claim.
- Apple Metal M3: the local extended comparable contract currently covers 31 workloads, but the last full artifact predates the all-domain repeat-symmetry fix; a clean Metal rerun is still required before citing all 31 as trusted claims.
- Node package surface: host-local package/runtime evidence lives in the package README and package compare artifacts, not in the strict backend claim lane.

Still in progress:
- render draw path with native render-pass submission, vertex buffers, depth/stencil, pipeline caching, and bind groups; remaining work is about broader coverage and stronger margins outside the current local strict comparable claim snapshot
- texture/raster path with compute texture sampling plus render-draw raster step; broader texture-heavy and raster-heavy matrices still need more evidence than the current local strict claim set
- GPU timestamp readback (returns zero on some adapter/driver combinations)
- broader device/driver coverage for substantiated comparison claims
- upstream quirk mining automation (prototype works; nightly drift ingest is not running)

## Platform flow

Fawn is organized as a platform pipeline, not just a source tree:

`agent` -> `config` -> `lean` -> `zig` -> package/browser surfaces -> `trace` + `bench`

- `agent/`: mines and normalizes upstream quirk and compatibility signals
- `config/`: owns schemas, gates, workload contracts, and migration-visible policy
- `lean/`: proves eliminations and emits artifacts that can remove runtime checks
- `zig/`: implements Doe, the runtime and compiler stack that executes WebGPU work
- `nursery/webgpu/`: packages Doe for Node.js and Bun
- `nursery/fawn-browser/`: carries the Chromium integration lane
- `trace/` and `bench/`: replay work, validate comparability, and produce benchmark evidence

`nursery/` is the home for Fawn's public surfaces and integration lanes; it is
not an incubation-only area.

Supporting docs at the repository root define the operating contract:
`thesis.md`, `architecture.md`, `process.md`, `status.md`, `upgrade-policy.md`,
and `licensing.md`.

## Package

The canonical npm package is `@simulatte/webgpu`, rooted in `nursery/webgpu/`.
It contains the Doe-native Node provider, addon build contract, Bun FFI path,
and CLI tools for benchmarking and CI workflows.

Node is the primary supported package surface. Bun has API parity (61/61
contract tests) via direct FFI; cube maturity remains prototype until cells
are populated by comparable benchmark artifacts.

```bash
# install from npm
npm install @simulatte/webgpu

# build the drop-in library
cd zig && zig build dropin

# publish
cd nursery/webgpu && npm publish --access public
```

## Building and running

Requires Zig 0.15.2 (see `config/toolchains.json`). From `zig/`:

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
