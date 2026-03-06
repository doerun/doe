# @simulatte/webgpu

Canonical Doe WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

Repository source currently lives under `nursery/webgpu-core/`, but the public
package identity is `@simulatte/webgpu`.
The old package names `@doe/webgpu-core` and `@doe/webgpu` are legacy
identities, not the canonical contract.

## Positioning

- This package is for compute benchmarking, runtime diagnostics, and artifact-driven validation.
- This package is not a browser-parity WebGPU SDK.
- This package does not claim drop-in compatibility with npm `webgpu` object-model consumers.

## Current status

- Latest local Apple Metal strict comparable matrix:
  `bench/out/apple-metal/20260306T143316Z/dawn-vs-doe.local.metal.extended.comparable.json`
  with `comparisonStatus=comparable`, `claimStatus=claimable`, and `30 / 30`
  comparable workloads claimable.
- Latest local AMD Vulkan strict comparable matrix:
  `bench/out/amd-vulkan/extended-comparable/20260302T182311Z/dawn-vs-doe.amd.vulkan.extended.comparable.json`
  with `comparisonStatus=comparable`, `claimStatus=diagnostic`, and `12 / 14`
  workloads claimable in the full matrix.
- The package surface is stable for headless benchmarking/CI workflows:
  `createDoeRuntime`, `runDawnVsDoeCompare`, `fawn-webgpu-bench`,
  `fawn-webgpu-compare`, and minimal in-process provider helpers.
- Latest local Node package-surface comparison against npm `webgpu`:
  `bench/out/node-doe-vs-dawn/doe-vs-dawn-node-2026-03-06T152824871Z.json`
  with `5 / 8` comparable workloads claimable for `@simulatte/webgpu`; wins are
  concentrated in upload-heavy workloads, while compute end-to-end workloads are
  still slower in this lane.
- Bun direct FFI remains available as a prototype path; no published
  competitor-comparison artifact is claimed for Bun yet.
- Browser-parity WebGPU, presentation, and broad npm `webgpu` compatibility are
  intentionally out of scope for v1.

## Stable contract (v1)

The package is intentionally contract-first around two stable CLIs and one Node runtime bridge:

1. `fawn-webgpu-bench`
2. `fawn-webgpu-compare`
3. Node API: `createDoeRuntime(...)`, `runDawnVsDoeCompare(...)`
4. Minimal in-process WebGPU compatibility API:
- `create(args?)`
- `globals`
- `setupGlobals(target?, args?)`
- `requestAdapter(...)`
- `requestDevice(...)`

See `API_CONTRACT.md` for canonical signatures and outputs.

## Quick start

### 1) Install from npm

```bash
npm install @simulatte/webgpu
```

The npm package ships the JS bridge and CLIs. Native Doe execution still needs
`doe-zig-runtime` plus `libdoe_webgpu` supplied via env vars or CLI flags.

Monorepo build path for those native artifacts:

```bash
cd ../zig
zig build dropin
```

### 2) Headless Doe bench

Package-installed usage:

```bash
FAWN_DOE_BIN=/abs/path/doe-zig-runtime \
FAWN_DOE_LIB=/abs/path/libdoe_webgpu.dylib \
npx fawn-webgpu-bench \
  --commands ./examples/buffer_upload_1kb_commands.json \
  --trace-jsonl ./out/run.ndjson \
  --trace-meta ./out/run.meta.json
```

Monorepo-local usage:

```bash
cd nursery/webgpu-core
fawn-webgpu-bench \
  --commands ../../examples/buffer_upload_1kb_commands.json \
  --trace-jsonl ./out/run.ndjson \
  --trace-meta ./out/run.meta.json
```

### 3) One-command Dawn-vs-Doe compare

Package-installed usage with explicit config/artifact paths:

```bash
FAWN_DOE_BIN=/abs/path/doe-zig-runtime \
FAWN_DOE_LIB=/abs/path/libdoe_webgpu.dylib \
npx fawn-webgpu-compare \
  --config /abs/path/compare.config.json \
  --out /abs/path/metal.compare.json
```

Monorepo-local usage:

```bash
cd nursery/webgpu-core
fawn-webgpu-compare \
  --config ../../bench/compare_dawn_vs_doe.config.local.metal.extended.comparable.json \
  --out ../../bench/out/metal.npm.compare.json
```

Override paths when needed:

```bash
FAWN_DOE_BIN=/abs/path/doe-zig-runtime \
FAWN_DOE_LIB=/abs/path/libdoe_webgpu.dylib \
fawn-webgpu-bench --commands /abs/path/commands.json
```

### 4) Use as Node WebGPU provider module (Doppler interop)

```bash
cd ../doppler
DOPPLER_NODE_WEBGPU_MODULE=@simulatte/webgpu node tools/doppler-cli.js test-model --surface node
```

By default, the in-process provider behind `create(...)` is loaded from module `webgpu`.
You can override this with:

```bash
FAWN_WEBGPU_NODE_PROVIDER_MODULE=webgpu \
FAWN_WEBGPU_CREATE_ARGS='backend=metal;enable-dawn-features=allow_unsafe_apis' \
node your-script.js
```

## Benchmark note

- Repo benchmark deltas use `((dawn_ms - doe_ms) / dawn_ms) * 100`; positive
  means Doe is faster than Dawn.
- Strict comparable claims require matched workload contracts, deterministic
  trace artifacts, and claimability checks.
- The Node package-comparison lane is separate from strict backend substantiation:
  it measures provider-surface workloads with `performance.now()` and should be
  cited as package/runtime evidence, not as backend claim evidence.
- Detailed benchmark policy and gate definitions live in `bench/README.md`,
  `process.md`, and `API_CONTRACT.md`.

## What we intentionally do not provide in v1

1. Full browser-parity WebGPU object-model emulation (events/lifetimes/presentation stack).
2. Full browser-style API parity or presentation stack behavior.
3. Broad drop-in compatibility guarantees for every third-party `webgpu` consumer.

## What we might add later (only if required)

1. Minimal compute-focused compatibility shim for specific Node consumers.
2. Partial enum/constants compatibility where required by concrete integrations.
3. Wider API parity only when it has direct benchmark/CI value.
