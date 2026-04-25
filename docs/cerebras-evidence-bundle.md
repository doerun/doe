# Cerebras evidence bundle

This is the single source document for the Cerebras evidence-bundle
governance pages. The packer extracts the marked sections below into
the archive-root files reviewers expect:

- `README.md`
- `CLAIM_SCOPE.md`
- `MODEL_ACCESS.md`
- `CEREBRAS_ASK.md`
- `LOCAL_INSPECTION.md`

`docs/cerebras-evidence-bundle-pointer.md` stays separate because it
is auto-generated after pack + verify and would be stale if it were
bundled.

<!-- archive:README.md:start -->
# Cerebras evidence bundle — README

You are holding a packed software-only evidence bundle for Doe's
Gemma-4-on-Cerebras lane. This file is the front door. Read it first,
then follow the run order below. The current external ask leads with
Gemma 4 31B dense hardware smoke evidence; the E2B artifacts remain
substantive control evidence and smaller repro fixtures.

## What's at the archive root

- `README.md` — this file.
- `BUNDLE_META.json` — build stamp: UTC timestamp, git commit,
  dirty-tree flag, host OS, cs_python availability on the bundler.
- `MANIFEST.txt` — sha256 + claim-role + path for every file inside.
- `CLAIM_SCOPE.md` — what this bundle proves and, explicitly, what
  it does not. Read before drawing any conclusions.
- `MODEL_ACCESS.md` — cache roots, canonical Gemma 4 E2B artifact
  identities, 31B fixture contracts where present, download commands,
  validation commands, and demo scope.
- `CEREBRAS_ASK.md` — operator-facing distillation: exact endpoint
  access needed, exact command to run, exact receipt fields to
  return, publication boundaries.
- `LOCAL_INSPECTION.md` — commands for reviewers who want to browse
  the evidence in a browser (status dashboard, E2B side-by-side,
  SDK-GUI-style viewer) with the same tools the bundler uses.

Every other file lives under its repo path (`docs/`, `bench/out/`,
`config/`) inside the tar; the packager preserves layout so
cross-references inside the receipts resolve as written.

## Run order

1. **Verify the archive itself** before trusting any of its contents:

   ```
   python3 bench/tools/verify_cerebras_validation_archive.py \
     --archive <this tarball>
   ```

   This extracts to a temp dir, re-hashes every file against
   `MANIFEST.txt`, checks `BUNDLE_META.json` required fields, and
   confirms the archive filename matches `BUNDLE_META.archiveFilename`.
   Any integrity failure is a reason to request a rebuild before
   acting on the contents.

2. **Read `BUNDLE_META.json`.** If `gitDirtyTree: true`, the bundle
   was built from an uncommitted working tree — prefer a clean
   rebuild before external circulation.

3. **Read `CLAIM_SCOPE.md`.** It enumerates the claims this bundle
   backs with evidence, the claims it explicitly does not back,
   and the external dependencies that unlock further claims. Every
   backed claim points at a `claim-role` listed in `MANIFEST.txt`.

4. **Read `MODEL_ACCESS.md`.** It pins the raw BF16 Hugging Face
   snapshot, the local Doppler RDRR/Q4_K_M artifact, the writable
   Hugging Face cache env vars, and the first-demo scope. Run
   `python3 bench/tools/prepare_gemma4_e2b_access.py --print-shell`
   in the repo when preparing a fresh host.

5. **Read `CEREBRAS_ASK.md`.** The operator-facing distillation of
   the external ask. The first requested run is the Gemma 4 31B dense
   L1 smoke runner. It also enumerates two paths — endpoint access (we
   run the runner) or Cerebras-assisted bundle run (Cerebras runs the
   bundle internally, returns the receipt) — plus the exact command,
   receipt fields, and publication boundaries for either.
   `docs/hardware-validation-appendix.md` is its parent document with
   the fuller context.

6. **Read `LOCAL_INSPECTION.md`** if you want to browse the
   evidence in a browser. Lists local-server commands for the
   status dashboard, E2B side-by-side demo, and SDK-GUI-style
   spatial compute viewer — all consuming the same bundle files without
   unpacking SDK binaries.

