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
  `none` / `on_device_fabric` / `host_partial`) so the orchestration
  tradeoff is explicit.
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
field stays honest at `not_attempted` until the SdkLayout streaming
executor lands; the current `executionBlocker` is
`sdk_layout_streaming_executor_missing`.

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

## What the sweep does not (yet) prove

- **Actual model execution on hardware.** Both models report
  `executionStatus: not_attempted`. The `executionBlocker` names the
  first unmet prerequisite; today it is the SdkLayout streaming
  executor (priority #6) for both models.
- **Longer Gemma chains.** Current chains are 2 or 3 kernels. The
  shape-plumbing for deeper chains (attention+MLP block) is tractable;
  we just have not added those receipts yet.
- **Full-grid per-kernel compile.** The 2D probe proves the PE-count
  ceiling for the simplest kernel. Compiling all 17 emitted kernels at
  E2B/31B grid with their real shape params is a separate sweep.
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
