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

1. **Gemma-4 E2B layer-block runs bit-exact under CSL simfabric.**
   Backed by `model-runtime-receipt` + `cross-runtime-parity-verdict`
   for E2B. All 35 layers, `maxAbsErr=0.0` per layer vs scalar-f32
   numpy reference, 6/6 cross-runtime parity preconditions met.

2. **Gemma-4 31B layer-block runs bit-exact under CSL simfabric at
   smoke shape.** Backed by 31B `model-runtime-receipt` +
   `cross-runtime-parity-verdict`. 61 layers chained; same smoke
   dimensions as E2B (`numHeads=8, headDim=8, kvLen=4, size=1024`).

3. **Doppler-equivalent WebGPU (Dawn-backed) matches CSL per-layer
   within `atol=1e-3`.** Backed by `emulator-accuracy-verdict`.
   Explicitly labeled *Doppler-equivalent* — a separate WGSL harness
   matching the semantic contract, not Doppler's production inference
   path.

4. **CSL WebGPU emulator is faster than local CSL simfabric on the
   same host.** Backed by `emulator-speed-verdict-L1` (~3740x) +
   `emulator-speed-verdict-L35` (~7674x). Scoped explicitly to
   "local debug ergonomics" per `compare_csl_emulator_vs_simfabric_speed.py`.

5. **Unified Doe entrypoint routes to 5 real backend targets.**
   Backed by `rollup/all-lanes-summary-L1.json`: webgpu-wgsl,
   doe-metal (backendId=doe_direct_plan), doe-vulkan, csl-sdklayout,
   csl-webgpu-emulator. `doe-metal`/`doe-vulkan` are backend-identity
   probes — not Gemma-4 output parity on Doe's native backend.

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

- **Doe executes the full Gemma-4 model end-to-end.** The bundle
  evidences the transformer layer-block only: no embedding, unembed,
  KV cache, or sampling boundary.

- **Real Gemma-4 weights have been used.** The
  `real-weight-parity-verdict` files for E2B and 31B both show
  `verdict=blocked_weights_absent` — the external checkpoint
  extractor is the blocker for every promotion criterion in
  `realWeightEvidence.promotionCriteriaMet`.

## What must land externally to unlock additional claims

| Unlock | External dependency |
| --- | --- |
| Real-weight layer-block parity | Doppler-provided weight extractor materializes `bench/out/gemma-4-{e2b,31b}-real-weights/` matching the fixture contract |
| Manifest-shape execution | Kernel rewrite for `headDim=512` (E2B) or `headDim=160` (31B); in-repo structural work |
| Full E2B end-to-end | Embed + 35 transformer + unembed + sample wired through the streaming runtime; in-repo structural work |
| Gemma-4 runs on Cerebras hardware | Hardware receipt via `--cmaddr` or `csl_appliance_driver.py`; external endpoint access |
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
3. Read `docs/hardware-validation-appendix.md` — know what the
   external ask is.
4. Read `MANIFEST.txt` — see each file's `claim-role`.
5. Re-compute any `.json` sha256 you want to spot-check against the
   manifest entry.
6. Read `bench/out/cerebras-evidence-bundle/summary.json` — 5 local
   gates should all report `status=passed`.

If any of 1–6 fails, reject the bundle and request a rebuild.
