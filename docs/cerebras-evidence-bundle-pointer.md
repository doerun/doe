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
| regenerated at | `2026-05-06T15:46:45Z` |
| archive | `bench/out/doe-cerebras-evidence-20260506-1146-627cb4c50716.tar.gz` |
| archive sha256 | `27f91b78d106bfbc4dd8c72b1151a2cd4c7d9ec16e645419d06d143048a213d6` |
| MANIFEST.txt sha256 | `eaaa48ee72bc7d3c296fb5161adb57acf2c366005b2497b7bf2ff13216fac97e` |
| BUNDLE_META.json sha256 | `9056511176ab34e2271b5fec3cf6a3cc063c002ef1e34d60f75bf2327ab73f43` |
| archive size (bytes) | `1052319` |
| git commit | `627cb4c50716044aef9d3a5eb5bf7828c7020c98` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (28/28 steps) |

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
