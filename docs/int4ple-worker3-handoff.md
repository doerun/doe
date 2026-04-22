# INT4 PLE Worker 3 handoff

Worker 3 owns the proof chain after the Doe HostPlan runtime emits a real
CSL transcript. This document pins the exact output contract, drift checks,
and hardware blocking rules for the current Gemma 4 E2B INT4 PLE lane.

This is not a hardware proof. Until the simulator parity and hardware receipt
gates are green, the shareable claim remains software evidence plus a request
for Cerebras hardware access.

## Source identity

The active source artifact is the Doppler-owned Program Bundle:

- Path: `/home/x/deco/doppler/examples/program-bundles/gemma-4-e2b-it-q4k-ehf16-af32-int4ple.program-bundle.json`
- Bundle ID: `gemma-4-e2b-it-q4k-ehf16-af32-int4ple-0894776e5a46`
- Program Bundle sha256: `3451df5d94b88af3935511b6a38dd2dfb42c02847cbcfbbeddd3420a866609de`
- Manifest sha256: `d3bd97d3f9065d2950cbee4267b93f345eabbb626eb7b8b9c96c9b0f590b6264`
- Execution graph sha256: `0894776e5a46f12d98d5574c050b3864806184cdf71ea640c2a03f4e30de0836`
- Weight set sha256: `54c2eb104625a2a4c0bd82e25be15c1330af765a92927445aa5e231b2668213d`
- Input set sha256: `c51e77b47bbcdefe32360b6251633fd2749a72a28622546abebc545bb6c8555a`

The Doe receipts must carry this identity through `sourceProgram` and any
hash-linked Program Bundle reference. Old Doe-generated identities are not
proof source identities unless they explicitly map to this Program Bundle.

## Output-ready transcript contract

Worker 2 is done only when
`bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json`
passes:

```bash
python3 bench/gates/doe_csl_int4ple_transcript_gate.py \
  --receipt bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json \
  --reference-export bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_program_bundle_reference_export.json \
  --require-simulator-success
```

The required fields are:

- `status = simulator_success`.
- `sourceProgram.executionDepth = full_model`.
- `sourceProgram.programBundleId` equals the bundle ID above.
- `sourceProgram.manifestSha256`, `graphSha256`, `weightSha256`, and
  `inputSetSha256` match the source identity above.
- `sourceProgram.programBundle.path` and `sha256` are present and hash-valid.
- `loweringPlan.status = ready_for_simfabric`.
- `loweringPlan.missingOperationCount = 0`.
- `loweringPlan.unsupportedKernels = []`.
- Every `loweringPlan.stages[].status` is
  `production_csl_kernel_available`.
- `hostPlanBundle.status = hostplan_ready`.
- Hash-linked `hostPlanBundle.normalizedExecution`, `hostPlan`,
  `runtimeConfig`, `memoryPlan`, `simulatorPlan`, `programBundle`, and
  `simulatorDriverResult` exist and match their sha256 fields.
- `hostPlanBundle.compileInputCoverage.missingTargetCount = 0`.
- `hostPlanBundle.weightMappingCoverage.status = complete`.
- `hostPlanBundle.weightMappingCoverage.missingWeightCount = 0`.
- `hostPlanBundle.hostIoLayoutCoverage.status = complete`.
- `hostPlanBundle.simulatorDriverResult.compileStatus = succeeded`.
- `hostPlanBundle.simulatorDriverResult.runStatus = succeeded`.
- `simulatorRun.status = succeeded`.
- `simulatorRun.executionTarget = simfabric`.
- `simulatorRun.compileStatus = succeeded`.
- `simulatorRun.kernelIsStub = false`.
- Hash-linked `simulatorRun.driverResult`, `tracePath`, and `progressPath`
  exist where the receipt says they exist.
- `cslTranscript.status = output_ready`.
- `cslTranscript.actualDecodeSteps` equals
  `decodeRequest.expectedActualDecodeSteps` and is greater than zero.
- `cslTranscript.stopReason` equals `decodeRequest.expectedStopReason`.
- Hash-linked `cslTranscript.transcript` exists and matches its sha256.
- Hash-linked `cslTranscript.generatedTokenIds` exists, has
  `dtype = uint32`, and its `tokenCount` equals `actualDecodeSteps`.
- `cslTranscript.logitsDigests` has exactly one entry per actual decode step.
- Each logits digest has `dtype = float32`, a valid shape, a selected token,
  and a hash-linked logits artifact.