7. **Spot-check the receipts.** `MANIFEST.txt` gives a claim-role
   per file. Open any `model-runtime-receipt` or
   `cross-runtime-parity-verdict` and confirm the assertions match
   the appendix's summary. For the paranoid: re-compute sha256 of
   any `.json` and compare against the manifest row.

8. **Re-run local gates (optional).** If the unpacked archive lives
   on a host with `git` + Python available:

   ```
   python3 bench/tools/run_cerebras_evidence_bundle.py
   ```

   Runs the same local gates captured in the bundle's
   `rollup/cerebras-evidence-bundle/summary.json`. Re-running should
   yield the same `verdict: passed` unless the repo has drifted.

## Claim taxonomy at a glance

| claim-role | What it is | Who it's for |
| --- | --- | --- |
| `governance` | Policy + external ask + this README's source | Anyone |
| `real-weight-fixture` | Pinned bundle contract for E2B / 31B | Reviewers of the real-weight promotion path |
| `doppler-rdrr-fixture` | Pinned Doppler RDRR/int4ple artifact-readability contract | Reviewers of the Doppler production-artifact path |
| `model-runtime-receipt` | Per-model runtime evidence (E2B, 31B) | Primary reviewers |
| `cross-runtime-parity-verdict` | Layer-block diagnostic parity artifacts | Numerical reviewers |
| `emulator-accuracy-verdict` | CSL simfabric vs WebGPU emulator where claimable | Correctness reviewers |
| `emulator-speed-verdict` | Local-debug-only speedup (not hardware) | Ergonomics reviewers |
| `manifest-shape-probe` | Upstream E2B tensor-shape contract probe | Reviewers of the manifest-shape rewrite |
| `manifest-shape-execution-oracle` | CPU/Numpy raw-BF16 E2B text-forward oracle at upstream tensor dimensions | Reviewers of the manifest-shape rewrite; not Doe/CSL runtime evidence |
| `manifest-shape-attention-core` | SdkLayout diagnostic for E2B local/global headDim 256/512 plus grouped-KV stream reuse | Reviewers of the attention rewrite; not full attention/logits/model evidence |
| `doppler-webgpu-capture-graph` | Doppler Node WebGPU bootstrap plus Gemma-4 E2B WGSL/command capture through `doe-gpu/capture` | Reviewers of the shared JS/WGSL input surface; not HostPlan/SdkLayout/CSL execution |
| `real-weight-parity-verdict` | Real-weight smoke-contract parity, including bundled diagnostic smoke depths | Reviewers of the checkpoint-derived layer-block path |
| `doppler-rdrr-probe` | Manifest/shard/tensor-span probe for the Doppler int4ple artifact | Reviewers of structural RDRR ingestion |
| `doppler-rdrr-q4k-extraction` | Q4_K_M RDRR-to-smoke-slice materialization verdict | Reviewers of the RDRR dequant path |
| `doppler-rdrr-q4k-audit` | Shape/hash audit for RDRR-derived smoke-contract slices | Reviewers of the RDRR dequant path |
| `doppler-rdrr-q4k-parity` | RDRR-derived smoke-contract WebGPU-vs-CSL parity verdicts, including bundled diagnostic smoke depths | Numerical reviewers; not Doppler production inference parity |
| `doppler-int4ple-reference-export` | Production Doppler INT4 PLE reference export; final logits plus bounded decode transcript when present | Reviewers of the source reference lane; not Doe CSL parity by itself |
| `doppler-int4ple-execution-graph` | Hash-linked execution graph used by the production Doppler INT4 PLE reference | Reviewers checking source identity |
| `doppler-int4ple-reference-input` | Prompt and tokenized prompt bound into the reference input-set hash | Reviewers checking deterministic input identity |
| `doppler-int4ple-reference-output-tokens` | Generated token IDs from the bounded greedy transcript | Reviewers checking transcript token parity |
| `doppler-int4ple-reference-transcript` | Per-step logits and token IDs for the bounded Doppler reference transcript, without raw logits tensors | Numerical reviewers checking the transcript contract |
| `doe-csl-int4ple-blocked-transcript` | Doe CSL transcript receipt shape, graph-derived lowering plan, and normalized HostPlan bundle for the production INT4 PLE lane, currently blocked before simfabric output | Reviewers checking the missing proof producer and blocker taxonomy |
| `doppler-int4ple-pending-parity` | Doe parity receipt binding the production Doppler INT4 PLE reference and documenting the missing CSL transcript | Numerical reviewers; blocked until CSL emits the matching transcript |
| `target-run-receipt` | Per-target L1 receipt for WebGPU WGSL, CSL WebGPU emulator, or CSL simfabric | Reviewers of the side-by-side layer-block demo |
| `moe-lane-scope` | 26B/A4B MoE blocked-lane + 6 TODO receipts | Anyone asking about MoE |
| `rollup` | Summary artifacts (lanes, gate bundle) | Quick triage |
| `depth-coverage-rollup` | Which declared depths have raw files vs evidence-eligible receipts; today only L1 synthetic is claimable | Anyone asking "is this the full model?" |

