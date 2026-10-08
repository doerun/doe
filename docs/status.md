# Doe status

This page routes current state. Artifacts own counts, timings, hashes, and
verdicts. Historical narrative lives under [`status/archive/`](status/archive/).

| Area | Live status | Ground truth |
| --- | --- | --- |
| Strategy milestones | [`status/runtime-backends-and-bench.md`](status/runtime-backends-and-bench.md) | [`config/doe-product-strategy.json`](../config/doe-product-strategy.json), [migration](product-strategy-contract.md) |
| Runtime and benchmarks | [`status/runtime-backends-and-bench.md`](status/runtime-backends-and-bench.md) | `reports/claim-index.json`, `bench/out/` |
| Independent framework integration | [`status/runtime-backends-and-bench.md#independent-onnx-integration`](status/runtime-backends-and-bench.md#independent-onnx-integration) | [ONNX Vulkan lifecycle qualification](../reports/benchmarks/amd-vulkan/20261008-onnx-vulkan-device-lifecycle/README.md), [completed application campaign](../reports/benchmarks/amd-vulkan/20261005-onnx-vulkan-campaign/README.md) |
| Execution ownership, calibration and shared-GPU interference, measurement resolution, and reusable programs | [`status/reusable-compute-programs.md`](status/reusable-compute-programs.md) | `config/doe-product-strategy.json`, `config/compute-program-decision.json`, `bench/out/compute-program/` |
| Implementation quality, runtime architecture, command contracts, and snapshot ownership | [`status/runtime-architecture-audit.md`](status/runtime-architecture-audit.md) | [bounded quality plan](../config/zig-review-plan.json), `runtime/zig/reviews/log.json`, coverage inventory in `runtime/zig/reviews/queue.tsv`, and `runtime/zig/source-layout.json` |
| Compiler and WebGPU | [`status/compiler-and-webgpu.md`](status/compiler-and-webgpu.md) | `zig build test-wgsl`, schema-registered evidence |
| TSIR | [`status/tsir.md`](status/tsir.md) | `reports/parity/`, manifest lowering entries |
| Cerebras and CSL | [`status/cerebras-csl.md`](status/cerebras-csl.md) | `bench/out/r3-cerebras-status/snapshot.{json,md}` |
| CSL runtime bring-up | [`status/cerebras-csl-runtime-bringup.md`](status/cerebras-csl-runtime-bringup.md) | Cerebras snapshot and model ledgers |
| Continuous integration | [`status/ci.md`](status/ci.md) | workflows and CI inventory tests |
| Chromium | [`browser-lane.md`](browser-lane.md) | browser milestone manifest and artifacts |
| Fawn preview and benchmark pages | [`status/fawn-start.md`](status/fawn-start.md) | [application evidence](../reports/maintenance/20261005-fawn-demo-switcher/README.md), `browser/chromium/resources/`, and user visual review |

Do not add dated progress entries here. Update the owning artifact or live
boundary, and preserve resolved narrative in an archive shard.
