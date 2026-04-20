# Gemma 4 + Doe + Cerebras hardware validation appendix

One-page companion to the hardware-access request. Every claim below
is keyed to an on-disk artifact; no marketing language, no performance
claims. Scope: E2B layer-block first; 31B layer-block is also present
as the scale-target scaffold.

## Attached bundle

Current archive filename, sha256s, size, and git commit are
auto-refreshed by
`bench/tools/prepare_cerebras_validation_bundle.sh` into:

- `docs/cerebras-evidence-bundle-pointer.md`

That file is regenerated on each successful pack, so the appendix
stays stable while the pointer tracks the latest build. Read it for
the exact values you'd cite in an email body. If the pointer doesn't
exist yet on a fresh clone, run
`bench/tools/prepare_cerebras_validation_bundle.sh` to generate it.

To verify the bytes you received:

```bash
python3 bench/tools/verify_cerebras_validation_archive.py \
    --archive <path-to-received-archive>
```

Or a one-command summary without unpacking:

```bash
bench/tools/summarize_cerebras_evidence_archive.sh <path-to-received-archive>
```

The archive's own `BUNDLE_META.json` is always the authoritative
source of truth for any bundle in hand.

## Target order

The first hardware validation target is Gemma 4 E2B because it is the current
correctness lane with a simulator-backed layer-block receipt. The next scale
target is Gemma 4 31B dense, not Gemma 4 26B/A4B MoE. Dense 31B keeps the
execution shape uniform while Doe validates streamed weights, SdkLayout ports,
host I/O ordering, full-grid compile behavior, and parity receipts on WSE.

Gemma 4 26B/A4B MoE remains a later efficiency lane. It needs separate
Gemma-specific receipts for router logits, top-k expert selection,
token-to-expert dispatch, shared expert execution, expert output combine, and
per-expert batching. It should not borrow the E2B or dense-31B receipts, and it
is not part of the first hardware-access ask.

## 1. Current artifact paths and hashes

E2B bundle:

- execution manifest `runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json`
  sha256 `67e13946350e69ee62c75f06e80b94d44e15a18ba5858a8e9011636cfa6c9c26`
- host plan `bench/out/e2b-full-graph/host-plan.json`
  sha256 `0a5c357199f1b67a27682a8df9cab12812c3373fccda183c4930693553fdae91`
- memory plan `bench/out/e2b-full-graph/memory-plan.json`
  sha256 `dcac44caf9bff14a5124e1be9605a257212e2c92ffd9a68c1628ea789aa45b20`
- runtime config `bench/out/e2b-full-graph/runtime-config.json`
  sha256 `18a59263bc575e7249c2052a07ef5bb926ab104d2dfb884bd4f4165e0f35dbf6`
- simulator plan `bench/out/e2b-full-graph/simulator-plan.json`
  sha256 `384c78dd2269d3b3b4597a7bcdcb0e1d1224ead577de15b1dae95d158ee082dd`
- stream execution plan `bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json`
  sha256 `e8fa1420ddcac5700338b9a1b96071d3403c95618c5c6ea536f24e581a505729`