## Contact and next steps

The external ask lives in `docs/hardware-validation-appendix.md`.
Nothing in this bundle should be circulated externally until its
verifier passes and `CLAIM_SCOPE.md` has been reviewed against what
you plan to claim.

If any required artifact is missing from `MANIFEST.txt` (e.g. you
see `missing:` lines in the manifest footer), rebuild the bundle
from a clean tree before external use.
<!-- archive:README.md:end -->

<!-- archive:CLAIM_SCOPE.md:start -->
# Cerebras evidence bundle — claim scope

This document is the **terms-of-bundle** for
`doe-cerebras-evidence-<YYYYMMDD-HHMM>-<shortSha>[-dirty].tar.gz`. It
is included in every such archive as `CLAIM_SCOPE.md` and states what
the bundle **does** and **does not** back with evidence.

It is distinct from `docs/hardware-validation-appendix.md`, which is
the external-facing outreach document describing what Cerebras would
need to run. This document is for the bundle itself: what it is honest
to say once a reviewer holds a copy.

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
   transcript receipt shape, graph-derived lowering blockers, a
   normalized HostPlan bundle, and the current missing simfabric
   producer. It is not Doe CSL parity, not hardware evidence, and not
   a performance claim.

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
   contracts. This is a lowering/artifact-chain claim, not a Doe/CSL
   full-model execution claim.

10. **Doppler-equivalent WebGPU and Doe-emitted CSL agree on the L1
   synthetic layer-block contract within `atol=1e-3`.** Explicitly
   labeled *Doppler-equivalent*: a separate WGSL harness matching the
   semantic contract, not Doppler's production inference path.

11. **CSL WebGPU emulator is faster than local CSL simfabric on the
   same host for local debug.** Backed by the L1 emulator speed
   verdict. Scoped explicitly to "local debug ergonomics" per
   `compare_csl_emulator_vs_simfabric_speed.py`.

12. **Unified Doe entrypoint routes to five backend targets, with
   runtime-output receipts for three L1 side-by-side lanes.** Backed
   by `rollup/all-lanes-summary-L1.json` plus `target-run-receipt`
   artifacts for `webgpu-wgsl`, `csl-sdklayout`, and
   `csl-webgpu-emulator`. `doe-metal` and `doe-vulkan` are
   backend-identity probes, not Gemma-4 output parity on Doe's native
   backend.

## What this bundle does NOT claim

Each non-claim here is actively gated in repo by
`bench/gates/claim_discipline_gate.py` and/or
`docs/claim-discipline.md`. Any archive prose that asserts these is a
bundle integrity failure.

- **Gemma-4 runs on Cerebras hardware.** No `hardware_success`
  receipt exists in this bundle. Simfabric is not hardware.

- **Any Gemma-4 / Cerebras / CSL / WSE / WSC performance claim
  outside the emulator-vs-local-simfabric debug-path exception.**

- **Gemma-4 31B runs at manifest shape.** The manifest is
  `numHeads=32, headDim=160`; the bundle evidences smoke shape only.

- **Gemma-4 26B/A4B MoE works on Cerebras, CSL, or any lane.** The
  bundle explicitly includes six `moe-lane-scope` TODO files plus a
  `lane-status.json` with `laneStatus=blocked`. Claim-discipline's MoE
  gate rejects "26B/A4B is running/working/operational" language.

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

- **31B real Gemma-4 weights have been used.** The 31B real-weight
  parity verdict remains blocked until its own extractor and parity
  receipt land.

