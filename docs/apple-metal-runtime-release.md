# Apple Metal runtime release bundle

This document is the Apple-local runtime release receipt for Doe.

Use it for the exact bundle entrypoint and artifact map. Use `docs/status.md`
for the current Apple claim language and caveats.

## Canonical command

```bash
python3 bench/runners/publish_apple_runtime_release.py --timestamp 20260328T031800Z
```

The current published Apple bundle on this host is:

- `bench/out/apple-runtime-release/20260328T031800Z/apple_runtime_release_manifest.json`

The manifest records:

- the raw and stripped `libwebgpu_doe.dylib` paths
- SHA-256 hashes, sizes, strip command, and dependency list under `artifact`
- the exact build + runner invocations under `invocation`
- the bound runtime receipts under `artifacts`

## Bound runtime receipts

The current manifest ties one Apple runtime deliverable to:

- drop-in ABI evidence:
  - `bench/out/apple-runtime-release/20260328T031800Z/dropin_report.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/dropin_symbol_report.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/dropin_behavior_report.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/dropin_benchmark_report.json`
- native consumer evidence:
  - `bench/out/apple-runtime-release/20260328T031800Z/apple_runtime_consumer_report.json`
- runtime compare + backend-gate evidence:
  - `bench/out/apple-runtime-release/20260328T031800Z/apple_metal_compare_dev.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/metal_sync_conformance_gate.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/metal_timing_policy_gate.json`
- CTS release publication:
  - `bench/out/apple-runtime-release/20260328T031800Z/cts_baseline.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/cts_trend.json`
- runtime footprint publication:
  - `bench/out/apple-runtime-release/20260328T031800Z/runtime_footprint_report.json`
  - `bench/out/apple-runtime-release/20260328T031800Z/runtime_footprint_report.md`

`config/webgpu-cts-evidence.json` now points at that bundle CTS baseline.

## Apple package companion receipts

The current Apple package receipts that sit beside the runtime bundle are:

- Bun Gemma64 claimable:
  - `bench/out/apple-metal/20260328T035500Z/gemma64.bun-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T035500Z/gemma64.bun-package.warm.ir.compare.json`
- Bun Gemma1B claimable:
  - `bench/out/apple-metal/20260328T035500Z/gemma1b.bun-package.ir.compare.json`
  - `bench/out/apple-metal/20260328T035500Z/gemma1b.bun-package.warm.ir.compare.json`
- Node/Dawn Gemma64 explicitly unsupported on `mac.lan`:
  - `bench/out/apple-metal/20260328T040500Z/gemma64.node-package.ir.workspace/inference_gemma3_270m_prefill_64tok_decode_64tok/right/node_webgpu_package.run000.meta.json`
- Node/Dawn Gemma1B explicitly unsupported on `mac.lan`:
  - `bench/out/apple-metal/20260328T040500Z/gemma1b.node-package.ir.workspace/inference_gemma3_1b_prefill_64tok_decode_64tok/right/node_webgpu_package.run000.meta.json`

## Scope

This is Apple Metal evidence only.

It is sufficient for:

- Apple-local runtime receipts
- Apple-local package claims that name the exact Bun workloads/runtimes

It is not sufficient for:

- a broad runtime-replacement claim
- a non-Apple package-performance claim
- conformance language
