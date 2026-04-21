# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | `bench/out/doe-cerebras-evidence-20260420-1937-ce8221028f83-dirty.tar.gz` |
| archive sha256 | `b011b0f396ba1c48c29d7cdcb3b4abd6e2fe1f6e49ea00bc643ab054ea99cf36` |
| MANIFEST.txt sha256 | `29ec10b8c05d29bb0c2c36402a1baec53abee6b0b914e2e1c9db55061b1a2e39` |
| BUNDLE_META.json sha256 | `be57becf6a2ed70283ac569a94745e01edaaf646e1d71e99cd911d5f91c332aa` |
| archive size (bytes) | `64229` |
| git commit | `ce8221028f83dc6292d1b19e3f11ec19dc1e36f4` |
| git dirty | `dirty` |
| evidence bundle verdict | `passed` (9/9 steps) |

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