- **Full E2B real-weight execution has been proven on Doe/CSL.** The
  E2B real-weight Doe/CSL evidence is L1 smoke-contract only. The
  manifest-shape full text-forward oracle is CPU/Numpy and does not
  promote the Doe runtime receipt.

- **Doppler production INT4 PLE parity against Doe CSL has been
  proven.** The production Doppler reference export is only the source
  side. The parity receipt remains blocked until Doe CSL simfabric
  emits the same bounded prefill+decode transcript with matching
  manifest, graph, weights, input set, real KV/cache behavior,
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
| Any MoE claim | Six MoE component receipts (router, top-k, dispatch, shared-expert, combine, per-expert-batching) replacing the current TODO files |

## Bundle expiration signals

- `BUNDLE_META.gitDirtyTree=true`: the bundler's working tree had
  uncommitted changes. The receipts may or may not correspond to a
  reproducible commit. Prefer a dirty=false rebuild before external
  circulation.
- Any file referenced by `MANIFEST.txt` that is missing at unpack
  time: bundle-integrity failure.
- A `hardware_success` receipt landing in-repo that postdates the
  bundle's git commit: the claim surface has expanded and the bundle
  understates current state.

## Reviewer workflow

1. Read `BUNDLE_META.json`; confirm `gitDirtyTree=false` and the
   short SHA matches what you expected.
2. Read `CLAIM_SCOPE.md`; know what the bundle backs.
3. Read `CEREBRAS_ASK.md`; it is the operator-facing command,
   endpoint-access ask, and receipt-field list.
4. Read `LOCAL_INSPECTION.md` if you want to browse the evidence in a
   browser.
5. Read `MANIFEST.txt`; see each file's `claim-role`.
6. Re-compute any `.json` sha256 you want to spot-check against the
   manifest entry.
7. Read `bench/out/cerebras-evidence-bundle/summary.json`; local gates
   should report `status=passed`, except documented skipped optional
   gates.

If any of 1-7 fails, reject the bundle and request a rebuild.
<!-- archive:CLAIM_SCOPE.md:end -->

<!-- archive:MODEL_ACCESS.md:start -->
# Gemma 4 E2B model access handoff

This is the model/cache side of the Cerebras evidence handoff. It pins
the local artifact identities and the environment variables that make
the raw SafeTensors, Doppler RDRR, and hardware-run commands resolve
consistently.

## Cache roots

The current Linux host should not use `/media/x/models` for Hugging
Face auth or cache state unless its permissions are fixed. A failed
`hf auth login` that tries to create
`/media/x/models/huggingface_cache` is an environment problem, not a
model problem.

Use the home-backed cache and explicit model roots:

```bash
export HF_HOME=/home/x/.cache/huggingface
export HUGGINGFACE_HUB_CACHE=/home/x/.cache/huggingface/hub
export HF_HUB_CACHE=/home/x/.cache/huggingface/hub
export DOE_MODELS_ROOT=/home/x/model-downloads
export DOE_GEMMA4_E2B_SAFETENSORS_DIR=/home/x/model-downloads/gemma4-e2b-it
export DOE_GEMMA4_E2B_RDRR_ROOT=/home/x/deco/doppler/models/local/gemma-4-e2b-it-q4k-ehf16-af32-int4ple
```

Run the preflight after changing any of those paths:

```bash
python3 bench/tools/prepare_gemma4_e2b_access.py --print-shell
```

Add `--create` to create the selected cache directories. Add
`--require-assets` when a CI/operator step must fail if the raw
SafeTensors or Doppler RDRR artifact is missing.

## Canonical artifacts

The canonical raw checkpoint source for the BF16/text oracle lane is
`google/gemma-4-E2B-it` from Hugging Face:

- upstream model id: `google/gemma-4-E2B-it`
- upstream page: <https://huggingface.co/google/gemma-4-E2B-it>
- local raw snapshot: `$DOE_GEMMA4_E2B_SAFETENSORS_DIR`
- expected local files: `config.json`, one or more `.safetensors`
  files, `tokenizer.json`, and `tokenizer_config.json`
- active Doe use: manifest-shape CPU oracle and BF16-derived
  smoke-contract layer-block slices

