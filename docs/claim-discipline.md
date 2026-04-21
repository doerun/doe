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

This is a compiler/runtime artifact claim. It is not a full-model
execution claim.

### L1 synthetic E2B-shaped layer-block parity is evidenced

Evidence:

- `bench/out/doe-run/all-lanes-summary-L1.json` carries
  `evidenceEligibility.claimable=true`,
  `evidenceTier=synthetic_l1_layer_block`, and
  `runtimeParityTolerance.rollupVerdict=all_within_tolerance`.
- The runtime-output lanes are `webgpu-wgsl`, `csl-sdklayout`, and
  `csl-webgpu-emulator`; Metal/Vulkan rows are backend-identity
  probes, not model-output parity lanes.
- The fixture behind the tolerance is
  `config/gemma-4-e2b-real-weight-fixture.json`, but the current
  run still uses synthetic seeded tensors.

Allowed wording:

- "One synthetic Gemma-4 E2B-shaped layer block runs through browser
  WebGPU, CSL simfabric, and the CSL WebGPU emulator within
  `atol=1e-3`."
- "This proves the local compiler/runtime shape for one layer-block
  contract, not real weights, not full E2B, and not hardware."

### L1 real-weight E2B smoke-contract parity is evidenced

Evidence:

- `bench/tools/extract_gemma4_e2b_weight_slices.py` materializes the
  current smoke-contract `.f32` slices from the BF16 SafeTensors source
  discoverable through Doppler's local int4ple origin metadata.
- `bench/out/weights-audit/gemma-4-e2b-weights-audit.json` passes and
  matches the fixture-pinned `weightSetSha256` in
  `config/gemma-4-e2b-real-weight-fixture.json`.
- `bench/out/gemma-4-e2b-real-weight-parity-L1.json` reports
  `verdict=parity_passed` for Doppler-equivalent WebGPU vs CSL
  simfabric at L1. The output digests differ, but the per-layer
  tolerance check passes under the fixture formula
  `abs(a-b) <= atol + rtol * max(abs(a), abs(b))`.
- `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` reports
  `executionStatus=real_weight_layer_block_success` and carries the
  real-weight parity summary.
- The same model receipt carries `sdkLayoutModelExecutionEvidence`, which
  promotes the generated E2B SdkLayout layer-block smoke into the model-level
  receipt path with source hashes, stream execution plan hash, region/port/
  stream graph, host I/O layout, send/receive counts, simulator artifact
  links, `kernelIsStub=false`, `rt.stop()` completion, and parity status.

Allowed wording:

- "The E2B L1 layer-block smoke contract now runs with BF16-derived
  Gemma-4 weight slices in WebGPU and CSL simfabric, with output within
  the declared tolerance policy."
- "The generated E2B SdkLayout layer-block smoke is now promoted into the
  E2B model runtime receipt for the L1 smoke contract."
- "This is real checkpoint-derived weight evidence for the L1 smoke
  layer-block contract. It is not manifest-shape execution, not full
  E2B inference, not 31B, not MoE, and not hardware."

### Doppler RDRR/int4ple artifact structure is readable by Doe

Evidence:

- `config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json` pins the
  local Doppler int4ple RDRR artifact root, manifest/origin hashes,
  declared shard table, target shard index, Q4_K_M block constants, and
  Gemma-4 layer-0 tensor list.
- `bench/tools/probe_doppler_rdrr_artifact.py` validates the manifest,
  declared shard sizes, selected shard hash, Gemma-4 int4 per-layer
  embedding transform metadata, and target tensor byte spans.
- `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json` reports
  the structural verdict and explicitly keeps `dequantStatus.q4k` at
  `blocked_not_implemented`.

Allowed wording:

- "Doe can structurally read the local Doppler Gemma-4 E2B int4ple RDRR
  artifact: manifest, declared shards, selected target shard hash,
  target tensor spans, Q4_K_M packed-size formulas, and int4 PLE metadata."
- "This is a production-artifact readability proof. The structural probe
  itself is not the Q4_K_M parity verdict, not Doppler production
  inference output parity, and not full E2B execution from the RDRR
  artifact."

### Doppler RDRR Q4_K_M L1 smoke-contract parity is evidenced

Evidence:

- `bench/tools/extract_gemma4_e2b_rdrr_weight_slices.py` reads Q4_K_M
  tensor spans from the local Doppler RDRR artifact and materializes
  Doe's existing Gemma-4 E2B smoke-contract `.f32` slice files under
  `bench/out/gemma-4-e2b-rdrr-int4ple-weights/`.
