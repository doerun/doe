# Gemma 4 + Doe + Cerebras hardware validation appendix

One-page companion to the hardware-access request. Every claim below
is keyed to an on-disk artifact; no marketing language, no performance
claims. Scope: Gemma 4 31B dense first for hardware validation; E2B remains
the smaller control fixture and regression lane.

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

The first hardware validation target is Gemma 4 31B dense. It is the
highest-value inference target, it has a uniform dense transformer execution
shape, and it maps better to a first Cerebras proof than Gemma 4 26B/A4B MoE.
The 31B lane should start with the af16 full-prompt HostPlan runner. Qwen
3.6 27B now has the matching af16 HostPlan wrapper for a companion hybrid
architecture run. The smoke-shape layer-block path remains a bounded fallback
for endpoint and receipt-shape checks.

The concrete 31B steps are:

1. Verify the evidence archive from a Doe checkout at the archive commit.
2. Materialize or mount the Doppler Gemma 4 31B af16 artifact:
   `gemma-4-31b-it-text-q4k-ehf16-af16`, backed by the shared Q4K weight pack
   `gemma-4-31b-it-text-q4k-ehf16-af32`.
3. Build the generated HostPlan/CSL bundle from
   `runtime/zig/examples/execution-v1/gemma-4-31b-af16-smoke.json` and compile
   the targets with the SDK driver.
4. Run `bench/runners/csl-runners/gemma4_31b_af16_hostplan_streaming_runner.py`
   against the endpoint for `<bos>The color of the sky is`, token IDs
   `[2, 818, 2258, 529, 506, 7217, 563]`.
5. Bind the returned token/logit/KV transcript, or the fail-closed hardware
   blocker, to the Doppler reference export for the same model identity and
   input contract.

The concrete Qwen companion step is:

```bash
bench/tools/run_qwen3_6_27b_af16_hardware_path.sh --cmaddr <endpoint>
```

That wrapper fetches `Clocksmith/rdrr` model path
`models/qwen-3-6-27b-q4k-eaf16` plus the shared
`models/qwen-3-6-27b-q4k-ehaf16` weight pack, verifies the evidence archive,
compiles the bundled Qwen HostPlan source, and runs the chat-template prompt
for `The color of the sky is` against the endpoint.

Gemma 4 E2B remains a control lane. It is useful for cheap failure
reproduction, smaller bundle checks, bounded simfabric diagnostics, and
regression isolation. It should not block the 31B hardware ask unless a failure
is clearly shared by both model families.

Gemma 4 26B/A4B MoE remains a later efficiency lane. It needs separate
Gemma-specific receipts for router logits, top-k expert selection,
token-to-expert dispatch, shared expert execution, expert output combine, and
per-expert batching. It should not borrow the E2B or dense-31B receipts, and it
is not part of the first hardware-access ask.

Do not claim full 31B parity from smoke-shape, selected-logit, or synthetic
receipts. Those receipts only prove the step they execute. Full 31B hardware
parity requires a returned hardware transcript plus a Doppler reference export
bound to the same manifest, execution graph, weights, and input set.

## 1. Current artifact paths and hashes

E2B bundle:

- execution manifest `runtime/zig/examples/execution-v1/gemma-4-e2b-smoke.json`
  sha256 `67e13946350e69ee62c75f06e80b94d44e15a18ba5858a8e9011636cfa6c9c26`
- host plan `bench/out/e2b-full-graph/host-plan.json`
  sha256 `0a5c357199f1b67a27682a8df9cab12812c3373fccda183c4930693553fdae91`
- memory plan `bench/out/e2b-full-graph/memory-plan.json`
  sha256 `dcac44caf9bff14a5124e1be9605a257212e2c92ffd9a68c1628ea789aa45b20`
- runtime config `bench/out/e2b-full-graph/runtime-config.json`
  sha256 `10a768e88312828d7995675163814e829ab1eaac652ac63b197bd46f2d1a9f80`
- simulator plan `bench/out/e2b-full-graph/simulator-plan.json`
  sha256 `384c78dd2269d3b3b4597a7bcdcb0e1d1224ead577de15b1dae95d158ee082dd`
- stream execution plan `bench/out/e2b-full-graph/gemma-4-e2b-stream-execution-plan.json`
  sha256 `e8fa1420ddcac5700338b9a1b96071d3403c95618c5c6ea536f24e581a505729`