The canonical Doppler production-artifact lane is the local RDRR/Q4_K_M
fixture:

- fixture: `config/gemma-4-e2b-doppler-rdrr-int4ple-fixture.json`
- local root: `$DOE_GEMMA4_E2B_RDRR_ROOT`
- expected local files: `manifest.json`, `origin.json`,
  `tokenizer.json`, and shard files
- quantization: `Q4_K_M`
- active Doe use: RDRR structural probe, Q4_K_M smoke-slice
  extraction, and smoke-contract parity

Raw BF16 and RDRR/Q4_K_M are both active lanes. They prove different
things: the BF16 lane verifies the upstream text checkpoint and
smoke-contract slice extraction; the RDRR lane verifies that Doe can
consume Doppler's converted artifact shape and dequantized smoke
slices. Neither lane is full Doppler production inference parity yet.

## Download and validation commands

Authenticate without writing credentials into the model root:

```bash
hf auth login --token <token> --add-to-git-credential false
```

Download the raw BF16 snapshot:

```bash
hf download google/gemma-4-E2B-it \
  --local-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"
```

Validate the raw BF16 lane:

```bash
python3 bench/tools/probe_gemma4_e2b_manifest_shape.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"

python3 bench/tools/run_gemma4_e2b_manifest_shape_execution.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR"

python3 bench/tools/extract_gemma4_e2b_weight_slices.py \
  --source-dir "$DOE_GEMMA4_E2B_SAFETENSORS_DIR" \
  --out-json bench/out/gemma-4-e2b-real-weight-extraction.json
```

Validate the Doppler RDRR/Q4_K_M lane:

```bash
python3 bench/tools/probe_doppler_rdrr_artifact.py \
  --artifact-root "$DOE_GEMMA4_E2B_RDRR_ROOT"

python3 bench/tools/run_doppler_rdrr_q4k_parity.py \
  --artifact-root "$DOE_GEMMA4_E2B_RDRR_ROOT"
```

Those commands are path-resilient: if the environment variables above
are set, the tools use them as defaults. Explicit flags still win for
one-off runs.

## Cerebras access commands

Direct endpoint:

```bash
cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers 35 \
  --compile-out bench/out/hardware-run/compile \
  --trace-out bench/out/hardware-run/trace.json \
  --weights-dir bench/out/gemma-4-e2b-real-weights \
  --cmaddr "$DOE_CSL_CMADDR"
```

WSC appliance:

```bash
python3 runtime/zig/tools/csl_appliance_driver.py \
  --code-dir bench/out/streaming-executor/e2b-layer-block-source \
  --layout layout.csl \
  --compiler-args "<operator-supplied cslc args>" \
  --compile-output bench/out/hardware-run/compile \
  --runner-command "cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py --num-layers 35 --compile-out bench/out/hardware-run/compile --trace-out bench/out/hardware-run/trace.json --weights-dir bench/out/gemma-4-e2b-real-weights --cmaddr %CMADDR%" \
  --download "bench/out/hardware-run/trace.json:bench/out/hardware-run/trace.json" \
  --receipt-out bench/out/hardware-run/appliance-receipt.json \
  --system
```

The WSC command uses `%CMADDR%` so `SdkLauncher` resolves the endpoint
at run time. Receipts redact that to `$DOE_CSL_CMADDR`; raw endpoints
and credentials must not be checked into repo artifacts.

## First demo scope

The first demo should show:

- E2B slice proof as the primary live row: Doppler/RDRR identity,
  BF16/RDRR slice provenance, SdkLayout smoke status, parity, and
  blockers
- 31B dense as a structural/blocked row: stream graph and model receipt
  present, execution/hardware absent
- Cerebras hardware as absent until a `hardware_success` receipt exists

Do not show full E2B, 31B execution, MoE, or performance claims as
green until the corresponding model-level and hardware receipts exist.
<!-- archive:MODEL_ACCESS.md:end -->

<!-- archive:CEREBRAS_ASK.md:start -->
# Cerebras operator — the ask

Operator-facing page for whoever at Cerebras is running the validation
on the endpoint. Tight and single-purpose. The rest of the bundle's
documents are reviewer-facing; this one is for the person pressing
Enter on the hardware.

