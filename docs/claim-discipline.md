# Doe + Gemma-4 + Cerebras claim discipline

This document codifies what the repository can honestly claim today for
the Doppler→Doe→Cerebras Gemma-4 lane, keyed to artifacts, and names
the gates that unlock each stronger claim.

It is narrower than `docs/numeric-stability-claim-ladder.md`. That doc
covers Doe's numeric-fragility story. This doc covers the E2B/31B
Cerebras-execution story: what the simulator and WebGPU evidence
supports, and what still needs external input.

If you catch marketing or a PR description claiming something not
listed in "allowed claims today," revise it.

## Allowed claims today

Each claim below is backed by a specific on-disk artifact or gate.

### Doe lowers Doppler execution-v1 to executable Cerebras CSL

Evidence:

- execution-v1 manifests at `runtime/zig/examples/execution-v1/*.json`
- E2B + 31B host-plan, memory-plan, runtime-config, stream-graph at
  `bench/out/e2b-full-graph/`, `bench/out/31b-full-graph/`
- 17-kernel CSL compile coverage recorded in each model-runtime receipt

### E2B layer-block simulator execution succeeds bit-exact against the scalar-f32 numpy reference

Evidence:

- `bench/out/streaming-executor/e2b-layer-block-smoke-trace.json` —
  cs_python simfabric run, 35 layers chained, `maxAbsErr=0.0` per layer
- `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` with
  `executionStatus=simulator_success, executionBlocker=none`
- Cross-runtime parity gate verdict at
  `bench/out/streaming-executor/e2b-layer-block-cross-runtime-parity-check.json`
  reports `promotionEligible=true, met=6/6`
- Regression-locked by C4/C7/C11/C12 in
  `bench/tools/e2b_layer_block_self_check.py`

### 31B layer-block simulator execution succeeds bit-exact at full manifest depth (61 layers)

Evidence:

- `bench/out/scratch/31b-l61-probe-trace.json` and the regenerated
  `bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json` with
  `executionStatus=simulator_success`
- 31B-specific cross-runtime parity at
  `bench/out/streaming-executor/gemma-4-31b-layer-block-cross-runtime-parity-check.json`
- Regression-locked by C9/C10/C13 in the self-check

### Doe-emitted CSL and a Doppler-equivalent WGSL/WebGPU implementation match within per-layer tolerance on the E2B layer-block contract

Evidence:

- Real WebGPU (Dawn on AMD) execution at
  `bench/tools/doppler_webgpu_reference_export.cjs`
- Per-layer parity at
  `bench/out/doppler-reference/webgpu-vs-numpy-per-layer-parity.json`
  reports `verdict.crossRuntimeParityPassed=true`, all 35 E2B layers
  within `atol=1e-3`
- L=1 gate-validated receipt at
  `examples/doe-csl-reference-parity.gemma-4-e2b-layer-block-L1-webgpu.sample.json`
  passes `csl_reference_parity_gate.py --require-tolerance-parity`

The phrase is deliberately **"Doppler-equivalent"**. Same WGSL semantic
contract via the same `webgpu` npm package Doppler uses, but a separate
standalone compute shader — not Doppler's production inference pipeline.

### The CSL kernel is the real transformer layer block, not a stub

Evidence:

- `streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence.kernelIsStub=false`
  on both model receipts