- layer-block CSL kernel `bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
  sha256 `023b391f136de9f5feb65d206b1144c3dfe760d49adfb7a771f409f0c7fb23a4`
- runtime receipt `bench/out/e2b-full-graph/gemma-4-e2b-runtime-receipt.json`
  (compiler/runtime artifact receipt; not full-model inference)
- unified L1 rollup `bench/out/doe-run/all-lanes-summary-L1.json`
  (`evidenceEligibility.evidenceTier=synthetic_l1_layer_block`)
- E2B real-weight fixture `config/gemma-4-e2b-real-weight-fixture.json`
  and parity verdict `bench/out/gemma-4-e2b-real-weight-parity-L1.json`
  (BF16-derived smoke-contract slices, not manifest-shape execution)
- E2B BF16 diagnostic verdicts
  `bench/out/gemma-4-e2b-real-weight-parity-L{2,4,8,35}.json`
  (smoke-chain depth progress only, not promoted full-model evidence)
- E2B manifest-shape probe
  `bench/out/manifest-shape/gemma-4-e2b-manifest-shape-probe.json`
  (records the upstream local/global head-dim and grouped-KV contract)
- E2B manifest-shape attention-core diagnostic
  `bench/out/manifest-shape/gemma-4-e2b-manifest-shape-attention-core.json`
  (SdkLayout simfabric execution for local/global headDim 256/512 and
  grouped-KV stream reuse; not full attention/logits/model execution)
- Doppler WebGPU capture graph
  `bench/out/doppler-capture/gemma-4-e2b-doe-webgpu-capture-graph.json`
  (Doppler Node provider bootstrap plus Gemma-4 E2B WGSL/command capture
  through `doe-gpu/capture`; not production inference parity)
- Doppler capture-to-CSL attention-core lowering receipt
  `bench/out/doppler-capture/gemma-4-e2b-capture-to-csl-attention-core-lowering.json`
  (consumes the capture graph hash and binds it to the first
  SdkLayout/CSL attention-core simulator slice; not full captured-graph
  lowering)
- Doppler RDRR/int4ple fixture
  `config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json` and probe
  verdict `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json`
  (manifest/shard/tensor-span readability)
- Doppler RDRR Q4_K_M L1 smoke-contract parity verdict
  `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json`
  plus extraction and weights-audit artifacts under the same RDRR
  evidence directory (not Doppler production inference output parity)
- Doppler RDRR Q4_K_M diagnostic verdicts
  `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity-L{2,4,8,35}.json`
  (same smoke contract at diagnostic depths, not promoted full-model evidence)
- Doppler production INT4 PLE reference export contract
  `config/doppler-int4ple-reference-export.schema.json`, sample
  `examples/doppler-int4ple-reference-export.gemma-4-e2b.contract.json`,
  exporter `bench/tools/export_doppler_int4ple_reference.mjs`, and gate
  `bench/gates/doppler_int4ple_reference_export_gate.py`. The output-ready
  receipt path is
  `bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_int4ple_reference_export.json`
  after the exporter runs. The Doe CSL transcript receipt contract is
  `config/doe-csl-int4ple-transcript.schema.json`; the current blocked
  receipt is emitted by `bench/tools/run_doe_csl_int4ple_transcript.py` at
  `bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json`
  and validated by `bench/gates/doe_csl_int4ple_transcript_gate.py`.
  This is the preferred Cerebras reference lane, but it is not evidence until
  the Doppler transcript and a Doe CSL simfabric transcript for the same
  source identity pass the parity gate.

31B bundle (scale-target scaffold, same shape as E2B):

- execution manifest `runtime/zig/examples/execution-v1/gemma-4-31b-smoke.json`
  sha256 `753bce9331c65f84badb297658362bc158b2ada4e494d4da5a199716cba37f2e`
- host plan sha256 `d4f9501ea943aed141835bea8c10897c8fa59dc1d86ee606fd0e0895e4d8c4bd`
- memory plan sha256 `559f847aee4565be488f9db5224bd8d97455a070dccc1ef8b5b33c1450815f19`
- runtime config sha256 `797e628043cb64d647d6d92b07acf9f85d21ecd145be0ffa1262da985a46bc1e`
- simulator plan sha256 `903491aac2af6fedf80e6e72b104624fffbaf7b510a7f0ed6d8af11279eab4b8`
- runtime receipt `bench/out/31b-full-graph/gemma-4-31b-runtime-receipt.json`
  (scale-target scaffold; not manifest-shape 31B execution)

CSL runtime fixture registry (shared) sha256 `4428f5b22e716b3f04f1269dc426cc2ac5ec11c8b31b89ec655484f52a388fa2`.

## 2. What the simfabric proof demonstrates

The claimable local parity proof has two L1 lanes today:
`bench/out/doe-run/all-lanes-summary-L1.json` records the synthetic WebGPU,
CSL simfabric, and CSL WebGPU emulator lanes within fixture tolerance, and
`bench/out/gemma-4-e2b-real-weight-parity-L1.json` records BF16-derived
real-weight smoke-contract parity for the same L1 layer-block shape.
The depth matrix `bench/out/doe-run/depth-coverage-matrix.json` is the current
source for which declared depths are evidence-eligible. Diagnostic files at
deeper depths do not turn into E2B claims unless their summary carries
`evidenceEligibility.claimable=true`.

The Doppler RDRR/int4ple proof now has two separate steps. The structural
probe `bench/out/doppler-rdrr/gemma-4-e2b-int4ple-rdrr-probe.json` validates
the local Doppler production artifact's manifest, declared shard sizes,
selected shard hash, target tensor spans, Q4_K_M packed-size formulas, and
int4 per-layer embedding metadata. The Q4_K_M wrapper verdict
`bench/out/doppler-rdrr/gemma-4-e2b-int4ple-q4k-parity.json` dequantizes the
RDRR spans into Doe's existing L1 smoke-contract slice format and checks
WebGPU-vs-CSL simfabric parity. The diagnostic wrappers under the same
directory extend the smoke-chain depth only. None of these steps prove
Doppler production inference output parity or full E2B execution from the
RDRR artifact.

The manifest-shape probe is a third, separate diagnostic: it reads the raw
E2B SafeTensors metadata and records that upstream uses local `headDim=256`,
`globalHeadDim=512`, and `numKeyValueHeads=1`. It binds Doe's manifest
fields to that source metadata, but it is still not a real manifest-shape
execution path.

The next valuable Cerebras proof should use the production Doppler INT4 PLE
RDRR inference path as the source program, not the direct LiteRT/TFLite `.task`
path and not the Doe-side Doppler-equivalent WebGPU harness. The direct path
remains useful for shape and adapter work, but it is not the current
correctness-claim lane. The promotion target is a same-program parity receipt
at `/home/x/deco/doe/config/doe-csl-reference-parity.schema.json`: matching
Doppler WebGPU and Doe-emitted CSL bounded prefill+decode transcripts for the
same source artifact, manifest identity, graph or capture identity, weight
identity, and prompt/input contract under the declared tolerance policy. The
transcript must include full prefill completion, fixed-step greedy decode, real
KV/cache state, per-step logits hashes, matching selected token IDs, matching
final generated token sequence, no synthetic inputs or weights, and no stub
stages. A full `final_logits` tensor export is a useful intermediate bring-up
check, but not the final Cerebras-facing proof. Until the production INT4 PLE
reference transcript exists, the hardware ask remains scoped to the L1/smoke
and diagnostic evidence above.

The manifest-shape attention-core receipt is the first runtime-executed
diagnostic for those dimensions. It compiles and runs the local and global
head dimensions through SdkLayout, reusing one K/V stream for all eight query
heads to exercise the grouped-KV source contract. It is still only a
Q.K-plus-V diagnostic, not the production attention operator, decoder stack,
logits parity, hardware, or performance evidence.

The Doppler WebGPU capture graph is the shared-input step. It proves Doppler's
Node WebGPU bootstrap can install `doe-gpu/capture` and record a Gemma-4 E2B
WGSL/command graph with manifest identity and hashes. The capture-to-CSL
lowering receipt now consumes that graph for the first attention-core
SdkLayout/CSL simulator slice. Full captured-graph HostPlan lowering and
production Doppler inference parity remain blocked.

The INT4 PLE reference export step is separate from the capture and
Doe-side Doppler-equivalent harnesses. Its receipt must be produced by the
production Doppler WebGPU inference path and carry `inputsSynthetic=false`
and `weightsSynthetic=false`. The `final_logits` digest is only an
intermediate bring-up checkpoint. The promotion target is a bounded
deterministic prefill+decode transcript with per-step logits and token IDs
for the fixed tokenized prompt. Doe promotion starts only after the same
receipt is bound into `config/doe-csl-reference-parity.schema.json` with
matching manifest, graph, weight, and input hashes, real KV/cache behavior,
token-ID parity, per-step logits parity, no stubs, and no synthetic inputs
or weights.

Kernel surface: pre-attn RMSNorm, 8-head MHA with per-head vector
Q/K/V and multi-pair ROPE, post-attn RMSNorm, gated MLP with poly_c1
GELU. RMSNorm uses `math.sqrt` + a Newton-Raphson refinement step so
WSE vs WebGPU sqrt approximations agree bit-exactly at f32.

Scope caveats: the synthetic L1 rollup still uses seeded tensors, while the
real-weight L1 verdict uses BF16-derived smoke-contract slices. Both remain
the smoke layer-block shape, not manifest-shape execution and not full
end-to-end Gemma inference.

## 3. What hardware validation should run

Two paths either work; CEREBRAS_ASK.md inside the evidence bundle
has the operator-facing detail for both. MODEL_ACCESS.md inside the same
bundle pins the raw 31B checkpoint path, Doppler Q4K/af16 artifact, Hugging
Face cache environment, and claim boundary.

- **Path A — endpoint access.** Cerebras provides a reachable CS/WSC
  endpoint; we run the commands below from our side.
- **Path B — Cerebras-assisted source checkout run.** A Cerebras engineer runs
  the same source checkout commands internally and returns the receipt.
  No code from our side needs to run on Cerebras infrastructure —
  the runner is under `bench/runners/`.

Minimum sufficient ask (same source path either way):

1. Primary lane: Gemma 4 31B af16 full-prompt HostPlan runner. It uses the
   Doppler af16 manifest, the shared real Q4K weight pack, generated CSL, and
   concrete prompt token IDs. A successful run returns token/logit/KV transcript
   evidence for the prompt; a blocked run returns the named hardware blocker
   and last phase reached.
2. Current local bridge evidence: final-norm plus selected-logit splice for
   `<bos>The color of the sky is`, preserving token `3730` (` blue`) as the
   winner over Doppler's selected candidate set, using real Gemma 31B hidden
   state, CSL-owned final norm, real tied lm-head weights, and generated CSL.
   This is not full-prompt hardware evidence; it is the strongest local
   no-hardware check.
3. Fallback lane: 31B layer-block smoke with optional real-weight smoke slices,
   or Gemma af16 per-kernel cells. These are bounded checks and must be labeled
   as such.
4. Identity pin: hardware receipt records the same manifest, source graph,
   HostPlan, compile target inventory, weight identity, and tokenized prompt
   identity as the bundle.

## 4. What receipt fields we want back

Emitted as `doe_target_run_receipt` (existing schema) with
`target=hardware`, plus the hardware-specific fields below:

- `hardware.endpoint` — redacted (host/appliance tag, not raw IP)
- `hardware.jobId` — provider-assigned, redacted if policy requires
- `hardware.sdkVersion` — Cerebras SDK release running on the endpoint
- `hardware.fabricId` and `hardware.deviceArch` — for trace pinning
- `executedCompile.elapsedMs` and `executedRun.elapsedMs` — only if
  Cerebras policy permits disclosure
- `executedRun.status` — `succeeded` / `failed:<taxonomy>`
- `executedRun.generatedTokenIds` — if the full-prompt run reaches token
  output
- `executedRun.logitsDigest` or `executedRun.output.sha256` — if logits
  or output tensors are returned
- `executedRun.numericalParity` — token/logit comparison against the
  Doppler reference when output is available
- `executedRun.blocker` and `executedRun.lastPhaseReached` — if the run
  stops before token output
- `cacheKeyComponents` — kernel, plan, target, and shape fields emitted
  by the runner
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
- any performance claim beyond the returned parity receipt's own scope
- comparisons against other hardware unless the methodology is jointly
  signed off

The current public claims (see `docs/claim-discipline.md`) are
deliberately scoped to **portability and parity**. The narrow local
exception — emulator vs local simfabric wall time on the same host —
is explicitly labeled "local debug path only, NOT a Cerebras hardware
performance claim" in
`bench/tools/compare_csl_emulator_vs_simfabric_speed.py`.

## Where to look first

- Claim discipline: `docs/claim-discipline.md`
- Receipts: `bench/out/e2b-full-graph/`, `bench/out/31b-full-graph/`
- Cross-runtime evidence: `bench/out/doppler-reference/`
- Self-check: `python3 bench/tools/e2b_layer_block_self_check.py`
- Status shard: `docs/status/cerebras-csl.md`