Before running, read `MODEL_ACCESS.md` in the bundle. It pins the raw
BF16 Hugging Face snapshot, the local Doppler RDRR/Q4_K_M artifact,
writable Hugging Face cache env vars, and the first-demo claim
boundary. The primary hardware ask is Gemma 4 31B dense L1 smoke
execution; E2B remains the smaller control lane and should not be
treated as a prerequisite for the 31B hardware receipt unless the
failure is clearly shared.

## Two paths — either works

**Path A (preferred): temporary endpoint access.** We run the runner
from our side against a Cerebras-provided endpoint:

1. **Reachable CS/WSC endpoint.** Either a direct `--cmaddr <ip:port>`
   target or an appliance SdkLauncher endpoint.
2. **SDK Python environment** matching the `csPython` on the bundler's
   host. SDK 2.10 is the active Doe CSL floor; older receipts are
   historical and should not be used for new hardware claims.
3. **Authorization to run the runner** in `bench/runners/csl-runners/`
   against the endpoint with the pinned manifest + graph + kernel
   source from this bundle.

**Path B: Cerebras-assisted bundle run.** A Cerebras engineer runs the
bundle internally on their cluster and returns the receipt:

1. **Unpack this archive** and run the `What to run` commands below.
   Kernel, manifest, and graph are all pinned inside the bundle with
   recorded sha256; `MANIFEST.txt` has every file's digest.
2. **Return the `doe_target_run_receipt`** with the fields listed under
   `What to return`. No code from our side needs to run on your
   cluster; the runner is self-contained under `bench/runners/`.
3. **Redact what your policy requires.** Every `hardware.*` field has
   an explicit `"redacted"` convention so we can compare receipts
   without leaking endpoint identity.

## What to run

Minimum viable primary run:

```bash
cs_python bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py \
  --num-layers 1 \
  --size 1024 \
  --compile-out bench/out/hardware-run/compile \
  --trace-out  bench/out/hardware-run/trace.json \
  --cmaddr <operator-supplied>
```

WSC appliance equivalent:

```bash
python3 runtime/zig/tools/csl_appliance_driver.py \
  --code-dir bench/out/streaming-executor/e2b-layer-block-source \
  --layout layout.csl \
  --compiler-args "<operator-supplied cslc args>" \
  --compile-output bench/out/hardware-run/compile \
  --runner-command "cs_python bench/runners/csl-runners/gemma_4_31b_layer_block_smoke.py --num-layers 1 --size 1024 --compile-out bench/out/hardware-run/compile --trace-out bench/out/hardware-run/trace.json --cmaddr %CMADDR%" \
  --download "bench/out/hardware-run/trace.json:bench/out/hardware-run/trace.json" \
  --receipt-out bench/out/hardware-run/appliance-receipt.json \
  --system
```

The appliance form intentionally uses `%CMADDR%` inside the launcher
command. The returned receipt redacts that to `$DOE_CSL_CMADDR`; do not
paste raw endpoint addresses into checked-in artifacts. The deprecated
appliance `SdkRuntime` binding is not part of this ask.

Run with the bundle's pinned smoke kernel at
`bench/out/streaming-executor/e2b-layer-block-source/transformer_layer_shape.csl`.
The same generated CSL source is intentionally used by the E2B and 31B
smoke runners; the 31B runner supplies the 61-layer model shape and
31B-specific stream contract.

If the 31B L1 run succeeds, the next conditional run is the same command
with `--num-layers 61`. That is still smoke-shape 31B evidence, not
manifest-shape 31B execution.

E2B control run, if the operator wants the smaller existing lane too:

```bash
cs_python bench/runners/csl-runners/e2b_layer_block_smoke.py \
  --num-layers 35 \
  --compile-out bench/out/hardware-run/e2b-control-compile \
  --trace-out  bench/out/hardware-run/e2b-control-trace.json \
  --cmaddr <operator-supplied>
```

For BF16-derived E2B real-weight smoke runs, first materialize and
validate the weights described in `MODEL_ACCESS.md`, then add:

```bash
--weights-dir bench/out/gemma-4-e2b-real-weights
```

Without `--weights-dir`, the hardware run remains a synthetic/smoke
tensor run and must not be described as real-weight evidence. 31B
real-weight evidence remains blocked until
`bench/out/gemma-4-31b-real-weights/` is materialized under its fixture
contract.

