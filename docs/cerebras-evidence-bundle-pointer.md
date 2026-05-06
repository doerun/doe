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
| regenerated at | `2026-05-06T00:16:28Z` |
| archive | `bench/out/doe-cerebras-evidence-20260505-2016-9664c22a2199.tar.gz` |
| archive sha256 | `b6d45334f0ad7d8d499f99d2354fe6a487ed74a5fab9f7ae0c6106528f479a60` |
| MANIFEST.txt sha256 | `ceac6f1a5c7cb8868653c782d7b331f026d5b1c5585301338f7ea37272e4d535` |
| BUNDLE_META.json sha256 | `911d8c135de99d0bd1d84916e320d3b591d7bda5019766ac0e04972983dc7433` |
| archive size (bytes) | `792992` |
| git commit | `9664c22a2199b01fc04188ba339daf887a29db3e` |
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
