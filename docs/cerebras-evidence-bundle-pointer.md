# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | `bench/out/doe-cerebras-evidence-20260420-1402-31a8ad02d07d-dirty.tar.gz` |
| archive sha256 | `6f35f66c3b7a56078352acdc1d047f14cb22c7bffcdc148290fcfb4e9e318a2f` |
| MANIFEST.txt sha256 | `60c8bf5da3803e4abf07b17318e8a27fb17e18a93fee6fb6eba8c5885c9de8dd` |
| BUNDLE_META.json sha256 | `6964770e0e66533e0b7bb1460e70aec44d7ec1b89ef762c0950b2f9b22163176` |
| archive size (bytes) | `45865` |
| git commit | `31a8ad02d07d0e2f5f908fa21c55cb1e48896a35` |
| git dirty | `dirty` |
| evidence bundle verdict | `passed` (5/5 steps) |

## Verify the bytes you received

```bash
python3 bench/tools/verify_cerebras_validation_archive.py \
    --archive <path-to-received-archive>
```

Expected: `PASS ... manifest sha integrity OK, claim-role taxonomy
clean, BUNDLE_META complete, claim-discipline scan clean`.

## Summarize without unpacking

```bash
bench/tools/summarize_cerebras_evidence_archive.sh <path-to-archive>
```

## Reproducibility note

If `git dirty` is `dirty`, the bundle was built from an uncommitted
working tree; rebuild from a clean tree before external circulation.
The archive's own `BUNDLE_META.json` is the authoritative source of
truth for any bundle in hand — this file just mirrors the values
from the last prep-script run on the repo.