The 31B runner writes a trace whose `executedRun` section includes the
host numpy comparison for the same smoke-shape layer-block chain. For
the E2B control run, this additional parity check can be run after the
hardware trace returns:

```bash
python3 bench/tools/compare_runner_vs_synthetic.py \
  --runner-trace bench/out/hardware-run/e2b-control-trace.json \
  --synthetic-trace bench/out/streaming-executor/e2b-layer-block-synthetic-trace.json
```

For E2B, this should report `promotionEligible=true` with six of six
preconditions met, matching the simfabric run recorded in this bundle.

Stretch, if time permits:

- Re-run the 31B smoke command with `--num-layers 61`.
- When 31B real-weight slices are available, re-run with
  `--weights-dir <path>` to promote the corresponding real-weight
  fields on the receipt.

## What to return

Any `doe_target_run_receipt` JSON extended with the fields below. All
fields are explicit; anything redacted should be filled with the string
`"redacted"` rather than omitted so the shape is preserved.

- `hardware.endpoint`: operator-scoped tag, not raw IP, or `"redacted"`
- `hardware.jobId`: provider-assigned job identifier, or `"redacted"`
- `hardware.sdkVersion`: Cerebras SDK release string
- `hardware.fabricId`: fabric identity for trace pinning
- `hardware.deviceArch`: e.g. `"wse3"`
- `executedCompile.elapsedMs`: wall time, only if operator authorizes
  disclosure; otherwise `"redacted"`
- `executedRun.elapsedMs`: same
- `executedRun.status`: `"succeeded"` or `"failed:<taxonomy>"`
- `executedRun.output.sha256`: sha256 of `activation_out.f32`; for 31B
  L1 this is compared against the runner's host numpy reference, while
  E2B control runs can also compare against the pinned simfabric smoke
  trace
- `executedRun.numericalParity.maxAbsErr`: max |csl - numpy| across
  all positions of the output tensor
- `executedRun.numericalParity.perLayerMaxAbsErr`: per-layer same
- `executedRun.perLayerOutputs[*].{layer,sha256,path}`: per-layer
  `.f32` digests so drift can be located to a specific layer
- `cacheKeyComponents`: kernel, plan, target, size
- `claimScope`: explicit `{claimable: [...], notClaimable: [...]}` signed
  off by the operator

## What we will NOT publish without written approval

- Any hardware timing beyond what the operator authorizes
- Endpoint identity (IP, physical location, rack/appliance IDs)
- Queue-depth, fabric-level, or operator-internal telemetry in SDK logs
- Any performance claim beyond the receipt's own local numerical
  comparison fields
- Comparisons against other hardware unless the methodology is jointly
  signed off

See `docs/claim-discipline.md` for the full enforcement policy. The
claim-discipline gate in this repo rejects any performance prose that
does not cite a `hardware_success` receipt; the gate only goes INACTIVE
when such a receipt exists in `bench/out/`.

## Point of contact

Questions, clarifications, or receipt-field negotiation: reply to the
email thread this archive came from, or the sender address on the
outreach message. The Doe team is the point of contact; we handle the
interpretation side of anything that comes back.

`docs/hardware-validation-appendix.md` is the parent appendix;
`CEREBRAS_ASK.md` is its operational distillation. If the two ever
disagree, the appendix wins.
<!-- archive:CEREBRAS_ASK.md:end -->

<!-- archive:LOCAL_INSPECTION.md:start -->
# Bundle — local inspection

Commands for a reviewer who has unpacked the bundle into a repo
checkout and wants to browse the evidence with the same browser tools
the bundler uses. All commands assume the repo root is the current
directory.

## Pre-flight

```bash
python3 bench/tools/verify_cerebras_validation_archive.py \
  --archive <the tarball you received>
```

Must PASS before acting on anything inside. The verifier re-checks
every manifest sha, BUNDLE_META shape, claim-role taxonomy, and runs
the claim-discipline regex scan against every doc in the archive.

## Status dashboard (static)

Shows the rollup of target matrix + claim badges in one view.

```bash
# No server needed; static HTML
open demos/doe-status-dashboard/index.html
```

Or behind any static HTTP server if the browser refuses `file://`
relative fetches.

