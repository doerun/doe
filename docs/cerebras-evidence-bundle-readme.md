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

3. **Read `CLAIM_SCOPE.md`.** It enumerates the 5 claims this bundle
   backs with evidence, the claims it explicitly does not back,
   and the external dependencies that unlock further claims. Every
   backed claim points at a `claim-role` listed in `MANIFEST.txt`.

4. **Read `CEREBRAS_ASK.md`.** The operator-facing distillation of
   the external ask. Enumerates two paths — endpoint access (we run
   the runner) or Cerebras-assisted bundle run (Cerebras runs the
   bundle internally, returns the receipt) — plus the exact command,
   receipt fields, and publication boundaries for either.
   `docs/hardware-validation-appendix.md` is its parent document with
   the fuller context.

5. **Read `LOCAL_INSPECTION.md`** if you want to browse the
   evidence in a browser. Lists local-server commands for the
   status dashboard, E2B side-by-side demo, and SDK-GUI-style
   artifact viewer — all consuming the same bundle files without
   unpacking SDK binaries.

6. **Spot-check the receipts.** `MANIFEST.txt` gives a claim-role
   per file. Open any `model-runtime-receipt` or
   `cross-runtime-parity-verdict` and confirm the assertions match
   the appendix's summary. For the paranoid: re-compute sha256 of
   any `.json` and compare against the manifest row.

7. **Re-run local gates (optional).** If the unpacked archive lives
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
| `real-weight-parity-verdict` | Real-weight smoke-contract parity, including bundled diagnostic depths | Reviewers of the checkpoint-derived layer-block path |
| `doppler-rdrr-probe` | Manifest/shard/tensor-span probe for the Doppler int4ple artifact | Reviewers of structural RDRR ingestion |
| `doppler-rdrr-q4k-extraction` | Q4_K_M RDRR-to-smoke-slice materialization verdict | Reviewers of the RDRR dequant path |
| `doppler-rdrr-q4k-audit` | Shape/hash audit for RDRR-derived smoke-contract slices | Reviewers of the RDRR dequant path |
| `doppler-rdrr-q4k-parity` | RDRR-derived smoke-contract WebGPU-vs-CSL parity verdicts, including bundled diagnostic depths | Numerical reviewers; not Doppler production inference parity |
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
