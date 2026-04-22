# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

## Latest archive

| Field | Value |
| --- | --- |
| archive | `bench/out/doe-cerebras-evidence-20260422-1630-b121de880db7-dirty.tar.gz` |
| archive sha256 | `554e5d9f91174ddf2e5294155d3c2558c9e79b59635e3ba1c17a7665e0865edb` |
| MANIFEST.txt sha256 | `09a80980b02dfa60364373439af1d246ecf28bb3d3c8bdf2f2a827c34f2436a1` |
| BUNDLE_META.json sha256 | `55292a4c598d8ca59f09e9ce6970d196dd03c6b642afe5a31f32b303ff846dd4` |
| archive size (bytes) | `129401` |
| git commit | `b121de880db7700d293bb3495d589c328c813521` |
| git dirty | `dirty` |
| evidence bundle verdict | `passed` (31/31 steps) |

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