## E2B side-by-side demo (static OR with local CSL)

Shows WebGPU + CSL simfabric + CSL-WebGPU-emulator output comparisons
with the evidence cockpit strip.

Static-only mode:

```bash
python3 -m http.server 8020
# then open http://localhost:8020/demos/gemma4-e2b-csl-sim/
# click "Load Stored CSL" to fetch the pinned L=1 reference trace
```

Live mode, requiring `cs_python` on PATH:

```bash
python3 demos/gemma4-e2b-csl-sim/server.py --port 8020
# then open http://localhost:8020/demos/gemma4-e2b-csl-sim/
# "Run CSL Simulator" now dispatches a live cs_python invocation
```

## SDK-GUI-style spatial compute viewer

```bash
python3 demos/gemma4-e2b-csl-sim/server.py --port 8030
# then open http://localhost:8030/demos/doe-sdk-gui-viewer/
# default path auto-loads compile-L1; paste another compile workdir
# into the work-directory input to inspect that spatial compute state
```

The viewer is shaped after the Cerebras SDK GUI reference screenshots:
work-directory bar, route/color selector, scalable fabric viewport, PE
coordinate selector and drilldown, instruction/source/wavelet timeline
panes, debug pane, timeline navigation controls, and a terminal drawer
for exported commands.

It inspects repo-relative compile workdirs through the same
metadata-only server routes used by the E2B side-by-side demo. It maps
colors.json, host-I/O streams, stream telemetry, trace status, and Doe
evidence-bundle verdicts into the GUI without returning `.elf`, `.map`,
`.symbols`, `.viz`, or other SDK-owned file bytes.

The command strip also exposes copyable local commands for:

- `sdk_debug_shell visualize --artifact_dir ...` once the compile
  workdir is validated
- `python3 bench/tools/run_cerebras_evidence_bundle.py`
- `python3 bench/tools/pack_cerebras_validation_archive.py`
- `python3 bench/tools/verify_cerebras_validation_archive.py --archive ...`

On LAN HTTP origins where `navigator.clipboard` is blocked, the viewer
falls back to the browser's user-gesture copy path. When path redaction
is enabled, local-path commands are shown but not copyable.

## `sdk_debug_shell visualize` command

If the bundler's `BUNDLE_META.csPython.csPythonAvailableOnBundler` is
`true`, Cerebras SDK was reachable at pack time. The matching native
visualize command on a Cerebras-SDK-equipped host:

```bash
sdk_debug_shell visualize --artifact_dir <compile-workdir>
```

The `<compile-workdir>` is the compile workdir the runner wrote `.elf`,
`.lst`, `.map`, `.symbols`, and `.viz` files into during compilation.
These files are explicitly excluded from this bundle; they contain
SDK-internal binary artifacts that a reviewer should not receive
through a shared archive.

If `BUNDLE_META.csPython.csPythonAvailableOnBundler` is `false`, the
bundler had no Cerebras SDK installed; the visualize command is not
available via this bundle. Reviewers with their own SDK installation
can re-run the runner (see `CEREBRAS_ASK.md`) against the pinned
manifest/graph/kernel hashes in this bundle to produce their own
compile workdir, then visualize it locally.

## Quick archive summary

```bash
bench/tools/summarize_cerebras_evidence_archive.sh <archive>
```

Prints E2B/31B/MoE status, bundle gate verdict, manifest-shape
contract, RDRR Q4_K_M parity, declared-depth diagnostics, and emulator
verdicts entirely from inside the tarball via `tar -xzO | jq`, no
unpack needed.

## Evidence-bundle regen (on the bundler's tree)

```bash
python3 bench/tools/run_cerebras_evidence_bundle.py
```

Runs the local gates the bundle's
`rollup/cerebras-evidence-bundle/summary.json` captures. Useful if a
reviewer wants to confirm the same `verdict=passed` the archive records
still holds on the current repo state.

## Closing the loop

After a `hardware_success` receipt lands, re-run
`pack_cerebras_validation_archive.py` to produce a new archive whose
`BUNDLE_META.gitCommit` postdates the receipt and whose
claim-discipline gate state flips to INACTIVE for hardware-gated rules.
<!-- archive:LOCAL_INSPECTION.md:end -->