- The live CSL at
  `bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
  implements pre-attn RMSNorm, 8-head MHA with per-head vector Q/K/V
  and multi-pair ROPE, residual, post-attn RMSNorm, and gated MLP with
  `poly_c1` GELU

### The CSL WebGPU emulator is faster than local CSL simfabric on the same host at matched program identity and chain depth

Evidence:

- `bench/tools/compare_csl_emulator_vs_simfabric_speed.py` emits
  `doe_csl_emulator_speed_verdict` artifacts with matched
  `manifestSha256` and `graphSha256` on both sides
- `bench/out/doppler-reference/csl-emulator-speed-verdict-L35.json` and
  `...-L1.json` record ratios with `verdict=claimable_local_debug_speedup`
- Both sides are local correctness/debug runtimes — this ratio measures
  debug-path ergonomics, not hardware performance. Adjacent claims (faster
  than Cerebras hardware, faster than simfabric on other hosts) remain
  rejected

## Rejected claims

None of the following are allowed yet, and each is gated on a specific
unlock.

### "Doppler's production Gemma-4 pipeline matches Doe's CSL output"

Gate: Doppler-owned reference export (item #1 in the roadmap). The
Doppler-equivalent Dawn shader here is a SEPARATE harness that matches
the semantic contract but is not Doppler's browser inference path.

### "Doe executes the real Gemma-4 E2B/31B model with real weights"

Gate: real-weight extractor (item #3). Current inputs are seeded-RNG
fixtures. The model receipts honestly report
`promotionCriteria.syntheticInputsAbsent=false` and
`syntheticWeightsAbsent=false`.

### "Doe executes the full Gemma-4 model end-to-end"

Gate: full model execution (item #5). Current execution is the
transformer layer-block alone. Embeddings, unembedding, KV cache
bookkeeping, and sampling are not in the executed path.

### "The 31B kernel runs at the manifest's production shape"

Gate: manifest-shape 31B execution (item #6). Current 31B runs use
the smoke shape (`num_heads=8, head_dim=8, kv_len=4, size=1024`), same
as E2B. Manifest is `num_heads=32, head_dim=160`; production streaming
and memory budgets are unverified.

### "Doe runs Gemma 4 on real Cerebras hardware"

Gate: hardware receipt (item #8). Runner supports `--cmaddr` and
`runtime/zig/tools/csl_appliance_driver.py` exists, but no
`hardware_success` receipt has been produced.

### Any hardware performance or efficiency claim

Gate: hardware receipt + governed benchmark methodology. Simfabric
timing is not hardware performance. Until a hardware receipt lands,
claim **portability and parity** for hardware, not performance. The
narrow exception is the local emulator-vs-simfabric debug-path
comparison above, which is explicitly scoped to "local debug ergonomics"
by `compare_csl_emulator_vs_simfabric_speed.py`.

### "Gemma 4 26B / A4B MoE runs on Cerebras" (or on CSL, simfabric, WSE)

Gate: MoE-specific receipts. The existing E2B + 31B-dense receipts do
NOT unlock 26B MoE claims — MoE has distinct machinery (router
logits, top-k expert selection, token-to-expert dispatch, shared
expert execution, expert output combine, per-expert batching) and
needs its own evidence set. Until `doe_moe_*_receipt` artifacts exist
under `bench/out/` OR a Gemma-4-26B/A4B model-runtime receipt
promotes past `not_attempted`, `bench/gates/claim_discipline_gate.py`
rejects any text asserting the MoE is running/working/operational on
a Cerebras or Doe lane. The 31B-dense-first target order documented
in `docs/hardware-validation-appendix.md` is the binding policy:
26B/A4B MoE is explicitly the efficiency-story follow-up, not the
first-validation target.

## Promotion rules

Each rejected claim has a single-command unlock path in the repo.

| Rejected claim | Unlock command or external dep |
| --- | --- |
| Production Doppler pipeline parity | Doppler commits their WGSL shader into their pipeline and emits `activation_out.f32` matching the CSL runner's seeded-RNG inputs |
| Real-weight execution | `validate_weights_dir.py` passes on a Doppler-extracted weights-dir, then `e2b_layer_block_smoke.py --weights-dir <dir>` re-runs |
| Full E2B simulator | Extend runner to the full graph (embed + 35 transformer blocks + unembed + sample); this is structural work in Doe |
| Manifest-shape 31B | Extend the generator/kernel to `head_dim=160, num_heads=32`; validate memory budget + streaming |
| Hardware receipt | `e2b_layer_block_smoke.py --cmaddr <addr>` against a reachable CS endpoint, or appliance via `csl_appliance_driver.py` |
| Performance claim | Hardware receipt + governed benchmark at fixed workload |

## Where to look first

- Current receipts: `bench/out/e2b-full-graph/`, `bench/out/31b-full-graph/`
- Cross-runtime evidence: `bench/out/doppler-reference/`
- Self-check: `python3 bench/tools/e2b_layer_block_self_check.py`
- Status shard: `docs/status/2026-04.md`
- Broader numeric-stability ladder: `docs/numeric-stability-claim-ladder.md`