- `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-extraction.json`
  records the RDRR-derived slice materialization, the RDRR weight-set
  hash, and diagnostic drift against the BF16-derived smoke slices.
- `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json`
  reports the wrapper verdict, and
  `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-l1-parity.json`
  records the WebGPU-vs-CSL simfabric parity harness verdict using the
  RDRR-derived weights with `weightSetPinMode=record-only`.

Allowed wording:

- "Doe can dequantize the local Doppler Gemma-4 E2B int4ple RDRR
  Q4_K_M spans into the L1 smoke-contract slice format and run the
  WebGPU-vs-CSL simfabric parity harness within the declared tolerance."
- "This proves RDRR-derived L1 smoke-contract parity only. It is not
  Doppler production inference output parity, not manifest-shape
  execution, not full E2B, not 31B, not MoE, and not hardware."

### Declared real-weight smoke diagnostics are local, not promoted

Evidence:

- `bench/out/gemma-4-e2b-real-weight-parity-L{2,4,8,35}.json`
  records BF16-derived WebGPU-vs-CSL simfabric diagnostic verdicts for
  the declared smoke-chain depths. See the artifacts for current
  tolerance metrics.
- `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity-L{2,4,8,35}.json`
  records the parallel RDRR Q4_K_M diagnostic wrapper verdicts. See the
  artifacts for current tolerance metrics.
- C38 in `bench/tools/e2b_layer_block_self_check.py` treats these as
  optional diagnostics and rejects any state that promotes them to
  full-model or hardware evidence.
- `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json` now
  carries `sdkLayoutDepthDiagnosticEvidence` for the BF16-derived and
  RDRR-derived L35 smoke-chain diagnostics. The block is explicitly
  `claimable=false` and records the remaining manifest-shape runtime,
  Doppler production parity, and hardware blockers.
- C43 in `bench/tools/e2b_layer_block_self_check.py` requires the model
  receipt to keep the full-depth smoke diagnostics non-claimable while
  still hash-linking their parity and trace artifacts.

Allowed wording:

- "Doe has local E2B smoke-chain diagnostics across declared depths for
  both BF16-derived and RDRR-derived weight slices."
- "The E2B model receipt now exposes the BF16 and RDRR L35 smoke-chain
  diagnostics as non-claimable SdkLayout depth evidence."
- "These diagnostics extend the depth of the smoke contract only. They
  are not manifest-shape execution, not full E2B inference, not
  promoted release evidence, not 31B, not MoE, and not hardware."

### E2B manifest-shape tensor contract is recorded

Evidence:

- `bench/tools/probe_gemma4_e2b_manifest_shape.py` reads the local raw
  Gemma-4 E2B SafeTensors header and upstream text config without
  loading tensor bytes.
- `bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json`
  records the upstream tensor contract: local `headDim=256`,
  `globalHeadDim=512`, `numKeyValueHeads=1`, `numHeads=8`, and
  layer-0 q/k/v/o/projection tensor shapes.
- C39 in `bench/tools/e2b_layer_block_self_check.py` requires Doe's
  execution manifest fields to match the upstream tensor metadata.

Allowed wording:

- "Doe has a schema-backed E2B manifest-shape tensor-contract artifact
  that binds local `headDim=256`, `globalHeadDim=512`, and
  `numKeyValueHeads=1` to the source checkpoint metadata."
- "This is not manifest-shape execution; it is the config/tensor
  contract needed before that execution path can be implemented."

### E2B manifest-shape CPU execution oracle is recorded

Evidence:

- `bench/tools/run_gemma4_e2b_manifest_shape_execution.py` reads the
  local raw Gemma-4 E2B BF16 SafeTensors checkpoint and executes a
  text-only CPU/Numpy oracle.
- `bench/out/manifest-shape/gemma-4-e2b-manifest-shape-execution.json`
  records the manifest-shape text-forward result, including embed, PLE,
  all text decoder layers, final norm, tied lm-head top-k, finite-output
  checks, and explicit blockers for Doe/CSL runtime and hardware.
- C40 in `bench/tools/e2b_layer_block_self_check.py` requires this
  artifact to stay scoped as `runtimeLane=cpu_numpy_oracle` with
  `doeRuntimeExecuted=false`, `cslRuntimeExecuted=false`, and
  `hardwareExecuted=false`.

Allowed wording:

- "The raw BF16 Gemma-4 E2B text checkpoint has a schema-backed
  CPU/Numpy manifest-shape execution oracle."
