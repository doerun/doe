# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | `bench/out/doe-cerebras-evidence-20260420-1747-f069b36115b2-dirty.tar.gz` |
| archive sha256 | `ff0d7c95cdf3353e40365ec320bcdfec3fd4bde882c5b1e00f85ae331949cd20` |
| MANIFEST.txt sha256 | `6f2128c364c9aef5ae108cf3781480282be6b240d3271cede566b7cd4459d9c6` |
| BUNDLE_META.json sha256 | `f3a59412d4e855cd71de1740e705db45ced5d6be605fdc50c28ada927563ef51` |
| archive size (bytes) | `53663` |
| git commit | `f069b36115b24fb8c8b39d37b68541ab1fb098d1` |
| git dirty | `dirty` |
| evidence bundle verdict | `passed` (6/6 steps) |

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
