# @fawn/webgpu-node

Headless Doe bridge for browserless benchmarking and CI workflows.

## Positioning

- This package is for compute benchmarking, runtime diagnostics, and artifact-driven validation.
- This package is not a browser-parity WebGPU SDK.
- This package does not claim drop-in compatibility with npm `webgpu` object-model consumers.

## Stable contract (v1)

The package is intentionally contract-first around two stable CLIs and one Node runtime bridge:

1. `fawn-webgpu-bench`
2. `fawn-webgpu-compare`
3. Node API: `createDoeRuntime(...)`, `runDawnVsDoeCompare(...)`

See `API_CONTRACT.md` for canonical signatures and outputs.

## Quick start

### 1) Headless Doe bench

```bash
cd nursery/fawn-webgpu-node
fawn-webgpu-bench \
  --commands ../../examples/buffer_upload_1kb_commands.json \
  --trace-jsonl ./out/run.ndjson \
  --trace-meta ./out/run.meta.json
```

### 2) One-command Dawn-vs-Doe compare

```bash
cd nursery/fawn-webgpu-node
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

## What we intentionally do not provide in v1

1. Full Node N-API WebGPU JS object model (`navigator.gpu`, `GPUDevice`, etc.).
2. Full browser-style API parity or presentation stack behavior.
3. Drop-in compatibility guarantees for third-party libraries expecting npm `webgpu` module semantics.

## What we might add later (only if required)

1. Minimal compute-focused compatibility shim for specific Node consumers.
2. Partial enum/constants compatibility where required by concrete integrations.
3. Wider API parity only when it has direct benchmark/CI value.
