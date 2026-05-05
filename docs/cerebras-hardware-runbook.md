# Cerebras hardware runbook

Single operator-facing entry point for testing Doe's Gemma 4 31B and Qwen 3.6 27B
lanes end-to-end on Cerebras WSE/WSC. This is the practical "how to actually
run the validation" doc; deeper architecture, claim taxonomy, and acceptance
bars live under the cross-references at the bottom.

If you only have time to read one page, read this one.

## What this runbook covers

Two model lanes share the same CSL toolchain, the same evidence-bundle layout,
and the same hardware-ask shape:

- Gemma 4 31B dense — primary first hardware target
- Qwen 3.6 27B hybrid (full-attention + DeltaNet SSM) — second model target

Both lanes start from the smoke-shape layer-block runner, climb to manifest-
shape, and bind the hardware receipt back to the Doppler reference fixture.

## Two paths to a hardware receipt

Either path produces the same receipt shape. Pick whichever the endpoint
provider prefers.

- **Path A — endpoint access.** Cerebras provides a reachable CS/WSC endpoint
  and we run the runner from our side with `--cmaddr <addr>`.
- **Path B — Cerebras-assisted bundle run.** A Cerebras engineer runs the
  attached evidence bundle internally and returns the receipt JSON. Nothing
  from our side has to execute on Cerebras infrastructure; the runners under
  `bench/runners/csl-runners/` are self-contained.

## Quick reference