- `kvCacheEvidence.realKvCache = true`.
- `kvCacheEvidence.cacheWriteCount > 0`.
- `kvCacheEvidence.cacheReadCount > 0`.
- `kvCacheEvidence.layerSpanCoverage.coveredLayerCount` equals
  `layerSpanCoverage.layerCount`.
- `kvCacheEvidence.stepStateDigests` has exactly one entry per actual decode
  step.
- `inputsSynthetic = false`.
- `weightsSynthetic = false`.

Any failure above is a Worker 2 runtime-output blocker, not a parity blocker.

## Parity promotion contract

After the transcript is output-ready, Worker 3 binds and gates parity:

```bash
python3 bench/tools/bind_doppler_int4ple_reference_to_csl_parity.py \
  --reference-export bench/out/doppler-reference/gemma-4-e2b-int4ple-production-final-logits/doppler_program_bundle_reference_export.json \
  --csl-transcript-receipt bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-transcript.blocked.json \
  --out bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-reference-parity.pending.json

python3 bench/gates/csl_reference_parity_gate.py \
  --receipt bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-reference-parity.pending.json \
  --require-promotion-ready
```

The strict parity gate must require:

- `comparison.status = passed`.
- Same manifest hash.
- Same execution graph hash.
- Same weight hash.
- Same input set hash.
- Full model depth executed.
- External reference transcript bound.
- CSL transcript hash bound.
- Generated token IDs match.
- Stop reason matches.
- Per-step logits pass tolerance.
- Real KV/cache evidence is present.
- Stub stages are absent.
- Synthetic inputs and weights are absent.

If parity fails after an output-ready transcript exists, classify the failure
before touching hardware: identity mismatch, token mismatch, stop-reason
mismatch, logits tolerance mismatch, KV/cache evidence missing, stub leakage,
or synthetic artifact leakage.

## Drift checks

Worker 3 must reject stale receipts when Worker 1 or Worker 2 regenerate
artifacts. The minimum freshness check is:

```bash
python3 bench/gates/int4ple_worker3_freshness_gate.py
```

- The Program Bundle file hash still matches `sourceProgram.programBundle`.
- The Program Bundle manifest and graph hashes match the Doppler reference
  export.
- `sourceProgram.manifestSha256`, `graphSha256`, `weightSha256`, and
  `inputSetSha256` match the reference export.
- Every non-pending path/hash pair in the transcript, parity, and hardware
  receipts points to an existing file and hashes to the recorded sha256.
- The parity trace path points at the current transcript receipt and its
  sha256 matches.
- The hardware receipt points at the current simulator transcript and parity
  receipts and both sha256 fields match.

Schema failures, missing hash-linked artifacts, or identity drift must fail
before any Worker 3 command can claim a proof failure. A strict gate should
fail for missing transcript, missing KV/cache, failed parity, or pending
hardware, not because paths or hashes silently drifted.

## Hardware blocking policy

Prepare the hardware receipt only after receipts are stable:

```bash
python3 bench/tools/prepare_doe_csl_int4ple_hardware_receipt.py \
  --execution-target wsc_appliance \
  --program-bundle /home/x/deco/doppler/examples/program-bundles/gemma-4-e2b-it-q4k-ehf16-af32-int4ple.program-bundle.json

python3 bench/gates/doe_csl_int4ple_hardware_receipt_gate.py \
  --receipt bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-hardware-receipt.pending.json
```

The receipt must remain blocked until simulator parity is green:

- `hardwareRun.status = pending_simulator_parity` while sim parity has not
  passed.
- `promotionCriteria.hardwareExecuted = false` until a real hardware run
  occurs.
- `promotionCriteria.hardwareSuccessClaimable = false` until the strict
  hardware gate passes.
- `hardwareRun.endpointRedaction = $DOE_CSL_CMADDR`.
- No raw cmaddr endpoint or secret may appear in `hardwareRun.command`,
  `driverReceipt`, or related hardware fields.

Before a hardware proof can be claimed, this command must pass:

```bash
python3 bench/gates/doe_csl_int4ple_hardware_receipt_gate.py \
  --receipt bench/out/doppler-reference/gemma-4-e2b-int4ple-doe-csl-hardware-receipt.pending.json \
  --require-hardware-success
```

Until then, the correct state is a green pending hardware receipt plus a
failing strict hardware-success gate.
