# Doe CSL-plan evidence status

This document is the entry point for the evidence that backs Doe's
shared WGSL → CSL/Vulkan/Metal/D3D12 plan. Every section points at
artifact paths and the gate that validates them — no counts or error
thresholds are inlined, since those belong to the artifacts themselves
(per `CLAUDE.md`'s documentation discipline). The landing page for a
/loop iteration is the unified sweep.

## One-command regression check

Run `python3 bench/tools/run_csl_plan_sweep.py`. The summary lands at
`bench/out/csl-plan-sweep.json` with `{total, passed, failed,
allPassed}`. Exit code 0 iff every gate below is green. The sweep
regenerates a handful of derived artifacts before gating, so a clean
checkout + a clean sweep is idempotent:

1. `bench/out/csl-kernel-fingerprints.json` — ELF hashes (section 5b).
2. `bench/out/e2b-vs-31b-dry-run-diff.json` — cross-model sanity diff.
3. `bench/out/lookahead-sensitivity/{e2b,31b}-lookahead-sensitivity.json` — A/B sensitivity.
4. schema_gate over every registered artifact.
5. fixture / matrix / model-receipt / chain-parity / cmaddr checks.

## Evidence ladder

### 1. Cross-backend kernel matrix

Every WGSL kernel in the tracked registry has a Vulkan SPIR-V, Metal
MSL, D3D12 HLSL+DXIL, and (when the Cerebras SDK is available) a CSL
runtime artifact.

- Registry: `config/csl-runtime-fixtures.json` (schema
  `config/csl-runtime-fixtures.schema.json`).
- Cross-backend report: `bench/out/cross-backend-matrix/wgsl-backend-matrix.{json,md}`.
- Gate: `bench/gates/wgsl_backend_matrix_gate.py` with
  `--require-vulkan-ready --require-metal-ready --require-d3d12-ready
  --sdk-optional --min-csl-runtime-ready N`. SDK-optional mode enforces
  the CSL-ready threshold only when `DOE_CSL_SDK_ROOT` /
  `DOE_CSLC_EXECUTABLE` / `cslc` is detected locally, so CI jobs on
  hosts without the SDK still catch Vulkan/Metal/D3D12 regressions.

### 2. Per-kernel CSL runtime parity

Each runtime-ready fixture compiles and runs against the SDK 1.4
simulator and verifies bit-exact or bit-close output vs numpy.

- Governed-lane receipts: `bench/out/dual-compile-evidence/governed-lane-sdk-handoff/sim-success-*/`.
- Each fixture declares its `reduceStrategy` in the registry (enum:
  `none`, fabric-reduce variants, and host-reduced partial variants)
  plus optional `reduceStrategyNote` so the orchestration tradeoff is
  explicit.
- Gate: `bench/gates/csl_runtime_fixture_gate.py --require-ready-receipts`.

### 3. Full-grid cslc compile

Proven via direct cslc invocation on the smallest kernel across the
full PE counts that E2B and 31B need.

- Probe tools: `bench/tools/probe_cslc_grid_limits.py` (1D),
  `bench/tools/probe_cslc_2d_grid.py` (2D).
- Aggregate: `bench/out/cslc-grid-probe/grid-probe-aggregate.json`.
- Per-grid compile artifacts: `bench/out/cslc-grid-probe/compile-outputs/*/bin/`
  and `bench/out/cslc-grid-probe/2d-compile-outputs/*/bin/`.
- Finding: 1D flatten overflows the SDK's memcpy-module i16 width at
  31B peCount; 2D layouts keep each axis under the ceiling. E2B
  (149×117) and 31B (246×236) both compile cleanly under the 2D
  emitter.

### 4. Model-level runtime receipt

Binds manifest, host-plan, memory-plan, runtime-config, simulator-plan,
per-kernel fixture resolution, streaming-migration derivation, stream
graph, and chain-parity evidence into one artifact per model.

- Lane drivers: `bench/runners/run_e2b_full_graph_lane.py`,
  `bench/runners/run_31b_full_graph_lane.py`.
- Receipt builder: `bench/tools/build_model_runtime_receipt.py`
  (schema: `config/doe-model-runtime-receipt.schema.json`).
- Receipts: `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.{json,md}`,
  `bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.{json,md}`.
- Gate: `bench/gates/model_runtime_receipt_gate.py --require-fits
  --require-structural-full-coverage --min-kernel-coverage-pct 100
  --min-chain-parity-patterns N`. Separate `--require-execution` flag
  gates on `executionStatus in {simulator_success, hardware_success}`
  for future hardware receipts.

The `laneStatus` field reports structural coverage
(`structural_full_coverage` means every host-plan kernel resolves to a
runtime-ready fixture and the memory plan fits). The `executionStatus`
field stays honest at `not_attempted`; the current `executionBlocker`
is `streaming_executor_not_bound_to_execution_plan`. The SdkLayout
streaming executor primitives now compile and run under simfabric
(section 8 below lists the traces) — the remaining gap is generated
stage-kernel code that the executor dispatches per layer, per the
Gemma4 Doppler→Doe→Cerebras plan's Build-order step 1
(`ouroboros/docs/integration/gemma4-doppler-doe-cerebras-plan.md`).
Each model receipt now carries a `streamingExecutorPrimitivesEvidence`
block pointing at the primitive traces, so downstream consumers can
render "primitives: pass" as a distinct row from "full-model: blocked".

### 5. Stream graph + execution plan + dry-run trace + comparison tools

Derived orchestration artifacts for the streaming runtime, plus a pure-
Python dry-run that consumes the plan and emits a predicted trace, a
diff tool for predicted-vs-predicted or predicted-vs-hardware, and a
sensitivity sweep that varies prefetch lookahead and reports how
ring-buffer occupancy tracks.

- Emitters: `bench/tools/build_stream_graph.py`,
  `bench/tools/validate_stream_graph.py`,
  `bench/tools/dry_run_streaming_executor.py`,
  `bench/tools/diff_dry_run_traces.py`,
  `bench/tools/sweep_lookahead_sensitivity.py`.
- Schemas: `config/doe-stream-graph.schema.json`,
  `config/doe-stream-execution-plan.schema.json`,
  `config/doe-streaming-executor-dry-run-trace.schema.json`,
  `config/doe-dry-run-trace-diff.schema.json`,
  `config/doe-lookahead-sensitivity.schema.json`.
- Per-model output:
  `bench/out/{e2b,31b}-full-graph/gemma-4-{e2b,31b}-stream-graph.json`,
  `bench/out/{e2b,31b}-full-graph/gemma-4-{e2b,31b}-stream-execution-plan.json`,
  `bench/out/{e2b,31b}-full-graph/gemma-4-{e2b,31b}-dry-run-trace.json`.
- Cross-model diff: `bench/out/e2b-vs-31b-dry-run-diff.json`.
- Per-model sensitivity:
  `bench/out/lookahead-sensitivity/{e2b,31b}-lookahead-sensitivity.json`.
- `executorStatus` starts at `plan_only` until the streaming runtime
  implementation lands. At that point the field flips to
  `executor_ready` and eventually `executed`. The dry-run trace's
  `assumedBandwidthBytesPerCycle` is explicit so future hardware traces
  can swap the constant and be diff'd against the predicted shape.
- Stream-graph validation (`routingReachable`, `portBindingComplete`,
  `acyclic`) is a real computed check — fails the validator with a
  clear message when any flag is false.

### 5b. ELF fingerprint artifact

- Tool: `bench/tools/fingerprint_kernel_compiles.py`.
- Schema: `config/doe-csl-kernel-fingerprints.schema.json`.
- Output: `bench/out/csl-kernel-fingerprints.json` — per-ELF sha256 for
  runtime-ready fixture compiles + `aggregateSha256` summary for each
  cslc grid-probe bin directory. Catches emitter / cslc drift that
  passes schema + gate checks but still produces different compiled
  bytes.

### 6. Kernel-chain parity

Each chain-parity receipt proves that N distinct Doe-emitted kernels
compose end-to-end with bit-exact or bit-close numerical parity against
numpy. The model receipt's `chainParityEvidence` block unions the
passing chain patterns into `kernelPatternsChainProven`, the set of
host-plan patterns for which we have real composition evidence (not
just per-kernel parity).

- Schema: `config/doe-kernel-chain-parity.schema.json`.
- Orchestrator: `bench/tools/run_kernel_chain.py` (subprocess-boundary
  driver with per-tensor `chunkSize` + `postStepTransform` kinds
  `sum_across_pe` / `broadcast_to_pe` / `sum_and_broadcast` /
  `finalReduce: sum_across_pe`).
- Step adapter: `bench/runners/csl-runners/chain_step_adapter.py`.
- Chain receipts: `bench/out/kernel-chain-evidence/*/chain-parity.json`.
- Gate: `bench/gates/kernel_chain_parity_gate.py` with
  `--require-bit-close` or `--require-bit-exact`.

SDK constraint surfaced and worked around: two `SdkRuntime` instances
in one Python process trigger `simfab_api.cc:111`. Subprocess
boundaries reset SDK global state and let different kernels chain
cleanly.

### 7. Hardware endpoint propagation

The driver's substitution layer is unit-tested for the simfabric ↔
system flip and the receipt-redaction pass that replaces a raw endpoint
with `$DOE_CSL_CMADDR` in persisted commands.

- Verifier: `bench/tools/verify_cmaddr_propagation.py`.
- Smoke receipt: `bench/out/cmaddr-propagation-smoke.json`.
- No live endpoint required; the pure driver functions are verified via
  direct import.

### 8. SdkLayout streaming executor primitives

Bench/out/streaming-executor/ holds SdkLayout compile+run traces for
every primitive the executor needs to compose a layer block. Each
trace is schema-validated by `config/doe-streaming-executor-trace.schema.json`.

- Schema: `config/doe-streaming-executor-trace.schema.json`.
- Primitives proven (each with its own trace): stream passthrough
  (iter-2), compute transform (iter-3), region-to-region chain
  (iter-4), multi-PE SPMD via demux/mux (iter-5), compile-artifact
  cache + io_buffer_size knob (iter-6), four-stage layer-block-shaped
  chain (iter-7), plus hand-ported WGSL-semantics kernels for
  elementwise-sigmoid, elementwise-add, gather, and blocked
  reduce-sum.
- First generated layer-block smoke (plan Build-order step 1):
  `bench/out/streaming-executor/e2b-layer-block-smoke-trace.json`,
  produced by `bench/tools/generate_e2b_layer_block_runner.py` from
  `bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json`.
  The trace carries `layerBlockSmoke.{planSha256, kernelSourceSha256,
  targetMode, connectionGraph, hostIoLayout, ioBufferSizes,
  sendReceiveCounts, simulatorArtifactPaths, sourceModelReceiptPath}`.
- WGSL backend equivalence crosswalk: `bench/out/wgsl-backend-equivalence/`
  ties one WGSL source to every backend emitter (csl-memcpy,
  csl-sdklayout, spirv) with sha256-bound pointers to each backend's
  execution evidence (schema: `config/doe-wgsl-backend-equivalence.schema.json`).
- Vulkan runtime probe: `bench/out/vulkan-runtime-probe/` records
  per-step infrastructure status for Doe's native WebGPU stack
  (`libwebgpu_doe.so`). Currently surfaces
  `knownGap=compute_dispatch_drops_storage_writes` — infrastructure
  boots and buffers round-trip, but storage writes from compute
  dispatch don't reach the GPU (schema:
  `config/doe-vulkan-runtime-probe.schema.json`).

