# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | `bench/out/doe-cerebras-evidence-20260421-0810-9c90fca3c1f5-dirty.tar.gz` |
| archive sha256 | `7a1af1ffb04f55906e5d4bf5ff069e1b470935457410c060a1918a325f36db2e` |
| MANIFEST.txt sha256 | `bdc3a2a8b6522a043d9da58d0f2f425b5635e101211c6c509e52035b2ba76fca` |
| BUNDLE_META.json sha256 | `30e5df578969f55855ed37699fd601b5bd26c468c012f682ec6e98a6f4c99204` |
| archive size (bytes) | `88785` |
| git commit | `9c90fca3c1f58aa336329a3cce2f1429faacf959` |
| git dirty | `dirty` |
| evidence bundle verdict | `passed` (17/17 steps) |

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
