# Cerebras evidence bundle — current pointer

**Auto-generated** by
`bench/tools/prepare_cerebras_validation_bundle.sh` on each clean
run. Do not hand-edit; the prep script overwrites this file so it
always reflects the last successful pack.

> **Freshness check.** This pointer is a snapshot of the *last successful
> pack* — not a live status. Compare `regenerated at` against
> `git log -1 --format=%cI HEAD` before circulating the archive
> externally. Regenerate via the prep script if the repo has advanced
> beyond the pinned `git commit` below.

## Latest archive

| Field | Value |
| --- | --- |
| regenerated at | `2026-05-05T14:37:47Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-1037-bc3f4b91281f.tar.gz` |
| archive sha256 | `de34125885f2ef29610759aa0295754d407813bd1119c93821b63dfe3495106f` |
| MANIFEST.txt sha256 | `bcb1fc6594de11f3ff9185a070b284f2de24d0fcb5618d06c74f8082e0a46324` |
| BUNDLE_META.json sha256 | `56f1bbda22668d28a46221b41af9d1481422451442ac9ae26fd9da2c9b6f62cc` |
| archive size (bytes) | `220196` |
| git commit | `bc3f4b91281f715dc121198c71cd24fbbbb18506` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (24/24 steps) |

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

The prep script refuses to pack from a dirty tree. The archive's own
`BUNDLE_META.json` is the authoritative source of truth for any bundle
in hand; this file just mirrors the values
from the last prep-script run on the repo.
