# Cerebras evidence bundle — README

You are holding a packed software-only evidence bundle for Doe's
Gemma-4-on-Cerebras lane. This file is the front door. Read it first,
then follow the run order below.

## What's at the archive root

- `README.md` — this file.
- `BUNDLE_META.json` — build stamp: UTC timestamp, git commit,
  dirty-tree flag, host OS, cs_python availability on the bundler.
- `MANIFEST.txt` — sha256 + claim-role + path for every file inside.
- `CLAIM_SCOPE.md` — what this bundle proves and, explicitly, what
  it does not. Read before drawing any conclusions.
- `MODEL_ACCESS.md` — cache roots, canonical Gemma 4 E2B artifact
  identities, download commands, validation commands, and demo scope.
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
   the external ask. Enumerates two paths — endpoint access (we run
   the runner) or Cerebras-assisted bundle run (Cerebras runs the
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
