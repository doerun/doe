# Cerebras operator — the ask

Operator-facing page for whoever at Cerebras is running the
validation on the endpoint. Tight and single-purpose. The rest of
the bundle's documents are reviewer-facing; this one is for the
person pressing Enter on the hardware.

Before running, read `MODEL_ACCESS.md` in the bundle. It pins the
raw BF16 Hugging Face snapshot, the local Doppler RDRR/Q4_K_M
artifact, writable Hugging Face cache env vars, and the first-demo
claim boundary.

## Two paths — either works

**Path A (preferred): temporary endpoint access.** We run the runner
from our side against a Cerebras-provided endpoint:

1. **Reachable CS/WSC endpoint.** Either a direct `--cmaddr <ip:port>`
   target or an appliance SdkLauncher endpoint.
2. **SDK Python environment** matching the `csPython` on the
   bundler's host. SDK 2.10 is the active Doe CSL floor; older
   receipts are historical and should not be used for new hardware
   claims.
3. **Authorization to run the runner** in `bench/runners/csl-runners/`
   against the endpoint with the pinned manifest + graph + kernel
   source from this bundle.

**Path B: Cerebras-assisted bundle run.** A Cerebras engineer runs the
bundle internally on their cluster and returns the receipt:

1. **Unpack this archive** and run the `What to run` commands below.
   Kernel, manifest, and graph are all pinned inside the bundle with
   recorded sha256; `MANIFEST.txt` has every file's digest.
2. **Return the `doe_target_run_receipt`** with the fields listed
   under `What to return`. No code from our side needs to run on your
   cluster — the runner is self-contained under `bench/runners/`.
3. **Redact what your policy requires.** Every `hardware.*` field has
   an explicit `"redacted"` convention so we can compare receipts
   without leaking endpoint identity.

## What to run

**Minimum viable:**

```bash
cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers 35 \
  --compile-out bench/out/hardware-run/compile \
  --trace-out  bench/out/hardware-run/trace.json \
  --cmaddr <operator-supplied>
```

**WSC appliance equivalent:**

```bash
python3 runtime/zig/tools/csl_appliance_driver.py \
  --code-dir bench/out/streaming-executor/e2b-layer-block-source \
  --layout layout.csl \
  --compiler-args "<operator-supplied cslc args>" \
  --compile-output bench/out/hardware-run/compile \
  --runner-command "cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py --num-layers 35 --compile-out bench/out/hardware-run/compile --trace-out bench/out/hardware-run/trace.json --cmaddr %CMADDR%" \
  --download "bench/out/hardware-run/trace.json:bench/out/hardware-run/trace.json" \
  --receipt-out bench/out/hardware-run/appliance-receipt.json \
  --system
```

The appliance form intentionally uses `%CMADDR%` inside the launcher command.
The returned receipt redacts that to `$DOE_CSL_CMADDR`; do not paste raw
endpoint addresses into checked-in artifacts. The deprecated appliance
`SdkRuntime` binding is not part of this ask.

Run with the bundle's pinned kernel at
`bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`
(sha256 `023b391f136de9f5feb65d206b1144c3dfe760d49adfb7a771f409f0c7fb23a4`).

For BF16-derived real-weight smoke runs, first materialize and validate the
weights described in `MODEL_ACCESS.md`, then add:

```bash
--weights-dir bench/out/gemma-4-e2b-real-weights
```

to either command above. Without `--weights-dir`, the hardware run remains a
synthetic/smoke tensor run and must not be described as real-weight evidence.

**Parity check after the run:**

```bash
python3 bench/tools/compare_runner_vs_synthetic.py \
  --runner-trace bench/out/hardware-run/trace.json \
  --synthetic-trace bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json
```

This should report `promotionEligible=true` with 6/6 preconditions
met, matching the simfabric run recorded in this bundle.

**Stretch, if time permits:**

- Re-run with `--num-layers 61` against the 31B runner
  (`bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py`).
- When real weight slices are available, re-run with
  `--weights-dir <path>` to promote `syntheticWeightsAbsent` /
  `weightHashMatched` to true on the receipt.

## What to return

Any `doe_target_run_receipt` (JSON) extended with the fields below.
All fields are explicit; anything redacted should be filled with the
string `"redacted"` rather than omitted so the shape is preserved.

- `hardware.endpoint` — operator-scoped tag (not raw IP), or `"redacted"`
- `hardware.jobId` — provider-assigned job identifier, or `"redacted"`
- `hardware.sdkVersion` — Cerebras SDK release string
- `hardware.fabricId` — fabric identity for trace pinning
- `hardware.deviceArch` — e.g. `"wse3"`
- `executedCompile.elapsedMs` — wall time, only if operator
  authorizes disclosure; otherwise `"redacted"`
- `executedRun.elapsedMs` — same
- `executedRun.status` — `"succeeded"` or `"failed:<taxonomy>"`
- `executedRun.output.sha256` — sha256 of `activation_out.f32`.
  Compared against the simfabric trace's recorded digest.
- `executedRun.numericalParity.maxAbsErr` — max |csl − numpy| across
  all positions of the output tensor
- `executedRun.numericalParity.perLayerMaxAbsErr` — per-layer same
- `executedRun.perLayerOutputs[*].{layer,sha256,path}` — per-layer
  `.f32` digests so drift can be located to a specific layer
- `cacheKeyComponents` — kernel, plan, target, size (the runner
  already emits these as of the gap-1 seeding tick)
- `claimScope` — explicit `{claimable: [...], notClaimable: [...]}`
  signed off by the operator

## What we will NOT publish without written approval

- Any hardware timing beyond what the operator authorizes
- Endpoint identity (IP, physical location, rack/appliance IDs)
- Queue-depth, fabric-level, or operator-internal telemetry in SDK logs
- Any performance claim beyond "matches simfabric reference within
  tolerance", which is what the receipt explicitly states
- Comparisons against other hardware unless the methodology is
  jointly signed off

See `docs/claim-discipline.md` for the full enforcement policy. The
claim-discipline gate in this repo rejects any performance prose
that doesn't cite a `hardware_success` receipt; the gate only goes
INACTIVE when such a receipt exists in `bench/out/`.

## Point of contact

Questions, clarifications, or receipt-field negotiation: reply to
the email thread this archive came from, or the sender address on
the outreach message. The Doe team (bundle originator) is the point
of contact — we handle the interpretation side of anything that
comes back.

`docs/hardware-validation-appendix.md` is the parent appendix;
`CEREBRAS_ASK.md` is its operational distillation. If the two ever
disagree, the appendix wins (it is the external-facing contract;
this file is its summary).
