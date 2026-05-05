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
| regenerated at | `2026-04-25T19:27:00Z` |
| archive | `bench/out/doe-cerebras-evidence-20260425-1927-517490bef2a5.tar.gz` |
| archive sha256 | `e8cc98a84d270d6a189b99b1680960b225820d9434c928c701b1cc056b1f180c` |
| MANIFEST.txt sha256 | `fefd0b95aa7c75647b0824d3d3c8cec95c21798e685704c589cc03984ce7e04a` |
| BUNDLE_META.json sha256 | `ef16a40a372eb3b3b2794d3df1da10ccc7b4c2438aa99972ce76f092d147539f` |
| archive size (bytes) | `167446` |
| git commit | `517490bef2a5b4d6c5bd268b1e558629e3a37dd6` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (23/23 steps) |

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
