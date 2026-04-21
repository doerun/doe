# Cerebras evidence bundle — claim scope

This document is the **terms-of-bundle** for
`doe-cerebras-evidence-<YYYYMMDD-HHMM>-<shortSha>[-dirty].tar.gz`. It
is included in every such archive as `CLAIM_SCOPE.md` (via the
packager's allow-list) and states what the bundle **does** and
**does not** back with evidence.

It is distinct from `docs/hardware-validation-appendix.md`, which is
the external-facing outreach document describing what Cerebras would
need to run. This document is for the bundle itself — what it's
honest to say once a reviewer holds a copy.

## What this bundle claims

Each claim below is backed by an artifact inside the bundle,
enumerated in `MANIFEST.txt` with its `claim-role` tag.

1. **Gemma-4 E2B-shaped L1 synthetic layer-block parity is evidenced.**
   Backed by `rollup/all-lanes-summary-L1.json`, whose
   `evidenceEligibility.claimable=true`,
   `evidenceTier=synthetic_l1_layer_block`, and
   `runtimeParityTolerance.rollupVerdict=all_within_tolerance`.
   This is one layer-block with seeded tensors, not real weights and
   not full E2B.

2. **Gemma-4 E2B L1 real-weight smoke-contract parity is evidenced.**
   Backed by the E2B real-weight parity verdict and model-runtime
   receipt. The weights are BF16-derived smoke-contract slices
   materialized from the raw SafeTensors source discoverable through
   Doppler's local int4ple origin metadata. This is still one L1 smoke
   layer-block contract, not manifest-shape execution and not full E2B.

3. **Doe can structurally read the local Doppler Gemma-4 E2B int4ple
   RDRR artifact.** Backed by the Doppler RDRR fixture and probe
   verdict. This validates manifest/origin hashes, declared shard
   sizes, selected shard hash, target tensor spans, Q4_K_M packed-size
   formulas, and int4 PLE metadata. The structural probe itself is not
   the Q4_K_M parity verdict and not Doppler production inference
   output parity.

4. **Doppler RDRR Q4_K_M L1 smoke-contract parity is evidenced.**
   Backed by the RDRR Q4_K_M extraction artifact, RDRR weights audit,
   wrapper parity verdict, and inner WebGPU-vs-CSL simfabric parity
   verdict. This dequantizes the local RDRR Q4_K_M spans into Doe's
   existing E2B L1 smoke-contract slice format. It is not Doppler
   production inference output parity, not manifest-shape execution,
   and not full E2B.

5. **The production Doppler INT4 PLE lane has an output-ready
   reference export when the `doppler-int4ple-reference-export`
   artifact is present.** This is source-reference evidence only. The
   final-logits tensor is an intermediate checkpoint; the promotion
   target is a bounded deterministic prefill+decode transcript with
   per-step logits and token IDs. The
   `doe-csl-int4ple-blocked-transcript` artifact records the Doe CSL
   transcript receipt shape, graph-derived lowering blockers, and the
   current missing simfabric producer.
   It is not Doe CSL parity, not hardware evidence, and not a performance
   claim.

6. **E2B declared-depth smoke-chain diagnostics are bundled.** Backed
   by the BF16-derived and RDRR Q4_K_M diagnostic parity verdicts for
   the declared smoke depths beyond L1. These artifacts show depth
   progress for the same smoke contract; they are not promoted release
   evidence, manifest-shape execution, full E2B, or hardware evidence.

7. **The raw BF16 Gemma-4 E2B text checkpoint executes at manifest
   shape in a CPU/Numpy oracle.** Backed by the
   `manifest-shape-execution-oracle` artifact. This covers one
   text-only token through embed, PLE, all E2B decoder layers, final
   norm, and tied lm-head top-k at upstream local/global head
   dimensions. It is not Doe/CSL runtime evidence, not hardware
   evidence, and not a performance claim.

8. **Doe/CSL executes the E2B manifest-shape attention-core diagnostic
   for local/global head dimensions.** Backed by the
   `manifest-shape-attention-core` artifact. This covers SdkLayout
   simfabric execution for `headDim=256`, `globalHeadDim=512`, and
   grouped-KV stream reuse across eight query heads. It is not full
   attention, not decoder-stack execution, not logits parity, not
   hardware, and not a performance claim.

9. **Doe carries E2B and 31B through governed compiler/runtime
   artifacts.** Backed by the model-runtime receipts and fixture
   contracts. This is a lowering/artifact-chain claim, not a
   Doe/CSL full-model execution claim.

10. **Doppler-equivalent WebGPU and Doe-emitted CSL agree on the L1
   synthetic layer-block contract within `atol=1e-3`.** Explicitly
   labeled *Doppler-equivalent* — a separate WGSL harness matching
   the semantic contract, not Doppler's production inference path.

11. **CSL WebGPU emulator is faster than local CSL simfabric on the
   same host for local debug.** Backed by the L1 emulator speed
   verdict. Scoped explicitly to "local debug ergonomics" per
   `compare_csl_emulator_vs_simfabric_speed.py`.

12. **Unified Doe entrypoint routes to 5 backend targets, with
   runtime-output receipts for 3 L1 side-by-side lanes.** Backed by
   `rollup/all-lanes-summary-L1.json` plus `target-run-receipt`
   artifacts for `webgpu-wgsl`, `csl-sdklayout`, and
   `csl-webgpu-emulator`. `doe-metal`/`doe-vulkan` are
   backend-identity probes — not Gemma-4 output parity on Doe's
   native backend.

## What this bundle does NOT claim

Each non-claim here is **actively gated** in repo by
`bench/gates/claim_discipline_gate.py` and/or
`docs/claim-discipline.md`. Any archive prose that asserts these is
a bundle integrity failure.

- **Gemma-4 runs on Cerebras hardware.** No `hardware_success`
  receipt exists in this bundle. Simfabric is not hardware.

- **Any Gemma-4 / Cerebras / CSL / WSE / WSC performance claim
  outside the emulator-vs-local-simfabric debug-path exception.**

- **Gemma-4 31B runs at manifest shape.** The manifest is
  `numHeads=32, headDim=160`; the bundle evidences smoke shape only.

- **Gemma-4 26B/A4B MoE works on Cerebras, CSL, or any lane.** The
  bundle explicitly includes 6 `moe-lane-scope` TODO files + a
  `lane-status.json` with `laneStatus=blocked`. Claim-discipline's
  MoE gate rejects "26B/A4B is running/working/operational" language.

- **Doe executes the full Gemma-4 model end-to-end.** The bundle's
  manifest-shape full text-forward artifact is a CPU/Numpy oracle.
  Doe/CSL runtime evidence remains scoped to the layer-block smoke
  contract and does not yet cover a manifest-shape end-to-end runtime
  receipt.

- **L2/L4/L8/L35 are claimable E2B parity depths.** The depth matrix
  distinguishes raw diagnostic files from evidence-eligible receipts.
  Bundled BF16/RDRR smoke diagnostics beyond L1 are not promoted
  receipts. Today only L1 synthetic and E2B L1 real-weight
  smoke-contract evidence are claimable.

- **31B real Gemma-4 weights have been used.** The 31B
  real-weight parity verdict remains blocked until its own extractor
  and parity receipt land.

- **Full E2B real-weight execution has been proven on Doe/CSL.** The
  E2B real-weight Doe/CSL evidence is L1 smoke-contract only. The
  manifest-shape full text-forward oracle is CPU/Numpy and does not
  promote the Doe runtime receipt.

- **Doppler production INT4 PLE parity against Doe CSL has been
  proven.** The production Doppler reference export is only the
  source side. The parity receipt remains blocked until Doe CSL
  simfabric emits the same bounded prefill+decode transcript with
  matching manifest, graph, weights, input set, real KV/cache behavior,
  per-step logits, token IDs, no stubs, and no synthetic inputs or
  weights.

## What must land externally to unlock additional claims

| Unlock | External dependency |
| --- | --- |
| Doppler production INT4 PLE transcript parity | Doppler-owned production prefill+decode transcript export plus Doe CSL simfabric transcript for the same prompt/input contract, manifest, graph, weights, real KV/cache behavior, per-step logits, and token IDs |
| 31B real-weight layer-block parity | 31B extractor materializes `bench/out/gemma-4-31b-real-weights/` matching the fixture contract |
| Manifest-shape execution | Embed/unembed, decoder-stack stream binding, full attention semantics, and logits parity for E2B local `headDim=256`, `globalHeadDim=512`, `numKeyValueHeads=1`, or 31B `headDim=160`; in-repo structural work |
| Full E2B end-to-end | Embed + 35 transformer + unembed + sample wired through the streaming runtime; in-repo structural work |
| Gemma-4 runs on Cerebras hardware | Hardware receipt via either (a) endpoint access for us to run the runner with `--cmaddr` / `csl_appliance_driver.py`, or (b) Cerebras-assisted bundle run that returns the receipt |
| Any MoE claim | 6 MoE component receipts (router, top-k, dispatch, shared-expert, combine, per-expert-batching) replacing the current TODO files |

## Bundle expiration signals

- `BUNDLE_META.gitDirtyTree=true`: the bundler's working tree had
  uncommitted changes. The receipts may or may not correspond to a
  reproducible commit. **Prefer a dirty=false rebuild before
  external circulation.**
- Any file referenced by `MANIFEST.txt` that is missing at unpack
  time: bundle-integrity failure — a reviewer cannot verify the
  evidence they were told they hold.
- A `hardware_success` receipt landing in-repo that postdates the
  bundle's git commit: the claim surface has expanded and the bundle
  understates current state.

## Reviewer workflow

1. Read `BUNDLE_META.json` — confirm `gitDirtyTree=false` and the
   short SHA matches what you expected.
2. Read `CLAIM_SCOPE.md` (this file) — know what the bundle backs.
3. Read `CEREBRAS_ASK.md` — operator-facing command, endpoint-access
   ask, and receipt-field list. `docs/hardware-validation-appendix.md`
   is the parent document with fuller context.
4. Read `LOCAL_INSPECTION.md` if you want to browse the evidence in
   a browser (status dashboard / E2B side-by-side / SDK-GUI viewer).
5. Read `MANIFEST.txt` — see each file's `claim-role`.
6. Re-compute any `.json` sha256 you want to spot-check against the
   manifest entry.
7. Read `bench/out/cerebras-evidence-bundle/summary.json` — local
   gates should report `status=passed`, except documented skipped
   optional gates.

If any of 1–7 fails, reject the bundle and request a rebuild.
