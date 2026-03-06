# @simulatte/webgpu

Canonical Doe WebGPU package for browserless benchmarking, CI workflows, and
headless runtime integration.

This implementation currently lives under `nursery/webgpu-core/` for directory
continuity, but the public package identity is `@simulatte/webgpu`.
The old package names `@doe/webgpu-core` and `@doe/webgpu` are legacy
identities, not the canonical contract.

## Positioning

- This package is for compute benchmarking, runtime diagnostics, and artifact-driven validation.
- This package is not a browser-parity WebGPU SDK.
- This package does not claim drop-in compatibility with npm `webgpu` object-model consumers.

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

### 1) Headless Doe bench

```bash
cd nursery/webgpu-core
fawn-webgpu-bench \
  --commands ../../examples/buffer_upload_1kb_commands.json \
  --trace-jsonl ./out/run.ndjson \
  --trace-meta ./out/run.meta.json
```

### 2) One-command Dawn-vs-Doe compare

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

### 3) Use as Node WebGPU provider module (Doppler interop)

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

## What we intentionally do not provide in v1

1. Full browser-parity WebGPU object-model emulation (events/lifetimes/presentation stack).
2. Full browser-style API parity or presentation stack behavior.
3. Broad drop-in compatibility guarantees for every third-party `webgpu` consumer.

## What we might add later (only if required)

1. Minimal compute-focused compatibility shim for specific Node consumers.
2. Partial enum/constants compatibility where required by concrete integrations.
3. Wider API parity only when it has direct benchmark/CI value.