- layer-block CSL kernel `bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
  sha256 `023b391f136de9f5feb65d206b1144c3dfe760d49adfb7a771f409f0c7fb23a4`
- runtime receipt `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json`
  (`executionStatus=simulator_success`, `executionBlocker=none`)

31B bundle (scale-target scaffold, same shape as E2B):

- execution manifest `runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json`
  sha256 `753bce9331c65f84badb297658362bc158b2ada4e494d4da5a199716cba37f2e`
- host plan sha256 `d4f9501ea943aed141835bea8c10897c8fa59dc1d86ee606fd0e0895e4d8c4bd`
- memory plan sha256 `559f847aee4565be488f9db5224bd8d97455a070dccc1ef8b5b33c1450815f19`
- runtime config sha256 `797e628043cb64d647d6d92b07acf9f85d21ecd145be0ffa1262da985a46bc1e`
- simulator plan sha256 `903491aac2af6fedf80e6e72b104624fffbaf7b510a7f0ed6d8af11279eab4b8`
- runtime receipt `bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json`
  (`executionStatus=simulator_success`)

CSL runtime fixture registry (shared) sha256 `4428f5b22e716b3f04f1269dc426cc2ac5ec11c8b31b89ec655484f52a388fa2`.

## 2. What the simfabric proof demonstrates

`bench/out/streaming-executor/e2b-layer-block-smoke-trace.json`:
`status=succeeded`, `numLayersChained=35`, 4-stage transformer layer
block executed bit-exact per layer against the scalar-f32 numpy
reference (`maxAbsErr=0.0`). Kernel is not a stub
(`streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence.kernelIsStub=false`).

Cross-runtime parity verdict
`bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json`:
`promotionEligible=true`, 6 of 6 preconditions met —
`P1_runner_trace_exists`, `P2_runner_kernel_sha_matches_live`,
`P3_runner_ran_on_simulator_not_numpy`, `P4_runner_status_succeeded`,
`P5_per_layer_err_all_zero_bit_exact`,
`P6_output_digests_match_across_runtimes`.

Doppler-equivalent WGSL/WebGPU (Dawn on AMD Radeon 8060S) matches CSL
per-layer within `atol=1e-3`, all 35 E2B layers. Per-layer parity at
`bench/out/doppler-reference/webgpu-vs-numpy-per-layer-parity.json`.

Kernel surface: pre-attn RMSNorm, 8-head MHA with per-head vector
Q/K/V and multi-pair ROPE, post-attn RMSNorm, gated MLP with poly_c1
GELU. RMSNorm uses `math.sqrt` + a Newton-Raphson refinement step so
WSE vs WebGPU sqrt approximations agree bit-exactly at f32.

Scope caveats (explicit on the receipts themselves):
`promotionCriteria.syntheticInputsAbsent=false` and
`syntheticWeightsAbsent=false` — inputs and weights are seeded
deterministic tensors, not real Gemma 4 checkpoint slices. 31B runs
use the smoke shape (`num_heads=8, head_dim=8, kv_len=4, size=1024`),
not the manifest's production shape.

## 3. What hardware validation should run

Two paths either work; CEREBRAS_ASK.md inside the evidence bundle
has the operator-facing detail for both.

- **Path A — endpoint access.** Cerebras provides a reachable CS/WSC
  endpoint; we run the commands below from our side.
- **Path B — Cerebras-assisted bundle run.** A Cerebras engineer runs
  the bundle internally on their cluster and returns the receipt.
  No code from our side needs to run on Cerebras infrastructure —
  the runner is self-contained under `bench/runners/`.

Minimum sufficient ask (same command either way):

1. E2B layer-block smoke at `num_layers=35` against a reachable CS
   endpoint via `--cmaddr`, or appliance via
   `runtime/zig/tools/csl_appliance_driver.py`. The runner is
   `bench/runners/csl-runners/e2b_layer_block_smoke.py` and accepts
   `--cmaddr <addr>` today.
2. Output parity check: compare `activation_out.f32` against the
   simfabric trace's recorded output at the matching chain depth.
   Tolerance: `atol=1e-3` per `docs/claim-discipline.md`.
3. Graph-identity pin: hardware receipt records the same
   `manifestSha256`, stream-plan `planSha256`, and
   `kernelSourceSha256` listed above.

Stretch, if time permits:

- E2B layer-block at `num_layers=35` with real weight slices once we
  have them materialized (validator `bench/tools/validate_weights_dir.py`
  guards the `--weights-dir` contract).
- 31B dense layer-block smoke at the same chain depth as E2B, to exercise
  streaming scale. This is a dense-model validation target, not a MoE
  efficiency claim.

## 4. What receipt fields we want back

Emitted as `doe_target_run_receipt` (existing schema) with
`target=hardware`, plus the hardware-specific fields below:

- `hardware.endpoint` — redacted (host/appliance tag, not raw IP)
- `hardware.jobId` — provider-assigned, redacted if policy requires
- `hardware.sdkVersion` — Cerebras SDK release running on the endpoint
- `hardware.fabricId` and `hardware.deviceArch` — for trace pinning
- `executedCompile.elapsedMs` and `executedRun.elapsedMs` — wall time,
  only if Cerebras policy permits disclosure
- `executedRun.status` — `succeeded` / `failed:<taxonomy>`
- `executedRun.output.sha256` — matches or explicitly diverges from the
  simfabric trace's recorded `activation_out.f32` digest
- `executedRun.numericalParity` — `maxAbsErr` and `perLayerMaxAbsErr`
  against the simfabric reference
- `executedRun.perLayerOutputs[*]` — per-layer `.f32` digests so drift
  can be located if the chain-final digest diverges
- `cacheKeyComponents` — kernel, plan, target, size (already emitted by
  the runner as of the gap-1 seeding tick)
- Signed-off `claimScope` — explicit enumeration of what the receipt
  does and does not claim

## 5. What we will not publish without approval

Per `docs/claim-discipline.md`, without the endpoint provider's
explicit approval we will NOT publish:

- any hardware timing (`elapsedMs`) beyond what the endpoint operator
  authorizes
- endpoint identity, IP, physical location, rack or appliance IDs
- queue-depth, fabric-level, or operator-internal telemetry surfaced
  in SDK logs
- any performance claim beyond "matches simfabric reference within
  tolerance" — hardware speed claims are gated on endpoint approval and
  governed benchmark methodology
- comparisons against other hardware unless the methodology is jointly
  signed off

The current public claims (see `docs/claim-discipline.md`) are
deliberately scoped to **portability and parity**. The narrow local
exception — emulator vs local simfabric wall time on the same host —
is explicitly labeled "local debug path only, NOT a Cerebras hardware
performance claim" in
`bench/tools/compare_csl_emulator_vs_simfabric_speed.py`.

## Where to look first

- Claim ladder: `docs/claim-discipline.md`
- Receipts: `bench/out/e2b-full-graph/`, `bench/out/31b-full-graph/`
- Cross-runtime evidence: `bench/out/doppler-reference/`
- Self-check: `python3 bench/tools/e2b_layer_block_self_check.py`
- Status shard: `docs/status/2026-04.md`
