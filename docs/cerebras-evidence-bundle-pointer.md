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
| regenerated at | `2026-05-05T17:55:48Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-1355-39521f744989.tar.gz` |
| archive sha256 | `9fc10145af78fa982b8afad0227808247739728554bed879e4032e9dee1941ad` |
| MANIFEST.txt sha256 | `6feba5029b9a672f75edfc6fa1e648497f53e9f725463dfd507b637320af80b2` |
| BUNDLE_META.json sha256 | `d89e1e6bbbbe19eee7ee3ce7815cd59cb0587fe841f925fdbb95d72e08aa1685` |
| archive size (bytes) | `735248` |
| git commit | `39521f744989e682d4b261a37b1cd11a9f46f8a7` |
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