| Resource | Where |
|---|---|
| Current bundle pointer (auto-generated) | [`docs/cerebras-evidence-bundle-pointer.md`](cerebras-evidence-bundle-pointer.md) |
| Bundle source (packer extracts archive root files from this) | [`docs/cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md) |
| Build a fresh bundle | `bench/tools/prepare_cerebras_validation_bundle.sh` |
| Build emulator source archive | `python3 bench/tools/pack_cerebras_emulator_source_archive.py` |
| Verify a received archive | `python3 bench/tools/verify_cerebras_validation_archive.py --archive <path>` |
| Summarize an archive without unpacking | `bench/tools/summarize_cerebras_evidence_archive.sh <path>` |
| Verify a returned hardware receipt | `python3 bench/tools/verify_returned_hardware_receipt.py --receipt <path>` |
| Governance + claim boundaries | [`docs/hardware-validation-appendix.md`](hardware-validation-appendix.md) |
| Cerebras lane front door | [`docs/cerebras.md`](cerebras.md) |
| Gemma evidence ledger (acceptance bar + blockers) | [`docs/cerebras-evidence-ledger-gemma.md`](cerebras-evidence-ledger-gemma.md) |
| Qwen evidence ledger (acceptance bar + blockers) | [`docs/cerebras-evidence-ledger-qwen.md`](cerebras-evidence-ledger-qwen.md) |
| Live status snapshot | `bench/out/r3-cerebras-status/snapshot.md` (run `bench/tools/cerebras_status_snapshot.py`) |
| Live status shard | [`docs/status/cerebras-csl.md`](status/cerebras-csl.md) |
| Active fail-closed queue (Gemma) | `cerebras-evidence-ledger-gemma.md` § Active fail-closed queue |

## Gemma 4 31B — runner steps

Start with the smallest hardware step and climb.

### L1 smoke (first hardware ask)

```bash
cs_python bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py \
    --num-layers 1 \
    --size 1024 \
    --compile-out bench/out/hardware-run/compile \
    --trace-out  bench/out/hardware-run/trace.json \
    --cmaddr <operator-supplied>
```

This is a Gemma 4 31B dense layer-block smoke run. It is **not** a full 31B
manifest-shape claim and **not** a performance claim. Goal: prove the runner,
CSL source, SDK environment, compile path, hardware execution, and receipt
shape with a bounded tensor contract before climbing to the 61-layer chain
or manifest-shape streaming.

### Steps after L1 succeeds

1. Same runner, `--num-layers 61` — full smoke chain, still smoke-shape.
2. Same runner once `bench/out/gemma-4-31b-real-weights/` is materialized per
   `config/gemma-4-31b-real-weight-fixture.json` — smoke chain on real weights.
3. Manifest-shape (`headDim=160`, `numHeads=32`, `hiddenDim=5120`) with
   streaming weight residency, explicit KV policy, compile-artifact reuse, and
   bounded host memory.
4. Bind the resulting CSL hardware transcript to the Doppler reference export
   for the same bundle identity and input contract.

### AF16 simfabric cells

Gemma also has a bounded production-named CSL cell under
`bench/runners/csl-runners/gemma-4-31b-af16-cells/`. Regenerate the local
receipt set with:

```bash
python3 bench/tools/run_gemma4_31b_af16_simfabric_cells.py
```

The current cell is `lm_head_prefill_stable`. It compiles and runs the
dense-GEMV lm-head path at bounded shape, stages f16 activation and weight
payloads, reduces f32 partials across the row chain, and compares the sink
output with a host f32 oracle. The summary receipt is:

`bench/out/r3-1-31b-gemma-af16-simfabric-cells/summary-receipt.json`

For endpoint validation, pass:

```bash
python3 bench/tools/run_gemma4_31b_af16_simfabric_cells.py \
  --cmaddr <operator-supplied>
```

This is cell-level correctness evidence. It is not full 31B manifest-shape
execution and does not replace a returned hardware transcript.

### Current Gemma 31B blocker

`cerebras-evidence-ledger-gemma.md` Layer C is fail-closed on **Gemma af16 lm-head
dispatch evidence**. The bounded receipt at
`bench/out/r3-1-31b-af16-bounded-inference-smoke/receipt.json` validates the
f16 dtype contract but records `inferenceEvidenceGate.dispatch_evidence_lm_head_unbound`
because no token/logit/KV transcript exists yet. Diagnostic multi-row split-D2H
tiles still hang at `memcpy_d2h_start`; the live simfabric session
(`bench/out/r3-1-31b-af16-hostplan-session-bos-raw-sky-color-is-fast-embed512`)
is the active proof path. Hardware L1 smoke does not need this resolved, but
manifest-shape parity does.

## Qwen 3.6 27B — runner steps

Qwen does not yet have a single `layer_block_smoke` driver equivalent to
Gemma's. The validation surface is per-kernel CSL cells under
`bench/runners/csl-runners/qwen-3-6-27b-cells/`, plus the
`multi_token_decode_orchestrator_qwen.py` chain driver. Each cell is a small
end-to-end CSL kernel with its own `cs_python` driver.

### L1 cell smoke (first hardware ask)

Run any one cell against a reachable endpoint:

```bash
cs_python bench/runners/csl-runners/qwen-3-6-27b-cells/<kernel>_run.py \
    --cmaddr <operator-supplied> \
    --out-receipt bench/out/hardware-run/qwen-<kernel>-receipt.json
```

The 10 cells today are: `rmsnorm`, `rope_partial`, `residual`, `silu`,
`embed`, `tiled` (SUMMA matmul), `kv_write`, `gemv` (Q4_K dequant + GEMV),
`sample`, and `attn_decode`. The 11th compile target, `attn_prefill`, hits
`linker_pe_memory_overflow` and is not currently a cell.

The aggregator at
`bench/tools/synthesize_qwen_3_6_27b_simfabric_cells_summary_receipt.py` rolls
cell receipts into one summary at
`bench/out/r3-2-27b-qwen-simfabric-cells/summary-receipt.json`.

### Multi-token decode chain

Higher-level Qwen prefill + decode orchestration runs through:

```bash
cs_python bench/runners/csl-runners/multi_token_decode_orchestrator_qwen.py \
    --cmaddr <operator-supplied>
```

This is correctness-oriented chain evidence, not a single-shape layer-block
hardware proof.

### Steps after L1 succeeds

1. All 10 cells dispatch and parity-check against a reachable endpoint.
2. Multi-token decode chain runs end-to-end with bound transcript.
3. Manifest-shape with the GQA 24:4 / `head_dim=256` / `hidden=5120` /
   partial-rotary 0.25 / mropeSection contract from
   `runtime/zig/examples/execution-v1/qwen-3-6-27b-smoke.json`.
4. Bind to the Qwen Doppler reference fixture under
   `bench/fixtures/r3-2-27b-doppler-frozen/`.

### Current Qwen 27B blocker

The Qwen full-graph manifest compile receipt reports `blocker.class="none"`
and the per-kernel cells pass 10/10. The live engineering blocker is the
**`gemv` collectives compile path on the production Qwen smoke shape** at
manifest scale; per-kernel cells exercise GEMV in isolation but the manifest-
shape SDK fanout still needs hardware-side validation. Token-output evidence
is also blocked on lm-head dispatch, causal prefill attention, q/k norm, gated
FFN, depthwise convolution, linear attention/DeltaNet/SSM state, and recurrence-
carry receipts being bound to the HostPlan/CSL execution path; see the live
status shard for ordering.

## What receipt fields we need back

Emitted as `doe_target_run_receipt` (existing schema) with `target=hardware`,
plus the hardware-specific fields:

- `hardware.endpoint` — redacted (host/appliance tag, not raw IP)
- `hardware.jobId` — provider-assigned, redacted if policy requires
- `hardware.sdkVersion` — Cerebras SDK release running on the endpoint
- `hardware.fabricId` and `hardware.deviceArch` — for trace pinning
- `executedCompile.elapsedMs` and `executedRun.elapsedMs` — only if endpoint
  policy permits disclosure
- `executedRun.status` — `succeeded` / `failed:<taxonomy>`
- `executedRun.output.sha256` — matches or explicitly diverges from the
  simfabric trace's recorded `activation_out.f32` digest
- `executedRun.numericalParity` — `maxAbsErr` and `perLayerMaxAbsErr` against
  the simfabric reference
- `executedRun.perLayerOutputs[*]` — per-layer `.f32` digests for drift
  localization if the chain-final digest diverges
- `cacheKeyComponents` — kernel, plan, target, size (already emitted)
- Signed-off `claimScope` — explicit enumeration of what the receipt does and
  does not claim

Use `verify_returned_hardware_receipt.py` to mechanically check the returned
JSON before binding it.

## Publication boundaries

Per [`docs/claim-discipline.md`](claim-discipline.md), without explicit
endpoint-provider approval we will not publish:

- Hardware timing (`elapsedMs`) beyond what the operator authorizes.
- Endpoint identity, IP, physical location, rack or appliance IDs.
- Queue-depth, fabric-level, or operator-internal telemetry surfaced in SDK
  logs.
- Any performance claim beyond "matches simfabric reference within tolerance".
- Comparisons against other hardware unless the methodology is jointly signed
  off.

The current public claim scope is **portability and parity**, not speed.

## Email asks

When requesting a hardware run, attach the current bundle and pull pointer
metadata from `docs/cerebras-evidence-bundle-pointer.md` for the archive sha256
and verdict line. Example body:

> Subject: Gemma 4 31B dense smoke validation request on Cerebras hardware
>
> Hi <name>,
>
> We have a software evidence bundle for Doe's Gemma 4 on Cerebras lane and
> would like to validate the first 31B dense hardware step on WSE/WSC.
>
> The primary ask is intentionally small: a one-layer Gemma 4 31B dense
> layer-block smoke run via the runner above. Two acceptable paths: (A) we get
> temporary endpoint access and run the command with `--cmaddr`, or (B) a
> Cerebras engineer runs the attached bundle internally and returns the
> receipt JSON.
>
> Please return: `hardware.endpoint`, `hardware.jobId`, `hardware.sdkVersion`,
> `hardware.fabricId`, `hardware.deviceArch` (redacted as needed),
> `executedRun.status`, `executedRun.output.sha256`,
> `executedRun.numericalParity.maxAbsErr` and per-layer comparison fields, and
> any compile/runtime failure taxonomy if the run does not complete.
>
> Bundle pointer: <fill from docs/cerebras-evidence-bundle-pointer.md after
> clean rebuild>.
>
> If the 31B L1 smoke run succeeds, the natural follow-up is the same runner
> with `--num-layers 61`, still labeled smoke-shape evidence.
>
> We will not publish endpoint identity, fabric identity, queue details,
> timing, or performance comparisons without written approval.

The Qwen 27B ask uses the same email shape and the Qwen evidence summary
instead, but the Qwen layer-block smoke runner equivalent of
`gemma_4_31b_layer_block_smoke.py` is not yet authored. Until it lands, the
Qwen path is gated on completing that runner; do not cite a Qwen runner
filename in an external bundle.

## Local pre-flight before sending

Before circulating a bundle externally, regenerate from a clean tree and
spot-check the verdict:

```bash
git status                                        # clean tree
bench/tools/prepare_cerebras_validation_bundle.sh # rebuild + refresh pointer
python3 bench/tools/verify_cerebras_validation_archive.py \
    --archive bench/out/$(grep -oP 'doe-cerebras-evidence-\S+\.tar\.gz' \
        docs/cerebras-evidence-bundle-pointer.md | head -1)
```

The pointer file lists the archive sha256, MANIFEST sha256, BUNDLE_META sha256,
size, git commit, dirty flag, and verdict (`passed N/N steps`). If `git dirty`
shows `dirty` in the pointer, rebuild from a clean tree before circulation.

## See also

- [`docs/cerebras.md`](cerebras.md) — single front door for the whole lane
  (progress, source, reproduce, run on hardware, why).
- [`docs/cerebras-evidence-bundle.md`](cerebras-evidence-bundle.md) — bundle
  source-of-truth (the packer extracts archive-root files from marked sections
  here).
- [`docs/hardware-validation-appendix.md`](hardware-validation-appendix.md) —
  governance companion: artifact paths, simfabric-proof scope, publication
  boundaries.
- [`docs/cerebras-evidence-ledger-gemma.md`](cerebras-evidence-ledger-gemma.md) /
  [`docs/cerebras-evidence-ledger-qwen.md`](cerebras-evidence-ledger-qwen.md) — full
  evidence ledgers, integrity invariants, optimization roadmap.
- [`docs/status/cerebras-csl.md`](status/cerebras-csl.md) — live status shard.