- "This is a full text-forward oracle at upstream tensor dimensions,
  not a Doe/CSL runtime receipt, not hardware evidence, and not a
  performance claim."

### The CSL kernel implements the transformer layer-block shape

Evidence:

- `streamingExecutorPrimitivesEvidence.layerBlockKernelEvidence.kernelIsStub=false`
  on both model receipts
- The live CSL at
  `bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
  implements pre-attn RMSNorm, 8-head MHA with per-head vector Q/K/V
  and multi-pair ROPE, residual, post-attn RMSNorm, and gated MLP with
  `poly_c1` GELU

This is still a layer-block kernel claim. It is not an end-to-end
Gemma-4 inference claim.

### The CSL WebGPU emulator is a local debug lane

Evidence:

- `bench/tools/compare_csl_emulator_vs_simfabric_speed.py` emits
  `doe_csl_emulator_speed_verdict` artifacts with matched
  `manifestSha256` and `graphSha256` on both sides
- `bench/out/doppler-reference/csl-emulator-speed-verdict-L1.json`
  records the local debug speed ratio for the evidenced L1 synthetic
  path.

This ratio measures local demo/debug ergonomics only. It is not
Cerebras hardware performance.

## Rejected claims

None of the following are allowed yet, and each is gated on a specific
unlock.

### "Doppler's production Gemma-4 pipeline matches Doe's CSL output"

Gate: Doppler-owned reference export (item #1 in the roadmap). The
Doppler-equivalent Dawn shader here is a SEPARATE harness that matches
the semantic contract but is not Doppler's browser inference path.

### "Doe executes the full real Gemma-4 E2B/31B model with real weights"

Gate: full graph and manifest-shape real-weight receipts. E2B L1
smoke-contract real-weight parity and the generated SdkLayout layer-block
promotion are now evidenced, but they are not a full-model Doe/CSL claim.
E2B now has a CPU/Numpy manifest-shape oracle, but the Doe runtime still
needs embed, manifest-shape decoder blocks, unembed, KV/cache bookkeeping,
and sampling. 31B still needs its own real-weight receipt.

### "Doe executes the full Gemma-4 model end-to-end"

Gate: full model execution (item #5). Current execution is the
Doe/CSL transformer layer-block smoke path plus a separate CPU/Numpy
manifest-shape oracle. A full Doe runtime receipt still needs embed,
manifest-shape decoder blocks, unembed, KV cache bookkeeping, and
sampling in the Doe execution path.

### "L35 is a claimable full E2B parity pass"

Gate: `bench/out/doe-run/all-lanes-summary-L35.json` must carry
`evidenceEligibility.claimable=true`, the depth-coverage matrix
must count L35 under `depthsClaimableWithinTolerance`, and the model
receipt's `sdkLayoutDepthDiagnosticEvidence` must no longer be scoped
as non-claimable smoke evidence. Today the claimable depth is L1
synthetic only. Any L35 files on disk, including the model-receipt
diagnostic block, are diagnostic until promoted by this policy.

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
| Full real-weight model execution | Extend from the evidenced E2B L1 smoke-contract receipt and CPU/Numpy manifest-shape oracle to Doe/CSL manifest-shape/full-depth receipts; 31B needs its own real-weight parity verdict |
| L2/L4/L8/L35 claimable depth | `summarize_doe_run_lanes.py` emits `evidenceEligibility.claimable=true` for that depth and `emit_depth_coverage_matrix.py` counts it under `depthsClaimableWithinTolerance` |
| Full E2B simulator | Extend the Doe runner to the full graph (embed + manifest-shape transformer blocks + unembed + sample); this is structural work in Doe |
| Manifest-shape 31B | Extend the generator/kernel to `head_dim=160, num_heads=32`; validate memory budget + streaming |
| Hardware receipt | `e2b_layer_block_smoke.py --cmaddr <addr>` against a reachable CS endpoint, or appliance via `csl_appliance_driver.py` |
| Performance claim | Hardware receipt + governed benchmark at fixed workload |

## Where to look first

- Current receipts: `bench/out/e2b-full-graph/`, `bench/out/31b-full-graph/`
- Cross-runtime evidence: `bench/out/doppler-reference/`
- Self-check: `python3 bench/tools/e2b_layer_block_self_check.py`
- Status shard: `docs/status/2026-04.md`
- Broader numeric-stability ladder: `docs/numeric-stability-claim-ladder.md`