## What the sweep does not (yet) prove

- **Actual model execution on hardware.** Both models report
  `executionStatus: not_attempted`. The `executionBlocker` today is
  `streaming_executor_not_bound_to_execution_plan`: the SdkLayout
  streaming executor primitives exist and run on simfabric (section 8
  below), but the stream-execution-plan's stage codegen is not yet
  emitting kernels the executor dispatches per layer. Maps to
  Build-order step 1 of the cross-repo plan at
  `ouroboros/docs/integration/gemma4-doppler-doe-cerebras-plan.md`.
- **Longer Gemma chains.** Current chains are 2 or 3 kernels. The
  shape-plumbing for deeper chains (attention+MLP block) is tractable;
  we just have not added those receipts yet.
- **Full-grid per-kernel compile.** The 2D probe proves the PE-count
  ceiling for the simplest kernel. Compiling all 17 emitted kernels at
  E2B/31B grid with their real shape params is a separate sweep
  (Build-order step 2). Precondition: 2D emission must land across all
  14 layout emitters in `runtime/zig/src/doe_wgsl/emit_csl_layout.zig`
  — elementwise is done, 13 remain.
- **Weight-quantized numerical parity at the model level.** Per-kernel
  Q4K parity is covered by `fused_gemv_dequant`; whole-model logit
  parity requires the streaming executor plus a reference weights
  artifact.

## Pointers for a future hardware run

1. Set `DOE_CSL_SDK_ROOT=/path/to/sdk` and `DOE_CSL_CMADDR=IP:PORT`.
2. Re-run any governed-lane driver that supports the `{cmaddr_arg}`
   substitution — the driver-result will flip
   `executionTarget: system` and the runtime command will embed
   `--cmaddr=$DOE_CSL_CMADDR` (redacted in the receipt).
3. The model-level receipt's `executionStatus` should be updated to
   `hardware_success` with a pointer to the hardware trace once
   available.
