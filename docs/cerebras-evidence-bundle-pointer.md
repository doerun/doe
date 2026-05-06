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
| regenerated at | `2026-05-06T15:26:47Z` |
| archive | `bench/out/doe-cerebras-evidence-20260506-1126-c51b737b320f.tar.gz` |
| archive sha256 | `e68d80ce56f16ec88421925e6841c4e93f854be5e812025135073abc11bdc3d3` |
| MANIFEST.txt sha256 | `4a6adaa599e77cadf4a36439457b3ba8f56b3b16d602523badc063155ad55dbf` |
| BUNDLE_META.json sha256 | `e7e3c40f6eea2f2d40466a5628c65b053f0e6a319ca96c07dcd591939491c16f` |
| archive size (bytes) | `1052457` |
| git commit | `c51b737b320f0e02f8b44f11673383bc939835dc` |
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
