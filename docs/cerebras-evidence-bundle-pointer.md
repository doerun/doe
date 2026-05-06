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
| regenerated at | `2026-05-06T00:05:53Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-2005-f02520df1baa.tar.gz` |
| archive sha256 | `0742bfff175b2d16ee96d608df78730701b043d21a8d95870e8159492c7a21bb` |
| MANIFEST.txt sha256 | `ea049e90f3fc672c1e2fc72e1c2ba435bddf01af3029a2851b3802360848bf91` |
| BUNDLE_META.json sha256 | `ab09c905498449d8e7941ec583a187b0cbe15dff3a4ab668323938dbb9c02103` |
| archive size (bytes) | `793139` |
| git commit | `f02520df1baa417478720838a36fc272312d74fd` |
| git dirty | `clean` |
| evidence bundle verdict | `passed` (27/27 steps) |

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
